"""Repository dependency container for Phase 3 backend services."""

from __future__ import annotations

from dataclasses import dataclass

from src.repositories.in_memory import (
    InMemoryDispatchLogRepository,
    InMemoryDispatchPlanRepository,
    InMemoryTelemetryRepository,
)
from src.repositories.protocols import (
    DispatchLogRepository,
    DispatchPlanRepository,
    TelemetryRepository,
)


@dataclass(frozen=True, slots=True)
class RepositoryDependencies:
    """Persistence interfaces required by Phase 3 backend services."""

    telemetry_repository: TelemetryRepository
    dispatch_plan_repository: DispatchPlanRepository
    dispatch_log_repository: DispatchLogRepository


def create_in_memory_repository_dependencies() -> RepositoryDependencies:
    """Build isolated in-memory repository dependencies for local development or tests."""

    return RepositoryDependencies(
        telemetry_repository=InMemoryTelemetryRepository(),
        dispatch_plan_repository=InMemoryDispatchPlanRepository(),
        dispatch_log_repository=InMemoryDispatchLogRepository(),
    )
