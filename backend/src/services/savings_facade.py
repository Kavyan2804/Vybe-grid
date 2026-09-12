"""Application facade combining Phase 3 comparison and savings calculations."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta

from src.repositories.protocols import DispatchPlanRecord
from src.schemas.comparison import DispatchPlanComparison
from src.schemas.savings import SavingsDeltaMetrics, SavingsMetrics
from src.schemas.telemetry import TelemetrySource
from src.services.comparison_service import compare_plan_to_telemetry
from src.services.repository_dependencies import RepositoryDependencies
from src.services.savings_service import FuelConversion, calculate_savings


class SavingsFacadeError(ValueError):
    """Raised when a site/range cannot produce a complete Phase 3 comparison."""


@dataclass(frozen=True, slots=True)
class SavingsFacadeResult:
    """The comparison and derived ledger metrics for one site and time range."""

    comparison: DispatchPlanComparison
    optimized: SavingsMetrics
    baseline: SavingsMetrics
    saved: SavingsDeltaMetrics


class SavingsFacade:
    """Coordinate repository reads with the pure comparison and savings services."""

    def __init__(self, dependencies: RepositoryDependencies, conversion: FuelConversion) -> None:
        self._dependencies = dependencies
        self._conversion = conversion

    def calculate(
        self, *, site_id: str, start_at: datetime, end_at: datetime
    ) -> SavingsFacadeResult:
        """Calculate a read-only comparison for the half-open range ``[start_at, end_at)``."""

        if start_at >= end_at:
            raise SavingsFacadeError("start_at must be earlier than end_at")

        plan = self._dependencies.dispatch_plan_repository.latest_for_site(site_id=site_id)
        if plan is None:
            raise SavingsFacadeError(f"No dispatch plan was found for site '{site_id}'")
        if plan.site_id != site_id:
            raise SavingsFacadeError("requested site_id does not match the dispatch plan site_id")

        baseline = self._dependencies.telemetry_repository.list_for_site_in_range(
            site_id=site_id,
            start_at=start_at,
            end_at=end_at,
            source=TelemetrySource.BASELINE,
        )
        all_telemetry = self._dependencies.telemetry_repository.list_for_site_in_range(
            site_id=site_id,
            start_at=start_at,
            end_at=end_at,
        )
        optimized = tuple(
            point for point in all_telemetry if point.source is not TelemetrySource.BASELINE
        )
        if not optimized or not baseline:
            raise SavingsFacadeError(
                "optimized and baseline telemetry are both required for the requested range"
            )

        range_plan = _plan_for_range(plan, start_at=start_at, end_at=end_at)
        if not range_plan.series:
            raise SavingsFacadeError("dispatch plan has no hours in the requested range")

        comparison = compare_plan_to_telemetry(range_plan, optimized)
        savings = calculate_savings(optimized, baseline, self._conversion)
        return SavingsFacadeResult(
            comparison=comparison,
            optimized=savings.optimized,
            baseline=savings.baseline,
            saved=savings.saved,
        )


def _plan_for_range(
    plan: DispatchPlanRecord, *, start_at: datetime, end_at: datetime
) -> DispatchPlanRecord:
    """Return a copied plan view containing only decisions in ``[start_at, end_at)``."""

    filtered_series = []
    for decision in plan.series:
        hour = decision.get("hour")
        if isinstance(hour, bool) or not isinstance(hour, int) or hour < 0:
            raise SavingsFacadeError("dispatch plan hour must be a non-negative integer")
        planned_at = plan.tick_at + timedelta(hours=hour)
        if start_at <= planned_at < end_at:
            filtered_series.append(decision.copy())
    return replace(plan, series=filtered_series)
