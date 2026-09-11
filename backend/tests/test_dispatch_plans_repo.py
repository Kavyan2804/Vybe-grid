"""Tests for the dispatch-plans repository.

Covers:
  - Insert + read-back via ``get_latest_for_site``
  - The ``(site_id, tick_at)`` unique constraint is enforced
"""

from datetime import datetime, timezone

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models.sites import Site
from src.db.models.forecasts import Forecast
from src.db.models.dispatch_plans import DispatchPlan
from src.db.repositories.dispatch_plans import DispatchPlanRepository


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _seed_site(session: AsyncSession, site_id: str = "test-site") -> Site:
    site = Site(
        id=site_id,
        name="Test Site",
        timezone="Asia/Kolkata",
        config_version=1,
        config={"battery": {"capacity_kwh": 50}},
    )
    session.add(site)
    await session.flush()
    return site


async def _seed_forecast(session: AsyncSession, site_id: str = "test-site") -> Forecast:
    forecast = Forecast(
        site_id=site_id,
        issued_at=datetime(2026, 1, 14, 9, 0, tzinfo=timezone.utc),
        horizon_hours=24,
        source="openmeteo",
        stale=False,
        series=[{"hour": 0, "ghi_w_m2": 210}],
    )
    session.add(forecast)
    await session.flush()
    return forecast


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_insert_and_read_back(db_session: AsyncSession) -> None:
    """Insert a dispatch_plans row and read it back via ``get_latest_for_site``."""
    site = await _seed_site(db_session)
    forecast = await _seed_forecast(db_session, site.id)
    repo = DispatchPlanRepository(db_session)

    tick = datetime(2026, 1, 14, 9, 0, tzinfo=timezone.utc)
    plan = DispatchPlan(
        site_id=site.id,
        tick_at=tick,
        forecast_id=forecast.id,
        config_version=1,
        starting_soc_kwh=12.4,
        series=[{"hour": 0, "diesel_on": False}],
        objective_cost=812.4,
        solver_status="optimal",
        solve_ms=4210,
        source="milp",
    )
    await repo.create(plan)

    latest = await repo.get_latest_for_site(site.id)
    assert latest is not None
    assert latest.site_id == site.id
    assert latest.tick_at == tick
    assert latest.starting_soc_kwh == pytest.approx(12.4)
    assert latest.solver_status == "optimal"
    assert latest.source == "milp"
    assert latest.series == [{"hour": 0, "diesel_on": False}]


@pytest.mark.asyncio
async def test_unique_constraint_site_id_tick_at(db_session: AsyncSession) -> None:
    """Duplicate ``(site_id, tick_at)`` must fail with IntegrityError."""
    site = await _seed_site(db_session, "dup-site")
    forecast = await _seed_forecast(db_session, site.id)
    repo = DispatchPlanRepository(db_session)

    tick = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
    plan_kwargs = dict(
        site_id=site.id,
        tick_at=tick,
        forecast_id=forecast.id,
        config_version=1,
        starting_soc_kwh=10.0,
        series=[],
        objective_cost=100.0,
        solver_status="optimal",
        solve_ms=100,
        source="milp",
    )

    await repo.create(DispatchPlan(**plan_kwargs))

    with pytest.raises(IntegrityError):
        await repo.create(DispatchPlan(**plan_kwargs))
        await db_session.flush()
