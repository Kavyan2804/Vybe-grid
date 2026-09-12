"""Dispatch plan schemas per API_CONTRACT.md §2."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field

from src.schemas.common import ProvenanceBadge


class MockPlanRequest(BaseModel):
    """Development-only request for generating a deterministic mock plan."""

    site_id: str = Field(..., min_length=1, max_length=64, examples=["demo-site"])
    horizon_hours: int = Field(
        24, ge=1, le=168, description="Planning horizon in hours", examples=[24]
    )


class MockSolverStatus(str, Enum):
    """Status values for development-only plan generation."""

    MOCK = "mock"


class MockDispatchPoint(BaseModel):
    """One deterministic hourly mock dispatch value set."""

    hour: int = Field(..., ge=0, le=167, examples=[0])
    solar_kw: float = Field(..., ge=0, description="Mock solar dispatch in kW", examples=[20.0])
    wind_kw: float = Field(..., ge=0, description="Mock wind dispatch in kW", examples=[8.0])
    battery_kw: float = Field(
        ..., description="Mock battery dispatch in kW; positive means discharge", examples=[5.0]
    )
    diesel_kw: float = Field(..., ge=0, description="Mock diesel dispatch in kW", examples=[0.0])
    load_kw: float = Field(..., ge=0, description="Mock load served in kW", examples=[33.0])


class MockPlan(BaseModel):
    """Development-only plan; values are not optimizer output."""

    plan_id: str = Field(..., examples=["mock-plan-demo-site-001"])
    site_id: str = Field(..., examples=["demo-site"])
    created_at: datetime = Field(..., description="Creation timestamp of the mock plan")
    planning_horizon_hours: int = Field(..., ge=1, le=168, examples=[24])
    solver_status: MockSolverStatus = Field(
        MockSolverStatus.MOCK, description="Always 'mock'; this is not an optimized result"
    )
    total_cost: float = Field(..., ge=0, description="Deterministic mock cost in local currency")
    total_emissions_kg_co2: float = Field(
        ..., ge=0, description="Deterministic mock emissions in kg CO2"
    )
    dispatch: list[MockDispatchPoint] = Field(..., min_length=1, max_length=168)


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
    load_kw: float | None = Field(None, ge=0, description="Forecast site load in kW")
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
