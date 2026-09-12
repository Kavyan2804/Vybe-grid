"""Pure optimized-versus-baseline savings calculations."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime

from src.schemas.savings import SavingsDeltaMetrics, SavingsMetrics, SavingsResult
from src.schemas.telemetry import TelemetryPoint


class SavingsCalculationError(ValueError):
    """Raised when telemetry cannot form an unambiguous savings comparison."""


@dataclass(frozen=True, slots=True)
class FuelConversion:
    """Site-provided conversion inputs applied identically to both ledgers.

    The documented Phase 3 query sums hourly ``diesel_kw`` values as diesel kWh and
    counts a positive-diesel row as one diesel hour. This service therefore expects
    one telemetry point per one-hour tick; interval duration is not inferred here.
    """

    fuel_litres_per_kwh: float
    fuel_cost_per_litre: float
    co2_kg_per_litre: float

    def __post_init__(self) -> None:
        for name, value in (
            ("fuel_litres_per_kwh", self.fuel_litres_per_kwh),
            ("fuel_cost_per_litre", self.fuel_cost_per_litre),
            ("co2_kg_per_litre", self.co2_kg_per_litre),
        ):
            if value < 0:
                raise ValueError(f"{name} must be non-negative")


def calculate_savings(
    optimized_points: Sequence[TelemetryPoint],
    baseline_points: Sequence[TelemetryPoint],
    conversion: FuelConversion,
) -> SavingsResult:
    """Compare matching optimized and baseline telemetry without modifying either input.

    Each list must contain exactly one offset-aware telemetry point for every
    ``(site_id, at)`` key. The two key sets must match exactly, preventing a partial
    or unrelated ledger from being treated as a savings comparison.
    """

    optimized_by_time, optimized_site_id = _index_points(optimized_points, "optimized")
    baseline_by_time, baseline_site_id = _index_points(baseline_points, "baseline")

    if optimized_site_id != baseline_site_id:
        raise SavingsCalculationError(
            "optimized and baseline telemetry must belong to the same site_id"
        )
    if optimized_by_time.keys() != baseline_by_time.keys():
        raise SavingsCalculationError(
            "optimized and baseline telemetry must have matching timestamps"
        )

    optimized = _metrics(optimized_by_time.values(), conversion)
    baseline = _metrics(baseline_by_time.values(), conversion)
    return SavingsResult(
        site_id=optimized_site_id,
        optimized=optimized,
        baseline=baseline,
        saved=_difference(baseline, optimized),
    )


def _index_points(
    points: Sequence[TelemetryPoint], ledger_name: str
) -> tuple[dict[datetime, TelemetryPoint], str]:
    if not points:
        raise SavingsCalculationError(f"{ledger_name} telemetry must not be empty")

    site_ids = {point.site_id for point in points}
    if len(site_ids) != 1:
        raise SavingsCalculationError(f"{ledger_name} telemetry must contain one site_id")

    indexed: dict[datetime, TelemetryPoint] = {}
    for point in points:
        if point.at.tzinfo is None or point.at.utcoffset() is None:
            raise SavingsCalculationError(
                f"{ledger_name} telemetry contains a timestamp without an explicit offset"
            )
        if point.at in indexed:
            raise SavingsCalculationError(f"{ledger_name} telemetry contains duplicate timestamps")
        indexed[point.at] = point
    return indexed, site_ids.pop()


def _metrics(points: Iterable[TelemetryPoint], conversion: FuelConversion) -> SavingsMetrics:
    telemetry = tuple(points)  # Materialize only for deterministic repeated aggregation.
    diesel_energy_kwh = sum(point.diesel_kw for point in telemetry)
    diesel_hours = float(sum(point.diesel_kw > 0 for point in telemetry))
    fuel_litres = diesel_energy_kwh * conversion.fuel_litres_per_kwh
    return SavingsMetrics(
        diesel_hours=diesel_hours,
        diesel_energy_kwh=diesel_energy_kwh,
        fuel_litres=fuel_litres,
        cost=fuel_litres * conversion.fuel_cost_per_litre,
        co2_kg=fuel_litres * conversion.co2_kg_per_litre,
    )


def _difference(baseline: SavingsMetrics, optimized: SavingsMetrics) -> SavingsDeltaMetrics:
    return SavingsDeltaMetrics(
        diesel_hours=baseline.diesel_hours - optimized.diesel_hours,
        diesel_energy_kwh=baseline.diesel_energy_kwh - optimized.diesel_energy_kwh,
        fuel_litres=baseline.fuel_litres - optimized.fuel_litres,
        cost=baseline.cost - optimized.cost,
        co2_kg=baseline.co2_kg - optimized.co2_kg,
    )
