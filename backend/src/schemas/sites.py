"""Typed site configuration schemas for the Phase 1 API."""

from __future__ import annotations

from enum import Enum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class SiteModel(BaseModel):
    """Base configuration for strict, documented site payloads."""

    model_config = ConfigDict(extra="forbid", use_enum_values=True)


class SiteMetadata(SiteModel):
    """Human-readable metadata and timezone for a microgrid site."""

    name: str = Field(..., min_length=1, max_length=120, description="Display name of the site",
                      examples=["Kutch Community Microgrid"])
    timezone: str = Field(..., min_length=1, description="IANA timezone name",
                          examples=["Asia/Kolkata"])
    description: str | None = Field(None, max_length=500, description="Optional site description",
                                    examples=["Solar-battery system serving an off-grid village"])
    operator: str | None = Field(None, max_length=120, description="Organization operating the site",
                                 examples=["Vybe Energy Cooperative"])


class Location(SiteModel):
    """Geographic coordinates and elevation of the site."""

    latitude: float = Field(..., ge=-90, le=90, description="Latitude in decimal degrees",
                           examples=[23.2156])
    longitude: float = Field(..., ge=-180, le=180, description="Longitude in decimal degrees",
                            examples=[69.6678])
    elevation_m: float | None = Field(None, ge=-500, le=9000,
                                      description="Elevation above mean sea level in metres",
                                      examples=[15.0])


class AssetStatus(str, Enum):
    """Whether an energy asset is available for dispatch."""

    ACTIVE = "active"
    INACTIVE = "inactive"
    MAINTENANCE = "maintenance"


class EnergyAsset(SiteModel):
    """Common fields shared by all energy assets."""

    asset_id: str = Field(..., min_length=1, max_length=64, description="Unique asset identifier",
                          examples=["solar-roof-01"])
    name: str = Field(..., min_length=1, max_length=120, description="Human-readable asset name",
                      examples=["Community solar array"])
    status: AssetStatus = Field(AssetStatus.ACTIVE, description="Operational status")


class SolarAsset(EnergyAsset):
    """Solar photovoltaic generation asset."""

    asset_type: Literal["solar"] = Field("solar", description="Asset discriminator",
                                         examples=["solar"])
    capacity_kw: float = Field(..., gt=0, le=100_000, description="Rated solar capacity in kW",
                               examples=[120.0])
    efficiency_percentage: float = Field(20.0, gt=0, le=100,
                                         description="Panel conversion efficiency in percentage",
                                         examples=[21.5])
    tilt_degrees: float | None = Field(None, ge=0, le=90, description="Panel tilt in degrees",
                                       examples=[15.0])


class WindAsset(EnergyAsset):
    """Wind turbine generation asset."""

    asset_type: Literal["wind"] = Field("wind", description="Asset discriminator",
                                        examples=["wind"])
    capacity_kw: float = Field(..., gt=0, le=100_000, description="Rated wind capacity in kW",
                               examples=[80.0])
    cut_in_speed_mps: float = Field(3.0, ge=0, le=30,
                                    description="Minimum wind speed to generate power in m/s",
                                    examples=[3.5])
    cut_out_speed_mps: float = Field(25.0, gt=0, le=100,
                                     description="Wind speed at which the turbine shuts down in m/s",
                                     examples=[25.0])

    @model_validator(mode="after")
    def validate_wind_speeds(self) -> WindAsset:
        if self.cut_in_speed_mps >= self.cut_out_speed_mps:
            raise ValueError("cut_in_speed_mps must be lower than cut_out_speed_mps")
        return self


class BatteryAsset(EnergyAsset):
    """Battery energy storage asset."""

    asset_type: Literal["battery"] = Field("battery", description="Asset discriminator",
                                           examples=["battery"])
    capacity_kwh: float = Field(..., gt=0, le=100_000, description="Usable battery capacity in kWh",
                                examples=[500.0])
    max_charge_kw: float = Field(..., gt=0, description="Maximum charging power in kW",
                                 examples=[100.0])
    max_discharge_kw: float = Field(..., gt=0, description="Maximum discharging power in kW",
                                    examples=[100.0])
    min_soc_percentage: float = Field(10.0, ge=0, le=100,
                                     description="Minimum state of charge in percentage",
                                     examples=[10.0])
    max_soc_percentage: float = Field(90.0, ge=0, le=100,
                                     description="Maximum state of charge in percentage",
                                     examples=[90.0])
    initial_soc_percentage: float = Field(
        50.0, ge=0, le=100, description="Initial state of charge in percentage", examples=[50.0]
    )
    round_trip_efficiency_percentage: float = Field(
        90.0, gt=0, le=100, description="Round-trip efficiency in percentage", examples=[92.0]
    )

    @model_validator(mode="after")
    def validate_soc_range(self) -> BatteryAsset:
        if self.min_soc_percentage >= self.max_soc_percentage:
            raise ValueError("min_soc_percentage must be lower than max_soc_percentage")
        if not self.min_soc_percentage <= self.initial_soc_percentage <= self.max_soc_percentage:
            raise ValueError("initial_soc_percentage must be between min_soc_percentage and max_soc_percentage")
        return self


class DieselGenerator(EnergyAsset):
    """Dispatchable diesel backup generator."""

    asset_type: Literal["diesel"] = Field("diesel", description="Asset discriminator",
                                          examples=["diesel"])
    rated_power_kw: float = Field(..., gt=0, le=100_000, description="Rated generator output in kW",
                                  examples=[150.0])
    min_output_kw: float = Field(0.0, ge=0, description="Minimum stable generator output in kW",
                                 examples=[30.0])
    fuel_consumption_l_per_kwh: float = Field(
        ..., gt=0, description="Fuel consumed per generated kWh in litres", examples=[0.28]
    )
    fuel_cost_per_litre: float | None = Field(
        None, ge=0, description="Fuel cost per litre in local currency", examples=[96.0]
    )
    emissions_kg_co2_per_litre: float = Field(
        2.68, gt=0, description="Carbon emissions in kg CO2 per litre of fuel", examples=[2.68]
    )

    @model_validator(mode="after")
    def validate_output_range(self) -> DieselGenerator:
        if self.min_output_kw > self.rated_power_kw:
            raise ValueError("min_output_kw cannot exceed rated_power_kw")
        return self


Asset = Annotated[
    SolarAsset | WindAsset | BatteryAsset | DieselGenerator,
    Field(discriminator="asset_type"),
]


class EnergyAssets(SiteModel):
    """All generation and storage assets installed at a site."""

    assets: list[Asset] = Field(
        ..., min_length=1, description="Installed solar, wind, battery, and diesel assets",
        examples=[[{"asset_id": "solar-01", "name": "Solar array", "asset_type": "solar",
                    "capacity_kw": 120.0}]]
    )


class LoadProfile(SiteModel):
    """Expected electrical demand and optional operating profile."""

    peak_demand_kw: float = Field(..., gt=0, description="Peak electrical demand in kW",
                                  examples=[180.0])
    average_demand_kw: float = Field(..., gt=0, description="Average electrical demand in kW",
                                     examples=[75.0])
    critical_demand_kw: float = Field(0.0, ge=0, description="Demand that must always be served in kW",
                                      examples=[35.0])
    forecast_horizon_hours: int = Field(24, ge=1, le=168,
                                        description="Load forecast horizon in hours", examples=[24])

    @model_validator(mode="after")
    def validate_demand_levels(self) -> LoadProfile:
        if self.average_demand_kw > self.peak_demand_kw:
            raise ValueError("average_demand_kw cannot exceed peak_demand_kw")
        if self.critical_demand_kw > self.peak_demand_kw:
            raise ValueError("critical_demand_kw cannot exceed peak_demand_kw")
        return self


class OperatingConstraints(SiteModel):
    """Dispatch and resilience limits used by the API layer."""

    reserve_percentage: float = Field(20.0, ge=0, le=100,
                                      description="Required reserve margin in percentage",
                                      examples=[20.0])
    max_unmet_load_percentage: float = Field(
        0.0, ge=0, le=100, description="Maximum allowed unmet load in percentage", examples=[0.0]
    )
    diesel_startup_time_minutes: int = Field(
        10, ge=0, le=1440, description="Diesel startup time in minutes", examples=[10]
    )
    allow_diesel: bool = Field(True, description="Whether diesel generation may be dispatched")
    allow_load_shedding: bool = Field(False, description="Whether non-critical load may be shed")


class Site(SiteModel):
    """Complete validated site configuration used by Phase 1 APIs."""

    site_id: str = Field(..., min_length=1, max_length=64, description="Unique site identifier",
                         examples=["village-alpha"])
    metadata: SiteMetadata = Field(..., description="Site identity and operator metadata")
    location: Location = Field(..., description="Geographic location")
    energy_assets: EnergyAssets = Field(..., description="Installed energy assets")
    load_profile: LoadProfile = Field(..., description="Expected site electrical demand")
    operating_constraints: OperatingConstraints = Field(
        default_factory=OperatingConstraints, description="Dispatch and resilience constraints"
    )


class SiteImportResponse(BaseModel):
    """Response returned after importing a microgrid site configuration YAML."""

    site_id: str = Field(..., description="Imported site identifier")
    config_version: int = Field(..., ge=1, description="Version number of this configuration")
