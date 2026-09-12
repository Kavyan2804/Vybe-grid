"""Typed planned-versus-actual comparison response models for Phase 3."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class HourlyDispatchComparison(BaseModel):
    """One planned dispatch hour paired with its actual telemetry record."""

    model_config = ConfigDict(extra="forbid")

    hour: int = Field(..., ge=0)
    at: datetime
    planned_diesel_kw: float = Field(..., ge=0)
    actual_diesel_kw: float = Field(..., ge=0)
    planned_batt_charge_kw: float = Field(..., ge=0)
    planned_batt_discharge_kw: float = Field(..., ge=0)
    actual_batt_kw: float
    planned_solar_used_kw: float = Field(..., ge=0)
    actual_solar_kw: float = Field(..., ge=0)
    planned_unmet_flex_kw: float = Field(..., ge=0)
    actual_load_kw: float = Field(..., ge=0)


class DispatchPlanComparison(BaseModel):
    """Read-only pairing of one persisted dispatch plan with actual telemetry."""

    model_config = ConfigDict(extra="forbid")

    plan_id: int
    site_id: str = Field(..., min_length=1)
    hours: list[HourlyDispatchComparison]
