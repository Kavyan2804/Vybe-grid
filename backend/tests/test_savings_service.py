"""Unit tests for the pure Phase 3 optimized-versus-baseline calculation."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from src.schemas.telemetry import TelemetryPoint, TelemetrySource
from src.services.savings_service import (
    FuelConversion,
    SavingsCalculationError,
    calculate_savings,
)


def point(
    *,
    point_id: str,
    at: datetime,
    site_id: str = "site-a",
    diesel_kw: float = 0.0,
    source: TelemetrySource = TelemetrySource.SIMULATOR,
) -> TelemetryPoint:
    return TelemetryPoint(
        id=point_id,
        site_id=site_id,
        at=at,
        soc_kwh=20.0,
        diesel_on=diesel_kw > 0,
        diesel_kw=diesel_kw,
        batt_kw=0.0,
        solar_kw=5.0,
        load_kw=5.0,
        source=source,
        config_version=1,
    )


@pytest.fixture()
def conversion() -> FuelConversion:
    return FuelConversion(
        fuel_litres_per_kwh=0.25,
        fuel_cost_per_litre=100.0,
        co2_kg_per_litre=2.5,
    )


def test_identical_ledgers_produce_zero_savings(conversion: FuelConversion) -> None:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    optimized = [point(point_id="opt-1", at=start, diesel_kw=4.0)]
    baseline = [
        point(
            point_id="base-1",
            at=start,
            diesel_kw=4.0,
            source=TelemetrySource.BASELINE,
        )
    ]

    result = calculate_savings(optimized, baseline, conversion)

    assert result.optimized.diesel_energy_kwh == 4.0
    assert result.optimized.diesel_hours == 1.0
    assert result.saved.model_dump() == {
        "diesel_hours": 0.0,
        "diesel_energy_kwh": 0.0,
        "fuel_litres": 0.0,
        "cost": 0.0,
        "co2_kg": 0.0,
    }


def test_lower_optimized_diesel_produces_positive_savings(conversion: FuelConversion) -> None:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    optimized = [point(point_id="opt-1", at=start, diesel_kw=2.0)]
    baseline = [
        point(
            point_id="base-1",
            at=start,
            diesel_kw=6.0,
            source=TelemetrySource.BASELINE,
        )
    ]

    result = calculate_savings(optimized, baseline, conversion)

    assert result.saved.diesel_energy_kwh == 4.0
    assert result.saved.fuel_litres == 1.0
    assert result.saved.cost == 100.0
    assert result.saved.co2_kg == 2.5


def test_lower_baseline_diesel_produces_negative_savings(conversion: FuelConversion) -> None:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    optimized = [point(point_id="opt-1", at=start, diesel_kw=6.0)]
    baseline = [
        point(
            point_id="base-1",
            at=start,
            diesel_kw=2.0,
            source=TelemetrySource.BASELINE,
        )
    ]

    result = calculate_savings(optimized, baseline, conversion)

    assert result.saved.diesel_energy_kwh == -4.0
    assert result.saved.cost == -100.0
    assert result.saved.co2_kg == -2.5


def test_different_site_ids_are_rejected(conversion: FuelConversion) -> None:
    at = datetime(2026, 1, 1, tzinfo=UTC)

    with pytest.raises(SavingsCalculationError, match="same site_id"):
        calculate_savings(
            [point(point_id="opt-1", at=at, site_id="site-a")],
            [
                point(
                    point_id="base-1",
                    at=at,
                    site_id="site-b",
                    source=TelemetrySource.BASELINE,
                )
            ],
            conversion,
        )


def test_missing_matching_timestamp_is_rejected(conversion: FuelConversion) -> None:
    start = datetime(2026, 1, 1, tzinfo=UTC)

    with pytest.raises(SavingsCalculationError, match="matching timestamps"):
        calculate_savings(
            [point(point_id="opt-1", at=start)],
            [
                point(
                    point_id="base-1",
                    at=start + timedelta(hours=1),
                    source=TelemetrySource.BASELINE,
                )
            ],
            conversion,
        )


def test_duplicate_timestamps_are_rejected(conversion: FuelConversion) -> None:
    at = datetime(2026, 1, 1, tzinfo=UTC)

    with pytest.raises(SavingsCalculationError, match="duplicate timestamps"):
        calculate_savings(
            [point(point_id="opt-1", at=at), point(point_id="opt-2", at=at)],
            [
                point(
                    point_id="base-1",
                    at=at,
                    source=TelemetrySource.BASELINE,
                )
            ],
            conversion,
        )


def test_input_lists_and_models_are_not_mutated(conversion: FuelConversion) -> None:
    at = datetime(2026, 1, 1, tzinfo=UTC)
    optimized = [point(point_id="opt-1", at=at, diesel_kw=2.0)]
    baseline = [
        point(
            point_id="base-1",
            at=at,
            diesel_kw=4.0,
            source=TelemetrySource.BASELINE,
        )
    ]
    optimized_before = [item.model_dump() for item in optimized]
    baseline_before = [item.model_dump() for item in baseline]

    calculate_savings(optimized, baseline, conversion)

    assert [item.model_dump() for item in optimized] == optimized_before
    assert [item.model_dump() for item in baseline] == baseline_before


def test_injected_conversion_parameters_control_fuel_cost_and_co2() -> None:
    at = datetime(2026, 1, 1, tzinfo=UTC)
    conversion = FuelConversion(
        fuel_litres_per_kwh=0.4,
        fuel_cost_per_litre=73.5,
        co2_kg_per_litre=3.1,
    )

    result = calculate_savings(
        [point(point_id="opt-1", at=at, diesel_kw=1.0)],
        [
            point(
                point_id="base-1",
                at=at,
                diesel_kw=3.0,
                source=TelemetrySource.BASELINE,
            )
        ],
        conversion,
    )

    assert result.saved.fuel_litres == pytest.approx(0.8)
    assert result.saved.cost == pytest.approx(58.8)
    assert result.saved.co2_kg == pytest.approx(2.48)
