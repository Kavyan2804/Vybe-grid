"""Tests for typed forecast inputs and time-series validation."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from src.schemas.forecasts import ForecastPoint, LoadForecast
from src.services.forecast_validation import (
    ForecastValidationError,
    validate_forecast_points,
    validate_forecast_series,
)


def points(count: int = 3, interval_hours: int = 1) -> list[ForecastPoint]:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    return [
        ForecastPoint(
            timestamp=start + timedelta(hours=index * interval_hours),
            value=50 + index,
            unit="kW",
            confidence=0.9,
            source="mock-model",
        )
        for index in range(count)
    ]


def test_valid_load_forecast_is_accepted() -> None:
    forecast = LoadForecast(site_id="village-alpha", points=points())

    assert validate_forecast_series(forecast) is forecast
    assert validate_forecast_points(forecast.points) == timedelta(hours=1)


@pytest.mark.parametrize(
    "point",
    [
        {"timestamp": "2026-01-01T00:00:00", "value": 1, "unit": "kW"},
        {"timestamp": "2026-01-01T00:00:00Z", "value": -1, "unit": "kW"},
        {"timestamp": "2026-01-01T00:00:00Z", "value": 1, "unit": "kW", "confidence": 1.1},
        {"timestamp": "not-a-timestamp", "value": 1, "unit": "kW"},
    ],
)
def test_point_rejects_invalid_timestamp_value_or_confidence(point: dict) -> None:
    with pytest.raises(ValidationError):
        ForecastPoint.model_validate(point)


def test_empty_series_is_rejected() -> None:
    with pytest.raises(ValidationError):
        LoadForecast(site_id="site-1", points=[])


@pytest.mark.parametrize(
    "bad_points",
    [
        points(2) + points(1),  # duplicate timestamp
        points(3, 2),  # valid, used below only as a baseline
    ],
)
def test_duplicate_timestamps_are_rejected(bad_points: list[ForecastPoint]) -> None:
    if bad_points[0].timestamp != bad_points[1].timestamp:
        bad_points[1] = bad_points[0].model_copy()
    with pytest.raises(ForecastValidationError, match="duplicate timestamps"):
        validate_forecast_points(bad_points)


def test_inconsistent_intervals_are_rejected() -> None:
    bad = points()
    bad[2] = bad[2].model_copy(
        update={"timestamp": bad[1].timestamp + timedelta(hours=2)}
    )

    with pytest.raises(ForecastValidationError, match="consistent time interval"):
        validate_forecast_points(bad)


def test_unsorted_timestamps_are_rejected() -> None:
    bad = points()
    bad[0], bad[1] = bad[1], bad[0]

    with pytest.raises(ForecastValidationError, match="ascending timestamp"):
        validate_forecast_points(bad)


def test_forecast_length_is_bounded() -> None:
    with pytest.raises(ForecastValidationError, match="more than 168"):
        validate_forecast_points(points(169))
