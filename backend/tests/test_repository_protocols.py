"""Contract tests for Phase 3 repository protocols."""

from __future__ import annotations

import inspect
from dataclasses import fields

from src.repositories.protocols import (
    DispatchLogRecord,
    DispatchLogRepository,
    DispatchPlanRecord,
    DispatchPlanRepository,
    TelemetryRepository,
)


def parameter_names(protocol: type[object], method_name: str) -> list[str]:
    """Return a protocol method's declared parameter names in order."""

    return list(inspect.signature(getattr(protocol, method_name)).parameters)


def test_repository_protocols_are_importable_and_runtime_checkable() -> None:
    assert isinstance(TelemetryRepository, type)
    assert isinstance(DispatchPlanRepository, type)
    assert isinstance(DispatchLogRepository, type)
    assert isinstance(DispatchPlanRecord, type)
    assert isinstance(DispatchLogRecord, type)


def test_telemetry_repository_exposes_service_lookup_methods() -> None:
    assert parameter_names(TelemetryRepository, "list_for_site_in_range") == [
        "self",
        "site_id",
        "start_at",
        "end_at",
        "source",
    ]
    assert parameter_names(TelemetryRepository, "latest_soc") == ["self", "site_id"]


def test_dispatch_plan_repository_exposes_append_read_and_latest_methods() -> None:
    assert parameter_names(DispatchPlanRepository, "append") == ["self", "plan"]
    assert parameter_names(DispatchPlanRepository, "get") == ["self", "plan_id"]
    assert parameter_names(DispatchPlanRepository, "latest_for_site") == ["self", "site_id"]
    assert [field.name for field in fields(DispatchPlanRecord)] == [
        "id",
        "site_id",
        "tick_at",
        "forecast_id",
        "config_version",
        "starting_soc_kwh",
        "series",
        "objective_cost",
        "solver_status",
        "solve_ms",
        "source",
    ]


def test_dispatch_log_repository_exposes_append_and_read_methods() -> None:
    assert parameter_names(DispatchLogRepository, "append") == ["self", "entry"]
    assert parameter_names(DispatchLogRepository, "list_for_plan") == ["self", "plan_id"]
