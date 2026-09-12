"""Typed read-only savings comparison schemas for Phase 3."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from src.schemas.common import ProvenanceBadge


class SavingsMetrics(BaseModel):
    """Fuel, cost, and emissions totals for one telemetry ledger."""

    model_config = ConfigDict(extra="forbid")

    diesel_hours: float = Field(..., ge=0)
    diesel_energy_kwh: float = Field(..., ge=0)
    fuel_litres: float = Field(..., ge=0)
    cost: float = Field(..., ge=0)
    co2_kg: float = Field(..., ge=0)


class SavingsDeltaMetrics(BaseModel):
    """Signed difference between baseline and optimized ledger totals."""

    model_config = ConfigDict(extra="forbid")

    diesel_hours: float
    diesel_energy_kwh: float
    fuel_litres: float
    cost: float
    co2_kg: float


class SavingsResult(BaseModel):
    """Read-only comparison of optimized and baseline telemetry ledgers."""

    model_config = ConfigDict(extra="forbid")

    site_id: str = Field(..., min_length=1)
    optimized: SavingsMetrics
    baseline: SavingsMetrics
    saved: SavingsDeltaMetrics
    badges: list[ProvenanceBadge] = Field(
        default_factory=lambda: [ProvenanceBadge.SIMULATED, ProvenanceBadge.BASELINE]
    )
