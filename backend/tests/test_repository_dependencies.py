"""Tests for the Phase 3 repository dependency container."""

from __future__ import annotations

from datetime import UTC, datetime

from src.repositories.in_memory import (
    InMemoryDispatchLogRepository,
    InMemoryDispatchPlanRepository,
    InMemoryTelemetryRepository,
)
from src.repositories.protocols import (
    DispatchLogRecord,
    DispatchPlanRecord,
    DispatchPlanSource,
    DispatchSolverStatus,
    TelemetryRepository,
)
from src.schemas.telemetry import TelemetryPoint, TelemetrySource
from src.services.repository_dependencies import (
    RepositoryDependencies,
    create_in_memory_repository_dependencies,
)


def test_container_accepts_protocol_implementations() -> None:
    dependencies = RepositoryDependencies(
        telemetry_repository=InMemoryTelemetryRepository(),
        dispatch_plan_repository=InMemoryDispatchPlanRepository(),
        dispatch_log_repository=InMemoryDispatchLogRepository(),
    )

    assert isinstance(dependencies.telemetry_repository, TelemetryRepository)
    assert isinstance(dependencies.dispatch_plan_repository, InMemoryDispatchPlanRepository)
    assert isinstance(dependencies.dispatch_log_repository, InMemoryDispatchLogRepository)


def test_factory_returns_working_in_memory_repositories() -> None:
    dependencies = create_in_memory_repository_dependencies()
    at = datetime(2026, 1, 1, tzinfo=UTC)
    telemetry = TelemetryPoint(
        id="tel-1",
        site_id="site-a",
        at=at,
        soc_kwh=12.0,
        diesel_on=False,
        diesel_kw=0.0,
        batt_kw=0.0,
        solar_kw=4.0,
        load_kw=4.0,
        source=TelemetrySource.SIMULATOR,
        config_version=1,
    )
    plan = DispatchPlanRecord(
        id=1,
        site_id="site-a",
        tick_at=at,
        forecast_id=1,
        config_version=1,
        starting_soc_kwh=12.0,
        series=[],
        objective_cost=0.0,
        solver_status=DispatchSolverStatus.OPTIMAL,
        solve_ms=1,
        source=DispatchPlanSource.MILP,
    )
    log = DispatchLogRecord(
        id=1,
        plan_id=1,
        hour_index=0,
        executed_at=at,
        decision={"diesel_kw": 0.0},
    )

    dependencies.telemetry_repository.append(telemetry)
    dependencies.dispatch_plan_repository.append(plan)
    dependencies.dispatch_log_repository.append(log)

    assert dependencies.telemetry_repository.latest_soc(site_id="site-a") == 12.0
    assert dependencies.dispatch_plan_repository.get(plan_id=1) == plan
    assert dependencies.dispatch_log_repository.list_for_plan(plan_id=1) == (log,)


def test_factory_creates_separate_repository_instances() -> None:
    first = create_in_memory_repository_dependencies()
    second = create_in_memory_repository_dependencies()

    assert first.telemetry_repository is not first.dispatch_plan_repository
    assert first.telemetry_repository is not first.dispatch_log_repository
    assert first.dispatch_plan_repository is not first.dispatch_log_repository
    assert first.telemetry_repository is not second.telemetry_repository
    assert first.dispatch_plan_repository is not second.dispatch_plan_repository
    assert first.dispatch_log_repository is not second.dispatch_log_repository
