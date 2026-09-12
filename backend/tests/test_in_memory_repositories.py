"""Tests for deterministic in-memory Phase 3 repository fakes."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest

from src.repositories.in_memory import (
    DuplicateRepositoryIdError,
    InMemoryDispatchLogRepository,
    InMemoryDispatchPlanRepository,
    InMemoryTelemetryRepository,
)
from src.repositories.protocols import (
    DispatchLogRecord,
    DispatchPlanRecord,
    DispatchPlanSource,
    DispatchSolverStatus,
)
from src.schemas.telemetry import TelemetryPoint, TelemetrySource


def telemetry_point(
    *, point_id: str, at: datetime, site_id: str = "site-a", soc_kwh: float = 20.0
) -> TelemetryPoint:
    return TelemetryPoint(
        id=point_id,
        site_id=site_id,
        at=at,
        soc_kwh=soc_kwh,
        diesel_on=False,
        diesel_kw=0.0,
        batt_kw=0.0,
        solar_kw=4.0,
        load_kw=4.0,
        source=TelemetrySource.SIMULATOR,
        config_version=1,
    )


def plan(*, plan_id: int, tick_at: datetime, site_id: str = "site-a") -> DispatchPlanRecord:
    return DispatchPlanRecord(
        id=plan_id,
        site_id=site_id,
        tick_at=tick_at,
        forecast_id=10,
        config_version=1,
        starting_soc_kwh=20.0,
        series=[{"hour": 0, "diesel_kw": 0.0}],
        objective_cost=10.0,
        solver_status=DispatchSolverStatus.OPTIMAL,
        solve_ms=100,
        source=DispatchPlanSource.MILP,
    )


def dispatch_log(*, log_id: int, plan_id: int, executed_at: datetime) -> DispatchLogRecord:
    return DispatchLogRecord(
        id=log_id,
        plan_id=plan_id,
        hour_index=0,
        executed_at=executed_at,
        decision={"diesel_kw": 0.0, "diesel_on": False},
    )


def test_telemetry_append_retrieval_and_half_open_range() -> None:
    repository = InMemoryTelemetryRepository()
    start = datetime(2026, 1, 1, tzinfo=UTC)
    first = telemetry_point(point_id="tel-1", at=start)
    inside = telemetry_point(point_id="tel-2", at=start + timedelta(hours=1))
    endpoint = telemetry_point(point_id="tel-3", at=start + timedelta(hours=2))
    for record in (first, inside, endpoint):
        repository.append(record)

    records = repository.list_for_site_in_range(
        site_id="site-a", start_at=start, end_at=start + timedelta(hours=2)
    )

    assert records == (first, inside)


def test_latest_soc_returns_the_newest_point_for_a_site() -> None:
    repository = InMemoryTelemetryRepository()
    start = datetime(2026, 1, 1, tzinfo=UTC)
    repository.append(telemetry_point(point_id="tel-1", at=start, soc_kwh=16.0))
    repository.append(
        telemetry_point(point_id="tel-2", at=start + timedelta(hours=1), soc_kwh=12.5)
    )

    assert repository.latest_soc(site_id="site-a") == 12.5
    assert repository.latest_soc(site_id="missing") is None


def test_dispatch_plan_append_get_and_latest_for_site() -> None:
    repository = InMemoryDispatchPlanRepository()
    start = datetime(2026, 1, 1, tzinfo=UTC)
    first = plan(plan_id=1, tick_at=start)
    latest = plan(plan_id=2, tick_at=start + timedelta(hours=1))
    repository.append(first)
    repository.append(latest)

    assert repository.get(plan_id=1) == first
    assert repository.get(plan_id=999) is None
    assert repository.latest_for_site(site_id="site-a") == latest
    assert repository.latest_for_site(site_id="missing") is None


def test_dispatch_logs_are_filtered_by_plan_id() -> None:
    repository = InMemoryDispatchLogRepository()
    at = datetime(2026, 1, 1, tzinfo=UTC)
    matching = dispatch_log(log_id=1, plan_id=10, executed_at=at)
    repository.append(matching)
    repository.append(dispatch_log(log_id=2, plan_id=11, executed_at=at))

    assert repository.list_for_plan(plan_id=10) == (matching,)
    assert repository.list_for_plan(plan_id=99) == ()


@pytest.mark.parametrize(
    ("append", "record"),
    [
        (
            InMemoryTelemetryRepository().append,
            telemetry_point(point_id="tel-1", at=datetime(2026, 1, 1, tzinfo=UTC)),
        ),
        (
            InMemoryDispatchPlanRepository().append,
            plan(plan_id=1, tick_at=datetime(2026, 1, 1, tzinfo=UTC)),
        ),
        (
            InMemoryDispatchLogRepository().append,
            dispatch_log(log_id=1, plan_id=1, executed_at=datetime(2026, 1, 1, tzinfo=UTC)),
        ),
    ],
)
def test_duplicate_record_ids_are_rejected(
    append: Callable[[object], object], record: object
) -> None:
    append(record)

    with pytest.raises(DuplicateRepositoryIdError):
        append(record)


def test_empty_repositories_return_empty_or_none() -> None:
    at = datetime(2026, 1, 1, tzinfo=UTC)
    telemetry = InMemoryTelemetryRepository()
    plans = InMemoryDispatchPlanRepository()
    logs = InMemoryDispatchLogRepository()

    assert telemetry.list_for_site_in_range(site_id="site-a", start_at=at, end_at=at) == ()
    assert telemetry.latest_soc(site_id="site-a") is None
    assert plans.get(plan_id=1) is None
    assert plans.latest_for_site(site_id="site-a") is None
    assert logs.list_for_plan(plan_id=1) == ()
