"""Pure planned-versus-actual dispatch comparison logic."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta

from src.repositories.protocols import DispatchPlanRecord, JsonObject
from src.schemas.comparison import DispatchPlanComparison, HourlyDispatchComparison
from src.schemas.telemetry import TelemetryPoint


class DispatchComparisonError(ValueError):
    """Raised when a dispatch plan and telemetry cannot be compared unambiguously."""


def compare_plan_to_telemetry(
    plan: DispatchPlanRecord, actual_points: Sequence[TelemetryPoint]
) -> DispatchPlanComparison:
    """Compare every plan hour with an exact same-site telemetry timestamp.

    A plan series item at hour ``n`` is expected to match telemetry at
    ``plan.tick_at + n hours``. Both sets must match exactly; this prevents partial
    data or unrelated telemetry from being presented as a comparison.
    """

    actual_by_time = _index_actual_points(plan.site_id, actual_points)
    planned_by_time = _index_plan_hours(plan)

    if planned_by_time.keys() != actual_by_time.keys():
        raise DispatchComparisonError(
            "plan hours and actual telemetry must have matching timestamps"
        )

    comparisons = [
        _compare_hour(hour, at, decision, actual_by_time[at])
        for at, (hour, decision) in sorted(planned_by_time.items(), key=lambda item: item[1][0])
    ]
    return DispatchPlanComparison(plan_id=plan.id, site_id=plan.site_id, hours=comparisons)


def _index_actual_points(
    site_id: str, points: Sequence[TelemetryPoint]
) -> dict[datetime, TelemetryPoint]:
    indexed: dict[datetime, TelemetryPoint] = {}
    for point in points:
        if point.site_id != site_id:
            raise DispatchComparisonError("plan and actual telemetry must have the same site_id")
        if point.at in indexed:
            raise DispatchComparisonError("actual telemetry contains duplicate timestamps")
        indexed[point.at] = point
    return indexed


def _index_plan_hours(plan: DispatchPlanRecord) -> dict[datetime, tuple[int, JsonObject]]:
    indexed: dict[datetime, tuple[int, JsonObject]] = {}
    for decision in plan.series:
        hour = _required_hour(decision)
        at = plan.tick_at + timedelta(hours=hour)
        if at in indexed:
            raise DispatchComparisonError("dispatch plan contains duplicate hour values")
        indexed[at] = (hour, decision)
    return indexed


def _compare_hour(
    hour: int,
    at: datetime,
    decision: JsonObject,
    actual: TelemetryPoint,
) -> HourlyDispatchComparison:
    return HourlyDispatchComparison(
        hour=hour,
        at=at,
        planned_diesel_kw=_required_non_negative_number(decision, "diesel_kw"),
        actual_diesel_kw=actual.diesel_kw,
        planned_batt_charge_kw=_required_non_negative_number(decision, "batt_charge_kw"),
        planned_batt_discharge_kw=_required_non_negative_number(decision, "batt_discharge_kw"),
        actual_batt_kw=actual.batt_kw,
        planned_solar_used_kw=_required_non_negative_number(decision, "solar_used_kw"),
        actual_solar_kw=actual.solar_kw,
        planned_unmet_flex_kw=_required_non_negative_number(decision, "unmet_flex_kw"),
        actual_load_kw=actual.load_kw,
    )


def _required_hour(decision: JsonObject) -> int:
    value = decision.get("hour")
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise DispatchComparisonError("dispatch plan hour must be a non-negative integer")
    return value


def _required_non_negative_number(decision: JsonObject, field_name: str) -> float:
    value = decision.get(field_name)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        raise DispatchComparisonError(
            f"dispatch plan field '{field_name}' must be a non-negative number"
        )
    return float(value)
