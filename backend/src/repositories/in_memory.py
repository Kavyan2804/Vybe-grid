"""Deterministic in-memory implementations of the Phase 3 repository contracts."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime

from src.repositories.protocols import DispatchLogRecord, DispatchPlanRecord
from src.schemas.telemetry import TelemetryPoint, TelemetrySource


class DuplicateRepositoryIdError(ValueError):
    """Raised when an append would overwrite an existing persisted record."""


class InMemoryTelemetryRepository:
    """In-memory telemetry ledger for backend services and tests."""

    def __init__(self) -> None:
        self._points: dict[str, TelemetryPoint] = {}

    def append(self, point: TelemetryPoint) -> TelemetryPoint:
        """Store one telemetry point, rejecting duplicate record identifiers."""

        if point.id in self._points:
            raise DuplicateRepositoryIdError(f"Telemetry record '{point.id}' already exists")
        self._points[point.id] = point.model_copy(deep=True)
        return self._points[point.id].model_copy(deep=True)

    def list_for_site_in_range(
        self,
        *,
        site_id: str,
        start_at: datetime,
        end_at: datetime,
        source: TelemetrySource | None = None,
    ) -> tuple[TelemetryPoint, ...]:
        """Return telemetry in the half-open interval ``[start_at, end_at)``."""

        return tuple(
            point.model_copy(deep=True)
            for point in sorted(self._points.values(), key=lambda item: item.at)
            if point.site_id == site_id
            and start_at <= point.at < end_at
            and (source is None or point.source is source)
        )

    def latest_soc(self, *, site_id: str) -> float | None:
        """Return the state of charge from the newest stored telemetry point."""

        matching = (point for point in self._points.values() if point.site_id == site_id)
        latest = max(matching, key=lambda point: point.at, default=None)
        return None if latest is None else latest.soc_kwh


class InMemoryDispatchPlanRepository:
    """In-memory append-only dispatch-plan repository for backend services and tests."""

    def __init__(self) -> None:
        self._plans: dict[int, DispatchPlanRecord] = {}

    def append(self, plan: DispatchPlanRecord) -> DispatchPlanRecord:
        """Store one plan, rejecting a duplicate plan identifier."""

        if plan.id in self._plans:
            raise DuplicateRepositoryIdError(f"Dispatch plan '{plan.id}' already exists")
        self._plans[plan.id] = deepcopy(plan)
        return deepcopy(self._plans[plan.id])

    def get(self, *, plan_id: int) -> DispatchPlanRecord | None:
        """Return a copied plan by identifier, if present."""

        plan = self._plans.get(plan_id)
        return None if plan is None else deepcopy(plan)

    def latest_for_site(self, *, site_id: str) -> DispatchPlanRecord | None:
        """Return the latest copied plan for a site, if present."""

        matching = (plan for plan in self._plans.values() if plan.site_id == site_id)
        latest = max(matching, key=lambda plan: plan.tick_at, default=None)
        return None if latest is None else deepcopy(latest)


class InMemoryDispatchLogRepository:
    """In-memory append-only dispatch-log repository for backend services and tests."""

    def __init__(self) -> None:
        self._entries: dict[int, DispatchLogRecord] = {}

    def append(self, entry: DispatchLogRecord) -> DispatchLogRecord:
        """Store one execution log, rejecting a duplicate log identifier."""

        if entry.id in self._entries:
            raise DuplicateRepositoryIdError(f"Dispatch log '{entry.id}' already exists")
        self._entries[entry.id] = deepcopy(entry)
        return deepcopy(self._entries[entry.id])

    def list_for_plan(self, *, plan_id: int) -> tuple[DispatchLogRecord, ...]:
        """Return copied execution logs associated with a dispatch plan."""

        return tuple(
            deepcopy(entry) for entry in self._entries.values() if entry.plan_id == plan_id
        )
