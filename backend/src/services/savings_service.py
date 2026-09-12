"""Pure optimized-versus-baseline savings calculations."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from src.schemas.savings import SavingsDeltaMetrics, SavingsMetrics, SavingsResult
from src.schemas.telemetry import TelemetryPoint


class SavingsCalculationError(ValueError):
    """Raised when telemetry cannot form an unambiguous savings comparison."""


@dataclass(frozen=True, slots=True)
class FuelConversion:
    """Site-provided conversion inputs applied identically to both ledgers.

    Diesel output is converted to energy using the elapsed duration represented by
    each telemetry point. This prevents repeated rapid ticks from being counted as
    separate hours.
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
    *,
    end_at: datetime | None = None,
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

    optimized = _metrics(optimized_by_time.values(), conversion, end_at=end_at)
    baseline = _metrics(baseline_by_time.values(), conversion, end_at=end_at)
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


def weighted_diesel_totals(
    points: Iterable[TelemetryPoint],
    *,
    end_at: datetime | None = None,
) -> tuple[float, float]:
    """Return elapsed diesel runtime hours and diesel energy in kWh.

    A point describes the operating state until the next point. The final point
    runs until ``end_at`` when supplied; otherwise it retains the legacy one-hour
    duration for direct callers that do not have a query boundary.
    """
    telemetry = sorted(points, key=lambda point: point.at)
    diesel_hours = 0.0
    diesel_energy_kwh = 0.0
    for index, point in enumerate(telemetry):
        interval_end = (
            telemetry[index + 1].at
            if index + 1 < len(telemetry)
            else end_at
        )
        duration = (
            timedelta(hours=1)
            if interval_end is None
            else max(timedelta(0), interval_end - point.at)
        )
        duration_hours = duration.total_seconds() / 3600.0
        if point.diesel_kw > 0:
            diesel_hours += duration_hours
            diesel_energy_kwh += point.diesel_kw * duration_hours
    return diesel_hours, diesel_energy_kwh


def _metrics(
    points: Iterable[TelemetryPoint],
    conversion: FuelConversion,
    *,
    end_at: datetime | None = None,
) -> SavingsMetrics:
    diesel_hours, diesel_energy_kwh = weighted_diesel_totals(points, end_at=end_at)
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
