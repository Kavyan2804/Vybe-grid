"""Tests for the Phase 3 savings application facade."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from src.repositories.in_memory import (
    InMemoryDispatchLogRepository,
    InMemoryDispatchPlanRepository,
    InMemoryTelemetryRepository,
)
from src.repositories.protocols import (
    DispatchPlanRecord,
    DispatchPlanSource,
    DispatchSolverStatus,
)
from src.schemas.telemetry import TelemetryPoint, TelemetrySource
from src.services.repository_dependencies import RepositoryDependencies
from src.services.savings_facade import SavingsFacade, SavingsFacadeError
from src.services.savings_service import FuelConversion


def plan(*, site_id: str = "site-a") -> DispatchPlanRecord:
    return DispatchPlanRecord(
        id=1,
        site_id=site_id,
        tick_at=datetime(2026, 1, 1, tzinfo=UTC),
        forecast_id=1,
        config_version=1,
        starting_soc_kwh=20.0,
        series=[
            {
                "hour": 0,
                "diesel_kw": 2.0,
                "batt_charge_kw": 1.0,
                "batt_discharge_kw": 0.0,
                "solar_used_kw": 4.0,
                "unmet_flex_kw": 0.0,
            }
        ],
        objective_cost=10.0,
        solver_status=DispatchSolverStatus.OPTIMAL,
        solve_ms=100,
        source=DispatchPlanSource.MILP,
    )


def telemetry(
    *,
    point_id: str,
    at: datetime,
    diesel_kw: float,
    site_id: str = "site-a",
    source: TelemetrySource = TelemetrySource.SIMULATOR,
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
        source=source,
        config_version=1,
    )


def dependencies() -> RepositoryDependencies:
    return RepositoryDependencies(
        telemetry_repository=InMemoryTelemetryRepository(),
        dispatch_plan_repository=InMemoryDispatchPlanRepository(),
        dispatch_log_repository=InMemoryDispatchLogRepository(),
    )


def facade(repository_dependencies: RepositoryDependencies) -> SavingsFacade:
    return SavingsFacade(
        repository_dependencies,
        FuelConversion(
            fuel_litres_per_kwh=0.25,
            fuel_cost_per_litre=100.0,
            co2_kg_per_litre=2.5,
        ),
    )


def append_complete_ledger(repository_dependencies: RepositoryDependencies) -> datetime:
    dispatch_plan = plan()
    repository_dependencies.dispatch_plan_repository.append(dispatch_plan)
    repository_dependencies.telemetry_repository.append(
        telemetry(point_id="opt-1", at=dispatch_plan.tick_at, diesel_kw=2.0)
    )
    repository_dependencies.telemetry_repository.append(
        telemetry(
            point_id="base-1",
            at=dispatch_plan.tick_at,
            diesel_kw=6.0,
            source=TelemetrySource.BASELINE,
        )
    )
    return dispatch_plan.tick_at


def test_successful_calculation_returns_comparison_and_metrics() -> None:
    repository_dependencies = dependencies()
    at = append_complete_ledger(repository_dependencies)

    result = facade(repository_dependencies).calculate(
        site_id="site-a", start_at=at, end_at=at + timedelta(hours=1)
    )

    assert result.comparison.hours[0].planned_diesel_kw == 2.0
    assert result.comparison.hours[0].actual_diesel_kw == 2.0
    assert result.optimized.diesel_energy_kwh == 2.0
    assert result.baseline.diesel_energy_kwh == 6.0
    assert result.saved.diesel_energy_kwh == 4.0


def test_missing_plan_is_rejected() -> None:
    at = datetime(2026, 1, 1, tzinfo=UTC)

    with pytest.raises(SavingsFacadeError, match="No dispatch plan"):
        facade(dependencies()).calculate(
            site_id="site-a", start_at=at, end_at=at + timedelta(hours=1)
        )


def test_missing_telemetry_is_rejected() -> None:
    repository_dependencies = dependencies()
    dispatch_plan = plan()
    repository_dependencies.dispatch_plan_repository.append(dispatch_plan)

    with pytest.raises(SavingsFacadeError, match="telemetry"):
        facade(repository_dependencies).calculate(
            site_id="site-a",
            start_at=dispatch_plan.tick_at,
            end_at=dispatch_plan.tick_at + timedelta(hours=1),
        )


def test_mismatched_plan_site_is_rejected() -> None:
    class MismatchedSitePlanRepository(InMemoryDispatchPlanRepository):
        def latest_for_site(self, *, site_id: str) -> DispatchPlanRecord | None:
            return super().latest_for_site(site_id="site-a")

    plan_repository = MismatchedSitePlanRepository()
    dispatch_plan = plan(site_id="site-a")
    plan_repository.append(dispatch_plan)
    repository_dependencies = RepositoryDependencies(
        telemetry_repository=InMemoryTelemetryRepository(),
        dispatch_plan_repository=plan_repository,
        dispatch_log_repository=InMemoryDispatchLogRepository(),
    )

    with pytest.raises(SavingsFacadeError, match="does not match"):
        facade(repository_dependencies).calculate(
            site_id="site-b",
            start_at=dispatch_plan.tick_at,
            end_at=dispatch_plan.tick_at + timedelta(hours=1),
        )


def test_optimized_and_baseline_telemetry_remain_separate() -> None:
    repository_dependencies = dependencies()
    at = append_complete_ledger(repository_dependencies)

    result = facade(repository_dependencies).calculate(
        site_id="site-a", start_at=at, end_at=at + timedelta(hours=1)
    )

    assert result.comparison.hours[0].actual_diesel_kw == 2.0
    assert result.optimized.diesel_energy_kwh == 2.0
    assert result.baseline.diesel_energy_kwh == 6.0
