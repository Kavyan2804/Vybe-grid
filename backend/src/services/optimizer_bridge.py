"""Bridges the optimizer's rolling-horizon loop to the real Postgres database.

This is the piece Phase 2/3 were missing: `optimizer/application/rolling_horizon_service.py`
is fully synchronous (Pyomo, httpx and the digital twin all block), while the backend's own
`src/db/repositories/*` are async (`AsyncSession`). Rather than rewrite either side, this module
gives the optimizer's `PlanRepository` / `TelemetryRepository` / `ExecutionRepository` / `AlertPort`
ports (optimizer/domain/ports.py) a *synchronous* SQLAlchemy implementation that writes to the
exact same tables `src/db/models/*` declares, using a separate sync engine. `run_tick_sync()` is
the callable the scheduler (backend/src/scheduler/tick.py) invokes once per site per tick, off the
asyncio event loop via `run_in_executor` (see `scheduled_tick` below and its use in `main.py`).

Read endpoints (`api/overview.py`, `api/plans.py`, `api/telemetry.py`, `api/forecasts.py`) stay on
the existing async repositories — only the write side (this module) needed a bridge.

Known simplification, recorded rather than hidden: the optimizer treats `site.name` as the site's
identity throughout (`DispatchPlan.site_id = site.name`, `telemetry_repository.latest_soc(site.name)`).
Sites in this codebase are still single-tenant, so `settings.default_site_id` is kept equal to the
YAML site config's `name` field rather than introducing a second slug — see `config/settings.py`.
"""

from __future__ import annotations

import asyncio
import logging
import sys
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy import create_engine

# --- make the sibling `optimizer/` package importable regardless of how uvicorn was launched ---
_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from optimizer.application.baseline_service import MicrogridState  # noqa: E402
from optimizer.application.rolling_horizon_service import RollingHorizonService  # noqa: E402
from optimizer.domain.entities import (  # noqa: E402
    ActualState,
    DispatchDecision,
    DispatchPlan,
    Forecast,
    Site,
    load_site_from_yaml,
)
from optimizer.domain.ports import AlertPort, ExecutionRepository, PlanRepository, TelemetryRepository  # noqa: E402
from optimizer.infrastructure.dispatch_simulator.adapter import SimulatorDispatchAdapter  # noqa: E402
from optimizer.infrastructure.forecast_openmeteo.adapter import OpenMeteoForecastAdapter  # noqa: E402
from optimizer.infrastructure.optimizer_pyomo.adapter import PyomoHighsOptimizerAdapter  # noqa: E402

from src.config.settings import get_settings
from src.realtime.broadcaster import RealtimeEvent, RealtimeEventType, broadcaster
from src.db.models.alerts import Alert, AlertState, AlertType
from src.db.models.baseline import BaselineTelemetry
from src.db.models.dispatch_log import DispatchLog
from src.db.models.dispatch_plans import DispatchPlan as DispatchPlanORM
from src.db.models.forecasts import Forecast as ForecastORM
from src.db.models.sites import Site as SiteORM
from src.db.models.telemetry import Telemetry

# One site for now — a slug -> YAML path table, extended by adding a line, not a code change
# (REPO_STRUCTURE.md §1's "config-driven site" promise).
SITE_CONFIG_PATHS: dict[str, Path] = {
    "Dharavi Microgrid": _REPO_ROOT / "optimizer" / "sites" / "example-site.yml",
}

_sync_engine = None
_SyncSessionFactory: sessionmaker | None = None


def _sync_session_factory() -> sessionmaker:
    """Lazily build a sync engine/sessionmaker against the same database as the async one.

    Built lazily (not at import time) so importing this module never opens a connection —
    useful for tests that only exercise the pure mapping helpers below.
    """
    global _sync_engine, _SyncSessionFactory
    if _SyncSessionFactory is None:
        settings = get_settings()
        _sync_engine = create_engine(settings.database_url_sync, future=True)
        _SyncSessionFactory = sessionmaker(bind=_sync_engine, future=True, expire_on_commit=False)
    return _SyncSessionFactory


# ---------------------------------------------------------------------------
# Mapping: optimizer entities <-> the DB/API JSON shape (batt_charge_kw / batt_discharge_kw /
# soc_kwh / solar_used_kw / solar_curtailed_kw / unmet_flex_kw) that
# src/schemas/plans.py, src/services/comparison_service.py and src/services/savings_service.py
# all already assume. The optimizer itself uses a simpler shape (signed battery_kw, soc_pct) —
# this is the one place that difference is reconciled.
# ---------------------------------------------------------------------------


def decision_to_series_item(
    decision: DispatchDecision,
    *,
    battery_capacity_kwh: float,
    forecast_solar_kw: float | None,
    executed: bool,
) -> dict[str, Any]:
    """Convert one optimizer `DispatchDecision` into the persisted/served plan-series shape."""
    batt_charge_kw = max(0.0, decision.battery_kw)
    batt_discharge_kw = max(0.0, -decision.battery_kw)
    soc_kwh = (decision.soc_pct / 100.0) * battery_capacity_kwh
    solar_curtailed_kw = 0.0
    if forecast_solar_kw is not None:
        solar_curtailed_kw = max(0.0, forecast_solar_kw - decision.solar_kw)
    badges = list(decision.badges)
    if executed:
        # Hour 0, once actually run, is no longer just a forecast of what will happen.
        badges = [b for b in badges if b != "FORECAST"] or ["SIMULATED"]
    return {
        "hour": decision.hour,
        "diesel_on": decision.diesel_on,
        "diesel_kw": decision.diesel_kw,
        "batt_charge_kw": batt_charge_kw,
        "batt_discharge_kw": batt_discharge_kw,
        "soc_kwh": soc_kwh,
        "solar_used_kw": decision.solar_kw,
        "solar_curtailed_kw": solar_curtailed_kw,
        # Not separately exposed by DispatchDecision (folded into load_kw upstream) —
        # 0.0 is the honest default rather than a guess; see PHASE_2 follow-ups.
        "unmet_flex_kw": 0.0,
        "executed": executed,
        "badges": badges,
        "reason": decision.reason,
    }


def _forecast_series_json(forecast: Forecast) -> list[dict[str, Any]]:
    entries = []
    for hour, (solar, load) in enumerate(zip(forecast.solar_kw, forecast.load_kw)):
        entry: dict[str, Any] = {"hour": hour, "solar_kw": solar, "load_kw": load}
        if forecast.solar_p10_kw:
            entry["solar_p10_kw"] = forecast.solar_p10_kw[hour]
        if forecast.solar_p90_kw:
            entry["solar_p90_kw"] = forecast.solar_p90_kw[hour]
        entries.append(entry)
    return entries


def _aware_utc(value: datetime) -> datetime:
    """Treat a naive datetime as UTC rather than letting the DB driver guess.

    `OpenMeteoForecastAdapter.fetch_forecast()` currently returns `fetched_at` from
    `datetime.now()` (naive) — worth fixing at the source, but this module defends
    against it rather than silently assuming every caller has done so.
    """
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _normalize_solver_status(raw: str) -> str:
    """`"appsi_highs:optimal"` -> `"optimal"`; `"fallback:greedy_baseline"` -> `"feasible"`."""
    lowered = raw.lower()
    if "optimal" in lowered:
        return "optimal"
    if "infeasible" in lowered:
        return "infeasible"
    if "timeout" in lowered:
        return "timeout"
    return "feasible"


def _ensure_site_row(session: Session, site_id: str, config: dict[str, Any]) -> int:
    """Insert the site row (and version-1 config history) if it doesn't exist yet.

    Returns the site's current `config_version`. A site that already exists is left alone —
    this only seeds a fresh database, it never overwrites a config someone has since changed.
    """
    row = session.get(SiteORM, site_id)
    if row is not None:
        return row.config_version
    row = SiteORM(
        id=site_id,
        name=site_id,
        timezone=config.get("timezone", "UTC"),
        config_version=1,
        config=config,
    )
    session.add(row)
    session.flush()
    return 1


# ---------------------------------------------------------------------------
# Sync repository adapters — implement optimizer/domain/ports.py against Postgres.
# ---------------------------------------------------------------------------


@dataclass
class PostgresPlanRepository(PlanRepository):
    session: Session
    site_id: str
    config_version: int
    forecast_db_id: int | None
    battery_capacity_kwh: float
    forecast: Forecast
    last_plan_db_id: int | None = field(default=None, init=False)

    def save(self, plan: DispatchPlan) -> None:
        series = [
            decision_to_series_item(
                decision,
                battery_capacity_kwh=self.battery_capacity_kwh,
                forecast_solar_kw=(
                    self.forecast.solar_kw[decision.hour]
                    if decision.hour < len(self.forecast.solar_kw)
                    else None
                ),
                executed=(decision.hour == 0),
            )
            for decision in plan.decisions
        ]
        row = DispatchPlanORM(
            site_id=self.site_id,
            tick_at=plan.created_at,
            forecast_id=self.forecast_db_id,
            config_version=self.config_version,
            starting_soc_kwh=(series[0]["soc_kwh"] if series else 0.0),
            series=series,
            objective_cost=0.0,
            solver_status=_normalize_solver_status(plan.solver_status),
            solve_ms=int(plan.solve_time_ms),
            source="fallback" if plan.fallback_used else "milp",
        )
        self.session.add(row)
        self.session.flush()
        self.last_plan_db_id = row.id

    def latest(self, site_id: str) -> DispatchPlan | None:
        # Not on RollingHorizonService.tick()'s call path; kept for Protocol conformance.
        return None


@dataclass
class PostgresTelemetryRepository(TelemetryRepository):
    session: Session
    site_id: str
    config_version: int
    battery_capacity_kwh: float

    def record(self, reading: dict[str, Any]) -> None:
        soc_kwh = (float(reading["soc_pct"]) / 100.0) * self.battery_capacity_kwh
        row = Telemetry(
            site_id=self.site_id,
            at=datetime.fromisoformat(reading["recorded_at"]),
            soc_kwh=soc_kwh,
            diesel_on=bool(reading["diesel_on"]),
            diesel_kw=float(reading["diesel_kw"]),
            batt_kw=float(reading["battery_kw"]),
            solar_kw=float(reading["solar_kw"]),
            load_kw=float(reading["load_kw"]),
            source=str(reading["source"]),
            config_version=self.config_version,
        )
        self.session.add(row)
        self.session.flush()

    def latest_soc(self, site_id: str) -> float | None:
        """Return SoC in **percent** — what RollingHorizonService.tick() expects back.

        The stored column is soc_kwh; the optimizer's own unit is percent, so this is the
        one place that conversion happens on the read side (ARCHITECTURE.md §4: this is the
        *only* legal source of a tick's starting state).
        """
        stmt = (
            select(Telemetry.soc_kwh)
            .where(Telemetry.site_id == site_id)
            .order_by(Telemetry.at.desc())
            .limit(1)
        )
        soc_kwh = self.session.execute(stmt).scalar_one_or_none()
        if soc_kwh is None:
            return None
        return (soc_kwh / self.battery_capacity_kwh) * 100.0


@dataclass
class PostgresExecutionRepository(ExecutionRepository):
    session: Session
    telemetry_repository: PostgresTelemetryRepository
    plan_repository: PostgresPlanRepository

    def record_execution(
        self, plan: DispatchPlan, decision: DispatchDecision, actual: ActualState
    ) -> None:
        telemetry = actual.to_telemetry()
        self.telemetry_repository.record(telemetry)
        if self.plan_repository.last_plan_db_id is not None:
            log_row = DispatchLog(
                plan_id=self.plan_repository.last_plan_db_id,
                hour_index=decision.hour,
                executed_at=actual.recorded_at,
                decision=decision_to_series_item(
                    decision,
                    battery_capacity_kwh=self.telemetry_repository.battery_capacity_kwh,
                    forecast_solar_kw=None,
                    executed=True,
                ),
            )
            self.session.add(log_row)
            self.session.flush()


@dataclass
class PostgresAlertSink(AlertPort):
    session: Session
    site_id: str

    def emit(self, alert_type: str, subject: str, payload: dict[str, Any] | None = None) -> None:
        try:
            typed = AlertType(alert_type)
        except ValueError:
            # The DB's alert_type enum and packages/contracts/events/alert.schema.json have
            # drifted apart (see docs/agent/mistakes.md follow-up) — skip rather than crash
            # a rolling tick over a naming mismatch that isn't this module's to fix.
            return
        existing = self.session.execute(
            select(Alert)
            .where(Alert.site_id == self.site_id)
            .where(Alert.type == typed)
            .where(Alert.subject == self.site_id)
            .where(Alert.state != AlertState.RESOLVED)
            .limit(1)
        ).scalar_one_or_none()
        if existing is not None:
            return  # already open — the partial unique index says one is enough
        now = datetime.now(timezone.utc)
        row = Alert(
            id=f"alr_{uuid.uuid4().hex[:12]}",
            site_id=self.site_id,
            type=typed,
            subject=self.site_id,
            state=AlertState.CREATED,
            title=subject,
            raised_at=now,
            received_at=now,
            provenance=payload or {},
        )
        self.session.add(row)
        self.session.flush()


def _persist_baseline(
    session: Session,
    site_id: str,
    config_version: int,
    battery_capacity_kwh: float,
    baseline_decision: DispatchDecision,
    at: datetime,
) -> None:
    """Populate the shadow ledger (DATA_MODEL.md §3) so /api/savings has something to compare."""
    soc_kwh = (baseline_decision.soc_pct / 100.0) * battery_capacity_kwh
    session.add(
        BaselineTelemetry(
            site_id=site_id,
            at=at,
            soc_kwh=soc_kwh,
            diesel_on=baseline_decision.diesel_on,
            diesel_kw=baseline_decision.diesel_kw,
            batt_kw=baseline_decision.battery_kw,
            solar_kw=baseline_decision.solar_kw,
            load_kw=baseline_decision.load_kw,
            source="baseline",
            config_version=config_version,
        )
    )
    session.flush()


def run_tick_sync(site_id: str) -> dict[str, Any]:
    """Run one full rolling-horizon tick for `site_id` against the real database.

    Synchronous end to end by design — see this module's docstring. Called from the async
    scheduler via `run_in_executor` (backend/src/main.py), never awaited directly.
    """
    yaml_path = SITE_CONFIG_PATHS.get(site_id)
    if yaml_path is None:
        raise ValueError(f"no site configuration registered for site_id={site_id!r}")

    site: Site = load_site_from_yaml(str(yaml_path))
    with open(yaml_path, "r") as f:
        raw_config = yaml.safe_load(f)

    settings = get_settings()
    session_factory = _sync_session_factory()

    with session_factory() as session:
        config_version = _ensure_site_row(session, site_id, raw_config)

        forecast_port = OpenMeteoForecastAdapter()
        forecast: Forecast = forecast_port.fetch_forecast(site)

        forecast_row = ForecastORM(
            site_id=site_id,
            issued_at=_aware_utc(forecast.fetched_at),
            horizon_hours=len(forecast.solar_kw),
            source=forecast.source,
            stale=forecast.stale,
            series=_forecast_series_json(forecast),
        )
        session.add(forecast_row)
        session.flush()

        telemetry_repo = PostgresTelemetryRepository(
            session=session,
            site_id=site_id,
            config_version=config_version,
            battery_capacity_kwh=site.battery.capacity_kwh,
        )
        plan_repo = PostgresPlanRepository(
            session=session,
            site_id=site_id,
            config_version=config_version,
            forecast_db_id=forecast_row.id,
            battery_capacity_kwh=site.battery.capacity_kwh,
            forecast=forecast,
        )
        execution_repo = PostgresExecutionRepository(
            session=session, telemetry_repository=telemetry_repo, plan_repository=plan_repo
        )
        alert_sink = PostgresAlertSink(session=session, site_id=site_id)

        service = RollingHorizonService(
            site=site,
            forecast_port=forecast_port,
            optimizer_port=PyomoHighsOptimizerAdapter(),
            dispatch_port=SimulatorDispatchAdapter(),
            plan_repository=plan_repo,
            telemetry_repository=telemetry_repo,
            execution_repository=execution_repo,
            alert_port=alert_sink,
            solve_timeout_seconds=settings.solve_timeout_seconds,
        )
        result = service.tick(provided_forecast=forecast)

        _persist_baseline(
            session,
            site_id,
            config_version,
            site.battery.capacity_kwh,
            result["baseline_decision"],
            at=datetime.fromisoformat(result["telemetry"]["recorded_at"]),
        )

        session.commit()

    return {
        "site_id": site_id,
        "fallback_used": result["fallback_used"],
        "starting_soc_pct": result["starting_soc_pct"],
        "plan_id": plan_repo.last_plan_db_id,
        "recorded_at": result["telemetry"]["recorded_at"],
    }


_logger = logging.getLogger("gridpilot.scheduler")


async def scheduled_tick(site_id: str) -> dict[str, Any] | None:
    """Async entry point APScheduler calls — `RollingScheduler` only ever awaits a coroutine
    or calls a sync function inline (`backend/src/scheduler/tick.py`); since `run_tick_sync`
    blocks on HTTP and the MILP solve, it must never run directly on the event loop.

    Also the manual-trigger path (`POST /api/tick`) calls straight through this, so a
    button-triggered tick and a scheduled one publish realtime events identically.

    Publishing happens *here*, back on the event loop, not inside `run_tick_sync` — that
    function runs in a worker thread via `run_in_executor`, and `asyncio.Queue` (which the
    broadcaster is built on) is not thread-safe to touch from anywhere else.
    """
    loop = asyncio.get_running_loop()
    try:
        summary = await loop.run_in_executor(None, run_tick_sync, site_id)
        _logger.info("tick complete site_id=%s fallback_used=%s", site_id, summary["fallback_used"])
        now = datetime.now(timezone.utc)
        broadcaster.publish(
            RealtimeEvent(
                type=RealtimeEventType.PLAN_UPDATED,
                site_id=site_id,
                subject=str(summary.get("plan_id") or site_id),
                timestamp=now,
                payload={"fallback_used": summary["fallback_used"]},
            )
        )
        broadcaster.publish(
            RealtimeEvent(
                type=RealtimeEventType.TELEMETRY_UPDATED,
                site_id=site_id,
                subject=site_id,
                timestamp=now,
                payload={"soc_pct": summary["starting_soc_pct"]},
            )
        )
        return summary
    except Exception:
        _logger.exception("rolling-horizon tick failed for site_id=%s", site_id)
        return None
