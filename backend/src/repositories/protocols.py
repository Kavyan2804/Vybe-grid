"""Typed persistence contracts for Phase 3 backend services.

These protocols intentionally describe service-facing operations only. Concrete
database adapters belong to the persistence owner and are not defined here.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Protocol, TypeAlias, runtime_checkable

from src.schemas.telemetry import TelemetryPoint, TelemetrySource

JsonValue: TypeAlias = str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]
JsonObject: TypeAlias = dict[str, JsonValue]


class DispatchPlanSource(str, Enum):
    """Origins permitted for a persisted dispatch plan."""

    MILP = "milp"
    FALLBACK = "fallback"


class DispatchSolverStatus(str, Enum):
    """Solver outcomes permitted for a persisted dispatch plan."""

    OPTIMAL = "optimal"
    FEASIBLE = "feasible"
    INFEASIBLE = "infeasible"
    TIMEOUT = "timeout"


@dataclass(frozen=True, slots=True)
class DispatchPlanRecord:
    """The complete append-only Phase 3 dispatch-plan persistence contract."""

    id: int
    site_id: str
    tick_at: datetime
    forecast_id: int
    config_version: int
    starting_soc_kwh: float
    series: list[JsonObject]
    objective_cost: float
    solver_status: DispatchSolverStatus
    solve_ms: int
    source: DispatchPlanSource


@dataclass(frozen=True, slots=True)
class DispatchLogRecord:
    """An executed hour-zero decision linked to its planned dispatch."""

    id: int
    plan_id: int
    hour_index: int
    executed_at: datetime
    decision: JsonObject


@runtime_checkable
class TelemetryRepository(Protocol):
    """Read/write boundary for actual and baseline telemetry ledgers."""

    def list_for_site_in_range(
        self,
        *,
        site_id: str,
        start_at: datetime,
        end_at: datetime,
        source: TelemetrySource | None = None,
    ) -> Sequence[TelemetryPoint]:
        """Return one site's telemetry in the half-open interval ``[start_at, end_at)``."""

    def latest_soc(self, *, site_id: str) -> float | None:
        """Return the newest actual state of charge for a site, if recorded."""


@runtime_checkable
class DispatchPlanRepository(Protocol):
    """Append-only boundary for dispatch plans."""

    def append(self, plan: DispatchPlanRecord) -> DispatchPlanRecord:
        """Persist one immutable plan and return its stored representation."""

    def get(self, *, plan_id: int) -> DispatchPlanRecord | None:
        """Return a plan by identifier, if it exists."""

    def latest_for_site(self, *, site_id: str) -> DispatchPlanRecord | None:
        """Return the newest plan for a site, if it exists."""


@runtime_checkable
class DispatchLogRepository(Protocol):
    """Append/read boundary for executed dispatch decisions."""

    def append(self, entry: DispatchLogRecord) -> DispatchLogRecord:
        """Persist an executed decision linked to a dispatch plan."""

    def list_for_plan(self, *, plan_id: int) -> Sequence[DispatchLogRecord]:
        """Return execution records for one dispatch plan."""
