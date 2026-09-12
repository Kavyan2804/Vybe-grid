"""Typed actual telemetry schemas for the Phase 3 ledger contract."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class TelemetrySource(str, Enum):
    """Origin of an actual or shadow-baseline telemetry point."""

    SIMULATOR = "simulator"
    HARDWARE = "hardware"
    FALLBACK = "fallback"
    BASELINE = "baseline"


class TelemetryPoint(BaseModel):
    """One actual telemetry record as specified in DATA_MODEL.md section 3."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., min_length=1)
    site_id: str = Field(..., min_length=1, max_length=64)
    at: datetime = Field(..., description="ISO-8601 timestamp with an explicit offset")
    soc_kwh: float = Field(..., ge=0)
    diesel_on: bool
    diesel_kw: float = Field(..., ge=0)
    batt_kw: float
    solar_kw: float = Field(..., ge=0)
    load_kw: float = Field(..., ge=0)
    source: TelemetrySource
    config_version: int = Field(..., ge=1)

    @field_validator("at")
    @classmethod
    def require_offset_aware_timestamp(cls, value: datetime) -> datetime:
        """Reject timestamps that do not carry the API contract's required offset."""

        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("at must be an ISO-8601 timestamp with an explicit offset")
        return value
