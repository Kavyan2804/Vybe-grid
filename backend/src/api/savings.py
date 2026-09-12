"""Read-only savings comparison API."""

from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.repositories.baseline import BaselineTelemetryRepository as PgBaselineRepository
from src.db.repositories.dispatch_plans import DispatchPlanRepository as PgPlanRepository
from src.db.repositories.sites import SiteRepository
from src.db.repositories.telemetry import TelemetryRepository as PgTelemetryRepository
from src.db.session import get_db_session
from src.openapi import OPENAPI_ERROR_RESPONSES
from src.repositories.protocols import DispatchPlanRecord, DispatchPlanSource, DispatchSolverStatus
from src.schemas.comparison import DispatchPlanComparison
from src.schemas.savings import SavingsDeltaMetrics, SavingsMetrics
from src.schemas.telemetry import TelemetryPoint, TelemetrySource
from src.services.comparison_service import DispatchComparisonError, compare_plan_to_telemetry
from src.services.savings_facade import SavingsFacade  # re-exported for tests/back-compat
from src.services.savings_service import FuelConversion, SavingsCalculationError, calculate_savings

router = APIRouter(tags=["savings"])


class SavingsResponse(BaseModel):
    """Typed read-only comparison response for one site and time range."""

    model_config = ConfigDict(extra="forbid")

    comparison: DispatchPlanComparison
    optimized: SavingsMetrics
    baseline: SavingsMetrics
    saved: SavingsDeltaMetrics


# Kept for tests/callers that configure a facade directly; the real endpoint below no longer
# depends on it being set (see _materialize_savings_inputs).
_configured_facade: SavingsFacade | None = None


class _MaterializedSavingsInputs:
    """One request's DB rows, converted into the shapes `comparison_service` and
    `savings_service` already know how to compare (both pure, synchronous, no I/O)."""

    def __init__(
        self,
        conversion: FuelConversion,
        plan: DispatchPlanRecord | None,
        optimized_points: list[TelemetryPoint],
        baseline_points: list[TelemetryPoint],
        comparison_optimized_points: list[TelemetryPoint],
    ) -> None:
        self.conversion = conversion
        self.plan = plan
        self.optimized_points = optimized_points
        self.baseline_points = baseline_points
        self.comparison_optimized_points = comparison_optimized_points


def _telemetry_point(row, point_id: str, force_source: TelemetrySource | None) -> TelemetryPoint:
    if force_source is not None:
        source = force_source
    else:
        try:
            source = TelemetrySource(row.source)
        except ValueError:
            source = TelemetrySource.SIMULATOR
    return TelemetryPoint(
        id=point_id,
        site_id=row.site_id,
        at=row.at,
        soc_kwh=row.soc_kwh,
        diesel_on=row.diesel_on,
        diesel_kw=row.diesel_kw,
        batt_kw=row.batt_kw,
        solar_kw=row.solar_kw,
        load_kw=row.load_kw,
        source=source,
        config_version=row.config_version,
    )


async def _materialize_savings_inputs(
    session: AsyncSession, site_id: str, start_at: datetime, end_at: datetime
) -> _MaterializedSavingsInputs:
    """Read the real DB repositories once and convert the rows into the plain dataclasses
    `comparison_service.compare_plan_to_telemetry` and `savings_service.calculate_savings`
    already accept.
    """
    site_repo = SiteRepository(session)
    plan_repo = PgPlanRepository(session)
    telemetry_repo = PgTelemetryRepository(session)
    baseline_repo = PgBaselineRepository(session)

    site_row = await site_repo.get_by_id(site_id)
    fuel_l_per_kwh = 1.0
    fuel_price = 0.0
    co2_per_litre = 0.0
    if site_row is not None and site_row.config:
        diesel_cfg = site_row.config.get("diesel_generator", {})
        fuel_l_per_kwh = float(diesel_cfg.get("fuel_curve", {}).get("litres_per_kwh_max_load", 1.0))
        fuel_price = float(site_row.config.get("fuel_cost_per_litre", 0.0))
        co2_per_litre = float(site_row.config.get("emission_factor_kg_co2_per_litre", 0.0))
    conversion = FuelConversion(
        fuel_litres_per_kwh=fuel_l_per_kwh,
        fuel_cost_per_litre=fuel_price,
        co2_kg_per_litre=co2_per_litre,
    )

    optimized_rows = await telemetry_repo.list_for_site(site_id, start_time=start_at, end_time=end_at, limit=2000)
    baseline_rows = await baseline_repo.list_for_site(site_id, start_time=start_at, end_time=end_at, limit=2000)

    optimized_points = [_telemetry_point(row, f"t{row.id}", None) for row in optimized_rows]
    baseline_points = [_telemetry_point(row, f"b{row.id}", TelemetrySource.BASELINE) for row in baseline_rows]

    # `comparison_service.compare_plan_to_telemetry` expects one plan whose *entire* series was
    # executed (`plan.tick_at + hour` matching a telemetry row for every hour, exactly). That
    # isn't what actually happens: a new plan is produced every tick and only its hour 0 is ever
    # executed (ARCHITECTURE.md §3 step 8) — hours 1-23 are discarded and superseded next tick.
    # So the comparable unit isn't "one plan's 24 hours", it's "every plan's hour 0" over the
    # requested range, each landing a few milliseconds after its own plan's tick_at (solve +
    # persist + dispatch time). This reconstructs a synthetic plan on a clean integer-hour grid,
    # one entry per real plan, and snaps a *copy* of each paired telemetry point's timestamp onto
    # that same grid — for this hour-by-hour display comparison only. `calculate_savings` below
    # never sees the snapped copies; it compares optimized_points/baseline_points as recorded,
    # which already share an exact timestamp by construction (optimizer_bridge.py's
    # `_persist_baseline` stamps the baseline row with the optimized tick's own recorded_at).
    plan_rows = await plan_repo.list_for_site(site_id, start_time=start_at, end_time=end_at, limit=500)
    plan_record: DispatchPlanRecord | None = None
    comparison_optimized_points: list[TelemetryPoint] = []
    if plan_rows:
        reference_tick_at = plan_rows[0].tick_at
        synthetic_series = []
        # Positional pairing: exactly one telemetry row is recorded per tick
        # (PostgresExecutionRepository.record_execution), so plan_rows[i] <-> optimized_points[i]
        # for as many pairs as both lists actually have.
        for i, plan_row in enumerate(plan_rows):
            hour_zero = next((item for item in plan_row.series if item.get("hour") == 0), None)
            if hour_zero is None or i >= len(optimized_points):
                continue
            offset_hours = round((plan_row.tick_at - reference_tick_at).total_seconds() / 3600)
            synthetic_series.append({**hour_zero, "hour": offset_hours})
            snapped_at = reference_tick_at + timedelta(hours=offset_hours)
            comparison_optimized_points.append(optimized_points[i].model_copy(update={"at": snapped_at}))
        latest_row = plan_rows[-1]
        plan_record = DispatchPlanRecord(
            id=latest_row.id,
            site_id=latest_row.site_id,
            tick_at=reference_tick_at,
            forecast_id=latest_row.forecast_id or 0,
            config_version=latest_row.config_version,
            starting_soc_kwh=plan_rows[0].starting_soc_kwh,
            series=synthetic_series,
            objective_cost=latest_row.objective_cost or 0.0,
            solver_status=DispatchSolverStatus(latest_row.solver_status),
            solve_ms=latest_row.solve_ms or 0,
            source=DispatchPlanSource(latest_row.source),
        )

    return _MaterializedSavingsInputs(
        conversion=conversion,
        plan=plan_record,
        optimized_points=optimized_points,
        baseline_points=baseline_points,
        comparison_optimized_points=comparison_optimized_points,
    )


@router.get(
    "/savings",
    response_model=SavingsResponse,
    summary="Compare optimized and baseline savings",
    description=(
        "Return a read-only planned-versus-actual savings comparison for a timezone-aware "
        "half-open interval `[start_at, end_at)`. Optimized and baseline telemetry must both "
        "exist for the requested site and timestamps."
    ),
    response_description="The comparison and optimized, baseline, and signed saved metrics.",
    responses=OPENAPI_ERROR_RESPONSES,
)
async def get_savings(
    site_id: str = Query(..., min_length=1, description="Site identifier."),
    start_at: datetime = Query(..., description="Inclusive ISO-8601 timestamp with offset."),
    end_at: datetime = Query(..., description="Exclusive ISO-8601 timestamp with offset."),
    session: AsyncSession = Depends(get_db_session),
) -> SavingsResponse:
    """Calculate savings without persisting or mutating any ledger data.

    `comparison` and `saved` are computed independently rather than through
    `SavingsFacade.calculate()`'s single all-or-nothing call: a plan/telemetry alignment
    that can't be reconciled exactly should not block the number that actually matters
    (the measured diesel/cost/CO2 delta) — it should just leave `comparison.hours` empty.
    """
    field_errors: list[dict[str, object]] = []
    for field_name, value in (("start_at", start_at), ("end_at", end_at)):
        if value.tzinfo is None or value.utcoffset() is None:
            field_errors.append(
                {
                    "loc": ["query", field_name],
                    "msg": "Timestamp must include an explicit timezone offset.",
                    "type": "timezone_aware",
                }
            )
    if field_errors:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "validation_error",
                "message": "Request validation failed.",
                "field_errors": field_errors,
                "detail": {},
            },
        )
    if start_at >= end_at:
        raise HTTPException(
            status_code=400,
            detail={"error": "invalid_time_range", "message": "start_at must be earlier than end_at", "detail": {}},
        )

    inputs = await _materialize_savings_inputs(session, site_id, start_at, end_at)

    if not inputs.optimized_points or not inputs.baseline_points:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "telemetry_not_found",
                "message": "optimized and baseline telemetry are both required for the requested range",
                "detail": {},
            },
        )

    try:
        savings = calculate_savings(inputs.optimized_points, inputs.baseline_points, inputs.conversion)
    except SavingsCalculationError as exc:
        raise HTTPException(
            status_code=409,
            detail={"error": "savings_data_mismatch", "message": str(exc), "detail": {}},
        ) from exc

    comparison: DispatchPlanComparison
    if inputs.plan is not None and inputs.comparison_optimized_points:
        try:
            comparison = compare_plan_to_telemetry(inputs.plan, inputs.comparison_optimized_points)
        except DispatchComparisonError:
            comparison = DispatchPlanComparison(plan_id=inputs.plan.id, site_id=site_id, hours=[])
    else:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "dispatch_plan_not_found",
                "message": f"No dispatch plan was found for site '{site_id}' in the requested range",
                "detail": {},
            },
        )

    return SavingsResponse(
        comparison=comparison,
        optimized=savings.optimized,
        baseline=savings.baseline,
        saved=savings.saved,
    )
