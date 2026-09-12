"""Tests for pure Phase 3 planned-versus-actual dispatch comparison."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from src.repositories.protocols import (
    DispatchPlanRecord,
    DispatchPlanSource,
    DispatchSolverStatus,
)
from src.schemas.telemetry import TelemetryPoint, TelemetrySource
from src.services.comparison_service import DispatchComparisonError, compare_plan_to_telemetry


def decision(hour: int, *, diesel_kw: float = 0.0) -> dict[str, int | float]:
    return {
        "hour": hour,
        "diesel_kw": diesel_kw,
        "batt_charge_kw": 1.0,
        "batt_discharge_kw": 0.0,
        "solar_used_kw": 4.0,
        "unmet_flex_kw": 0.0,
    }


def plan(*, series: list[dict[str, int | float]], site_id: str = "site-a") -> DispatchPlanRecord:
    return DispatchPlanRecord(
        id=1,
        site_id=site_id,
        tick_at=datetime(2026, 1, 1, tzinfo=UTC),
        forecast_id=1,
        config_version=1,
        starting_soc_kwh=20.0,
        series=series,
        objective_cost=10.0,
        solver_status=DispatchSolverStatus.OPTIMAL,
        solve_ms=100,
        source=DispatchPlanSource.MILP,
    )


def actual(
    *,
    point_id: str,
    at: datetime,
    site_id: str = "site-a",
    diesel_kw: float = 0.0,
) -> TelemetryPoint:
    return TelemetryPoint(
        id=point_id,
        site_id=site_id,
        at=at,
        soc_kwh=20.0,
        diesel_on=diesel_kw > 0,
        diesel_kw=diesel_kw,
        batt_kw=1.0,
        solar_kw=4.0,
        load_kw=4.0,
        source=TelemetrySource.SIMULATOR,
        config_version=1,
    )


def test_exact_matching_plan_and_telemetry_are_compared() -> None:
    dispatch_plan = plan(series=[decision(0, diesel_kw=2.0)])
    result = compare_plan_to_telemetry(
        dispatch_plan,
        [actual(point_id="tel-1", at=dispatch_plan.tick_at, diesel_kw=2.0)],
    )

    assert result.plan_id == 1
    assert result.site_id == "site-a"
    assert result.hours[0].planned_diesel_kw == 2.0
    assert result.hours[0].actual_diesel_kw == 2.0
    assert result.hours[0].planned_batt_charge_kw == 1.0
    assert result.hours[0].actual_batt_kw == 1.0
    assert result.hours[0].planned_solar_used_kw == 4.0
    assert result.hours[0].actual_solar_kw == 4.0
    assert result.hours[0].planned_unmet_flex_kw == 0.0
    assert result.hours[0].actual_load_kw == 4.0


def test_multiple_hours_are_matched_by_plan_timestamp_and_hour() -> None:
    dispatch_plan = plan(series=[decision(0), decision(1, diesel_kw=3.0)])
    result = compare_plan_to_telemetry(
        dispatch_plan,
        [
            actual(point_id="tel-2", at=dispatch_plan.tick_at + timedelta(hours=1), diesel_kw=2.0),
            actual(point_id="tel-1", at=dispatch_plan.tick_at),
        ],
    )

    assert [hour.hour for hour in result.hours] == [0, 1]
    assert [hour.actual_diesel_kw for hour in result.hours] == [0.0, 2.0]


def test_missing_telemetry_counterpart_is_rejected() -> None:
    dispatch_plan = plan(series=[decision(0), decision(1)])

    with pytest.raises(DispatchComparisonError, match="matching timestamps"):
        compare_plan_to_telemetry(
            dispatch_plan,
            [actual(point_id="tel-1", at=dispatch_plan.tick_at)],
        )


def test_mismatched_site_is_rejected() -> None:
    dispatch_plan = plan(series=[decision(0)])

    with pytest.raises(DispatchComparisonError, match="same site_id"):
        compare_plan_to_telemetry(
            dispatch_plan,
            [actual(point_id="tel-1", at=dispatch_plan.tick_at, site_id="site-b")],
        )


def test_duplicate_actual_timestamps_are_rejected() -> None:
    dispatch_plan = plan(series=[decision(0)])
    point_at = dispatch_plan.tick_at

    with pytest.raises(DispatchComparisonError, match="duplicate timestamps"):
        compare_plan_to_telemetry(
            dispatch_plan,
            [
                actual(point_id="tel-1", at=point_at),
                actual(point_id="tel-2", at=point_at),
            ],
        )


def test_comparison_does_not_mutate_plan_or_actual_inputs() -> None:
    dispatch_plan = plan(series=[decision(0)])
    actual_points = [actual(point_id="tel-1", at=dispatch_plan.tick_at)]
    series_before = [item.copy() for item in dispatch_plan.series]
    actual_before = [point.model_dump() for point in actual_points]

    compare_plan_to_telemetry(dispatch_plan, actual_points)

    assert dispatch_plan.series == series_before
    assert [point.model_dump() for point in actual_points] == actual_before
