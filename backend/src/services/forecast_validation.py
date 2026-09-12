"""Local validation service for forecast time series."""

from __future__ import annotations

from datetime import timedelta
from typing import TypeVar

from src.schemas.forecasts import ForecastPoint, ForecastSeries

ForecastT = TypeVar("ForecastT", bound=ForecastSeries)
MAX_FORECAST_POINTS = 168


class ForecastValidationError(ValueError):
    """Raised when a forecast series is not suitable for API use."""

    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__("Forecast validation failed: " + "; ".join(errors))


def validate_forecast_points(
    points: list[ForecastPoint], *, max_points: int = MAX_FORECAST_POINTS
) -> timedelta:
    """Validate ordering, uniqueness, interval consistency, and length.

    Returns the common interval so callers can use it when scheduling or
    combining local forecast data.
    """

    errors: list[str] = []
    if not points:
        errors.append("points must contain at least one forecast point")
    if len(points) > max_points:
        errors.append(f"points cannot contain more than {max_points} forecast points")
    if errors:
        raise ForecastValidationError(errors)

    timestamps = [point.timestamp for point in points]
    if len(set(timestamps)) != len(timestamps):
        errors.append("points must not contain duplicate timestamps")
    if timestamps != sorted(timestamps):
        errors.append("points must be ordered by ascending timestamp")

    interval = timedelta(0)
    if len(timestamps) > 1:
        intervals = [
            timestamps[index + 1] - timestamps[index]
            for index in range(len(timestamps) - 1)
        ]
        interval = intervals[0]
        if interval <= timedelta(0):
            errors.append("timestamps must be strictly increasing")
        if any(current != interval for current in intervals[1:]):
            errors.append("timestamps must use a consistent time interval")

    if errors:
        raise ForecastValidationError(errors)
    return interval


def validate_forecast_series(forecast: ForecastT) -> ForecastT:
    """Validate a complete local forecast series and return it unchanged."""

    validate_forecast_points(forecast.points)
    return forecast
