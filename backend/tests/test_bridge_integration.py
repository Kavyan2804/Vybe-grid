"""Postgres bridge integration: tick → plan + telemetry + dispatch_log + baseline + savings."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from src.db.models.baseline import BaselineDispatchLog, BaselineTelemetry
from src.db.models.dispatch_log import DispatchLog
from src.db.models.dispatch_plans import DispatchPlan
from src.db.models.telemetry import Telemetry
from src.schemas.telemetry import TelemetryPoint
from src.services import optimizer_bridge
from src.services.optimizer_bridge import run_tick_sync
from src.services.savings_service import FuelConversion, calculate_savings


SITE_ID = "Dharavi Microgrid"


@pytest.fixture
def bridge_db(database_url_sync: str, monkeypatch: pytest.MonkeyPatch):
    """Point the sync bridge engine at the testcontainer and reset its session factory."""
    engine = create_engine(database_url_sync, future=True)
    factory = sessionmaker(bind=engine, future=True, expire_on_commit=False)
    monkeypatch.setattr(optimizer_bridge, "_sync_engine", engine)
    monkeypatch.setattr(optimizer_bridge, "_SyncSessionFactory", factory)
    return factory


@pytest.mark.integration
def test_run_tick_sync_persists_plan_telemetry_dispatch_and_baseline(bridge_db, monkeypatch):
    """One tick writes the full ledger triple + shadow baseline on identical conditions."""

    class FixedForecastAdapter:
        def fetch_forecast(self, site):
            from optimizer.domain.entities import Forecast

            now = datetime.now(timezone.utc)
            return Forecast(
                solar_kw=[20.0] * 12 + [2.0] * 12,
                load_kw=[18.0] * 24,
                source="integration-fixture",
                stale=False,
                fetched_at=now,
            )

    monkeypatch.setattr(optimizer_bridge, "OpenMeteoForecastAdapter", FixedForecastAdapter)

    summary = run_tick_sync(SITE_ID)
    assert summary["site_id"] == SITE_ID
    assert summary["plan_id"] is not None

    with bridge_db() as session:
        plans = session.execute(
            select(func.count()).select_from(DispatchPlan).where(DispatchPlan.site_id == SITE_ID)
        ).scalar_one()
        telemetry_count = session.execute(
            select(func.count()).select_from(Telemetry).where(Telemetry.site_id == SITE_ID)
        ).scalar_one()
        logs = session.execute(select(func.count()).select_from(DispatchLog)).scalar_one()
        baseline_tel = session.execute(
            select(func.count())
            .select_from(BaselineTelemetry)
            .where(BaselineTelemetry.site_id == SITE_ID)
        ).scalar_one()
        baseline_logs = session.execute(
            select(func.count()).select_from(BaselineDispatchLog)
        ).scalar_one()

        assert plans >= 1
        assert telemetry_count >= 1
        assert logs >= 1
        assert baseline_tel >= 1
        assert baseline_logs >= 1

        latest_tel = session.execute(
            select(Telemetry).where(Telemetry.site_id == SITE_ID).order_by(Telemetry.at.desc())
        ).scalars().first()
        latest_base = session.execute(
            select(BaselineTelemetry)
            .where(BaselineTelemetry.site_id == SITE_ID)
            .order_by(BaselineTelemetry.at.desc())
        ).scalars().first()
        assert latest_tel is not None and latest_base is not None
        assert latest_tel.at == latest_base.at
        assert latest_base.solar_kw == pytest.approx(latest_tel.solar_kw, rel=0, abs=1e-6)
        assert latest_base.load_kw == pytest.approx(latest_tel.load_kw, rel=0, abs=1e-6)

        conversion = FuelConversion(
            fuel_litres_per_kwh=0.28,
            fuel_cost_per_litre=90.0,
            co2_kg_per_litre=2.68,
        )
        result = calculate_savings(
            [
                TelemetryPoint(
                    id="opt-1",
                    site_id=SITE_ID,
                    at=latest_tel.at,
                    soc_kwh=latest_tel.soc_kwh,
                    diesel_on=latest_tel.diesel_on,
                    diesel_kw=latest_tel.diesel_kw,
                    batt_kw=latest_tel.batt_kw,
                    solar_kw=latest_tel.solar_kw,
                    load_kw=latest_tel.load_kw,
                    source="simulator",
                    config_version=1,
                )
            ],
            [
                TelemetryPoint(
                    id="base-1",
                    site_id=SITE_ID,
                    at=latest_base.at,
                    soc_kwh=latest_base.soc_kwh,
                    diesel_on=latest_base.diesel_on,
                    diesel_kw=latest_base.diesel_kw,
                    batt_kw=latest_base.batt_kw,
                    solar_kw=latest_base.solar_kw,
                    load_kw=latest_base.load_kw,
                    source="baseline",
                    config_version=1,
                )
            ],
            conversion,
        )
        assert result.site_id == SITE_ID
        assert result.optimized is not None
        assert result.baseline is not None
