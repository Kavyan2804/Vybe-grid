"""Typed time-series forecast input schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ForecastPoint(BaseModel):
    """One timestamped forecast observation."""

    model_config = ConfigDict(extra="forbid")

    timestamp: datetime = Field(
        ...,
        description="Timezone-aware ISO-8601 timestamp for this forecast point",
        examples=["2026-01-15T00:00:00Z"],
    )
    value: float = Field(..., ge=0, description="Forecast value in the declared unit", examples=[75.5])
    unit: str = Field(..., min_length=1, max_length=32, description="Unit of the forecast value",
                      examples=["kW"])
    confidence: float | None = Field(
        None, ge=0, le=1, description="Optional confidence score from 0 to 1", examples=[0.92]
    )
    source: str | None = Field(
        None, min_length=1, max_length=120, description="Optional local model or data source",
        examples=["mock-weather-model"],
    )

    @field_validator("timestamp")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timestamp must include a timezone offset")
        return value

    @field_validator("unit", "source")
    @classmethod
    def trim_text(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else None


class ForecastSeries(BaseModel):
    """Common envelope for a bounded, timestamped forecast series."""

    model_config = ConfigDict(extra="forbid")

    site_id: str = Field(..., min_length=1, max_length=64, description="Site identifier",
                         examples=["village-alpha"])
    points: list[ForecastPoint] = Field(
        ..., min_length=1, max_length=168, description="Forecast points in chronological order"
    )


class LoadForecast(ForecastSeries):
    """Expected electrical load forecast, measured in kW."""

    forecast_type: Literal["load"] = Field("load", description="Forecast discriminator")


class SolarGenerationForecast(ForecastSeries):
    """Solar generation forecast, measured in kW."""

    forecast_type: Literal["solar_generation"] = Field(
        "solar_generation", description="Forecast discriminator"
    )


class WindGenerationForecast(ForecastSeries):
    """Wind generation forecast, measured in kW."""

    forecast_type: Literal["wind_generation"] = Field(
        "wind_generation", description="Forecast discriminator"
    )


class WeatherForecast(ForecastSeries):
    """Weather forecast values such as irradiance, temperature, or wind speed."""

    forecast_type: Literal["weather"] = Field("weather", description="Forecast discriminator")


class FuelPriceForecast(ForecastSeries):
    """Fuel price forecast, commonly measured in currency per litre."""

    forecast_type: Literal["fuel_price"] = Field("fuel_price", description="Forecast discriminator")
