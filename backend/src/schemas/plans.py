"""Dispatch plan schemas per API_CONTRACT.md §2."""

from __future__ import annotations

from pydantic import BaseModel, Field

from src.schemas.common import ProvenanceBadge


class PlanSeriesItem(BaseModel):
    """Hourly dispatch decision in a 24-hour horizon."""

    hour: int = Field(..., ge=0, le=23, description="Hour offset (0-23)")
    diesel_on: bool = Field(..., description="Generator running status")
    diesel_kw: float = Field(..., ge=0, description="Generator output in kW")
    batt_charge_kw: float = Field(..., ge=0, description="Battery charging rate in kW")
    batt_discharge_kw: float = Field(..., ge=0, description="Battery discharging rate in kW")
    soc_kwh: float = Field(..., ge=0, description="Battery state of charge at end of hour in kWh")
    solar_used_kw: float = Field(..., ge=0, description="Solar power dispatched to load/battery in kW")
    solar_curtailed_kw: float = Field(..., ge=0, description="Excess solar power curtailed in kW")
    unmet_flex_kw: float = Field(0.0, ge=0, description="Unmet flexible load in kW (critical is always 0)")
    executed: bool = Field(..., description="True only for hour 0 that has actually run")
    badges: list[ProvenanceBadge] = Field(..., description="Provenance badges (SIMULATED, FORECAST, etc.)")


class DispatchPlanResponse(BaseModel):
    """Latest 24-hour dispatch plan response per API_CONTRACT.md §2."""

    plan_id: str = Field(..., description="Unique plan identifier (e.g. plan_000482)")
    site_id: str = Field(..., description="Microgrid site identifier")
    tick_at: str = Field(..., description="ISO-8601 timestamp with offset of when solve ran")
    starting_soc_kwh: float = Field(..., ge=0, description="Starting battery SoC in kWh from telemetry")
    series: list[PlanSeriesItem] = Field(default_factory=list, description="Hourly plan sequence")
    objective_cost: float = Field(..., description="Calculated total objective cost from optimizer")
    solver_status: str = Field(..., description="Solver status: optimal | feasible | infeasible | timeout | pending_integration")
    solve_ms: int = Field(..., ge=0, description="Solve execution duration in milliseconds")

