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
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

# --- make the sibling `optimizer/` package importable regardless of how uvicorn was launched ---
_candidate_roots = Path(__file__).resolve().parents
_REPO_ROOT = next(
    (root for root in _candidate_roots if (root / "optimizer").is_dir()),
    Path(__file__).resolve().parents[2],
)
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

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

from src.alerts import rules as alert_rules
from src.config.settings import get_settings
from src.db.models.alerts import Alert, AlertState, AlertType
from src.db.models.baseline import BaselineDispatchLog, BaselineTelemetry
from src.db.models.dispatch_log import DispatchLog
from src.db.models.dispatch_plans import DispatchPlan as DispatchPlanORM
from src.db.models.forecasts import Forecast as ForecastORM
from src.db.models.sites import Site as SiteORM
from src.db.models.telemetry import Telemetry
from src.realtime.broadcaster import RealtimeEvent, RealtimeEventType, broadcaster
from src.schemas.alerts import AlertType as ContractAlertType

# One site for now — a slug -> YAML path table, extended by adding a line, not a code change
SITE_CONFIG_PATHS: dict[str, Path] = {
    "Dharavi Microgrid": _REPO_ROOT / "optimizer" / "sites" / "example-site.yml",
}

_sync_engine = None
_SyncSessionFactory: sessionmaker | None = None
_ALERT_COOLDOWN = timedelta(seconds=60)


def _sync_session_factory() -> sessionmaker:
    """Lazily build a sync engine/sessionmaker against the same database as the async one."""
    global _sync_engine, _SyncSessionFactory
    if _SyncSessionFactory is None:
        settings = get_settings()
        _sync_engine = create_engine(settings.database_url_sync, future=True)
        _SyncSessionFactory = sessionmaker(bind=_sync_engine, future=True, expire_on_commit=False)
    return _SyncSessionFactory


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
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _normalize_solver_status(raw: str) -> str:
    lowered = raw.lower()
    if "optimal" in lowered:
        return "optimal"
    if "infeasible" in lowered:
        return "infeasible"
    if "timeout" in lowered:
        return "timeout"
    return "feasible"


def _ensure_site_row(session: Session, site_id: str, config: dict[str, Any]) -> int:
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

    def latest_diesel_on(self, site_id: str) -> bool | None:
        stmt = (
            select(Telemetry.diesel_on)
            .where(Telemetry.site_id == site_id)
            .order_by(Telemetry.at.desc())
            .limit(1)
        )
        value = self.session.execute(stmt).scalar_one_or_none()
        return None if value is None else bool(value)


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
    created_alert_ids: list[str] = field(default_factory=list)

    def emit(self, alert_type: str, subject: str, payload: dict[str, Any] | None = None) -> None:
        try:
            typed = AlertType(alert_type)
        except ValueError:
            return
        now = datetime.now(timezone.utc)
        existing = self.session.execute(
            select(Alert)
            .where(Alert.site_id == self.site_id)
            .where(Alert.type == typed)
            .where(Alert.subject == subject)
            .where(Alert.state != AlertState.RESOLVED)
            .limit(1)
        ).scalar_one_or_none()
        if existing is not None:
            return

        recent_resolved = self.session.execute(
            select(Alert)
            .where(Alert.site_id == self.site_id)
            .where(Alert.type == typed)
            .where(Alert.subject == subject)
            .where(Alert.state == AlertState.RESOLVED)
            .order_by(Alert.resolved_at.desc())
            .limit(1)
        ).scalar_one_or_none()
        if (
            recent_resolved is not None
            and recent_resolved.resolved_at is not None
            and _aware_utc(recent_resolved.resolved_at) + _ALERT_COOLDOWN > now
        ):
            return

        alert_id = f"alr_{uuid.uuid4().hex[:12]}"
        title = str((payload or {}).get("title") or subject)
        if len(title) > 160:
            title = title[:157] + "..."
        row = Alert(
            id=alert_id,
            site_id=self.site_id,
            type=typed,
            subject=subject,
            state=AlertState.CREATED,
            title=title,
            raised_at=now,
            received_at=now,
            provenance=payload or {"badges": ["SIMULATED"]},
        )
        self.session.add(row)
        self.session.flush()
        self.created_alert_ids.append(alert_id)


def _persist_baseline(
    session: Session,
    *,
    site_id: str,
    config_version: int,
    battery_capacity_kwh: float,
    baseline_decision: DispatchDecision,
    at: datetime,
    plan_id: int | None,
    realized_solar_kw: float,
    realized_load_kw: float,
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
            # Store the identical realized conditions the baseline decided against.
            solar_kw=realized_solar_kw,
            load_kw=realized_load_kw,
            source="baseline",
            config_version=config_version,
        )
    )
    if plan_id is not None:
        session.add(
            BaselineDispatchLog(
                plan_id=plan_id,
                hour_index=0,
                executed_at=at,
                decision=decision_to_series_item(
                    baseline_decision,
                    battery_capacity_kwh=battery_capacity_kwh,
                    forecast_solar_kw=realized_solar_kw,
                    executed=True,
                ),
            )
        )
    session.flush()


def _raise_tick_alerts(
    *,
    alert_sink: PostgresAlertSink,
    site: Site,
    site_id: str,
    forecast: Forecast,
    plan: DispatchPlan,
    actual: ActualState,
    baseline_decision: DispatchDecision,
    fallback_used: bool,
) -> None:
    """Evaluate Phase 3 alert rules against the just-completed tick and persist via AlertPort."""
    raised_at = actual.recorded_at
    soc_kwh = (actual.soc_pct / 100.0) * site.battery.capacity_kwh
    reserve_kwh = site.battery.capacity_kwh * (site.battery.soc_min_pct / 100.0)
    hours_until_diesel = next(
        (decision.hour for decision in plan.decisions if decision.diesel_on),
        24,
    )

    candidates = [
        alert_rules.low_soc_reserve(
            site_id=site_id,
            soc_kwh=soc_kwh,
            minimum_reserve_kwh=reserve_kwh,
            raised_at=raised_at,
        ),
        alert_rules.solver_fallback_active(
            site_id=site_id,
            fallback_active=fallback_used,
            raised_at=raised_at,
        ),
        alert_rules.forecast_stale(
            site_id=site_id,
            forecast_age_minutes=(
                (datetime.now(timezone.utc) - _aware_utc(forecast.fetched_at)).total_seconds()
                / 60.0
            ),
            maximum_age_minutes=90.0,
            raised_at=raised_at,
        ),
        alert_rules.critical_load_at_risk(
            site_id=site_id,
            critical_load_kw=site.load.critical_kw[0] if site.load.critical_kw else 0.0,
            available_supply_kw=actual.solar_kw
            + max(0.0, -actual.battery_kw)
            + actual.diesel_kw,
            minimum_margin_kw=0.0,
            raised_at=raised_at,
        ),
        alert_rules.diesel_required_soon(
            site_id=site_id,
            hours_until_required=float(hours_until_diesel),
            threshold_hours=2.0,
            raised_at=raised_at,
        ),
        # Compare diesel kW as a same-unit proxy for cost asymmetry this tick.
        alert_rules.baseline_divergence(
            site_id=site_id,
            optimized_cost=float(actual.diesel_kw),
            baseline_cost=float(baseline_decision.diesel_kw),
            tolerance=0.01,
            raised_at=raised_at,
        ),
    ]

    for candidate in candidates:
        if candidate is None:
            continue
        if candidate.type.value not in {member.value for member in ContractAlertType}:
            continue
        alert_sink.emit(
            alert_type=candidate.type.value,
            subject=candidate.subject or site_id,
            payload={
                "title": candidate.title,
                "badges": [badge.value for badge in candidate.provenance],
                "raised_at": candidate.raised_at.isoformat(),
            },
        )


def run_tick_sync(site_id: str) -> dict[str, Any]:
    """Run one full rolling-horizon tick for `site_id` against the real database."""
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
        actual: ActualState = result["actual_state"]

        _persist_baseline(
            session,
            site_id=site_id,
            config_version=config_version,
            battery_capacity_kwh=site.battery.capacity_kwh,
            baseline_decision=result["baseline_decision"],
            at=actual.recorded_at,
            plan_id=plan_repo.last_plan_db_id,
            realized_solar_kw=actual.solar_kw,
            realized_load_kw=actual.load_kw,
        )

        _raise_tick_alerts(
            alert_sink=alert_sink,
            site=site,
            site_id=site_id,
            forecast=forecast,
            plan=result["plan"],
            actual=actual,
            baseline_decision=result["baseline_decision"],
            fallback_used=result["fallback_used"],
        )

        session.commit()

    return {
        "site_id": site_id,
        "fallback_used": result["fallback_used"],
        "starting_soc_pct": result["starting_soc_pct"],
        "plan_id": plan_repo.last_plan_db_id,
        "recorded_at": result["telemetry"]["recorded_at"],
        "alert_ids": list(alert_sink.created_alert_ids),
        "soc_pct": actual.soc_pct,
        "diesel_on": actual.diesel_on,
    }


_logger = logging.getLogger("gridpilot.scheduler")


async def scheduled_tick(site_id: str) -> dict[str, Any] | None:
    """Async entry point APScheduler calls — blocks off the event loop via executor."""
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
                payload={"fallback_used": summary["fallback_used"], "plan_id": summary.get("plan_id")},
            )
        )
        broadcaster.publish(
            RealtimeEvent(
                type=RealtimeEventType.TELEMETRY_UPDATED,
                site_id=site_id,
                subject=site_id,
                timestamp=now,
                payload={
                    "soc_pct": summary.get("soc_pct", summary["starting_soc_pct"]),
                    "diesel_on": summary.get("diesel_on"),
                },
            )
        )
        for alert_id in summary.get("alert_ids") or []:
            broadcaster.publish(
                RealtimeEvent(
                    type=RealtimeEventType.ALERT_CREATED,
                    site_id=site_id,
                    subject=alert_id,
                    timestamp=now,
                    payload={"alert_id": alert_id},
                )
            )
        return summary
    except Exception:
        _logger.exception("rolling-horizon tick failed for site_id=%s", site_id)
        return None
