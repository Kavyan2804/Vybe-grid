import yaml
import json
import os
import re
from dataclasses import dataclass
from typing import Any, List, NamedTuple
from datetime import datetime, timezone
from jsonschema import Draft202012Validator

class FuelCurve(NamedTuple):
    litres_per_kwh_min_load: float
    litres_per_kwh_max_load: float

@dataclass(frozen=True)
class Battery:
    capacity_kwh: float
    max_charge_kw: float
    max_discharge_kw: float
    round_trip_efficiency: float
    degradation_cost_per_kwh_cycled: float
    soc_min_pct: float
    soc_max_pct: float

@dataclass(frozen=True)
class DieselGenerator:
    min_load_kw: float
    max_load_kw: float
    fuel_curve: FuelCurve
    start_cost: float
    min_uptime_h: float
    min_downtime_h: float

@dataclass(frozen=True)
class Load:
    critical_kw: List[float]
    flexible_kw: List[float]

@dataclass(frozen=True)
class Site:
    name: str
    latitude: float
    longitude: float
    timezone: str
    battery: Battery
    diesel_generator: DieselGenerator
    load: Load
    fuel_cost_per_litre: float
    emission_factor_kg_co2_per_litre: float

@dataclass(frozen=True)
class Forecast:
    solar_kw: List[float]
    load_kw: List[float]
    source: str
    stale: bool
    fetched_at: datetime
    solar_p10_kw: List[float] | None = None
    solar_p90_kw: List[float] | None = None

@dataclass(frozen=True)
class DispatchDecision:
    hour: int
    solar_kw: float
    battery_kw: float
    diesel_kw: float
    load_kw: float
    diesel_on: bool
    soc_pct: float
    badges: List[str]
    reason: str | None = None

@dataclass(frozen=True)
class DispatchPlan:
    site_id: str
    forecast_id: str
    decisions: List[DispatchDecision]
    created_at: datetime
    solver_status: str
    solve_time_ms: float
    fallback_used: bool


@dataclass(frozen=True)
class ActualState:
    """One realized one-hour dispatch interval produced by a DispatchPort."""

    site_id: str
    recorded_at: datetime
    solar_kw: float
    battery_kw: float
    diesel_kw: float
    load_kw: float
    load_served_kw: float
    unmet_load_kw: float
    soc_pct: float
    diesel_on: bool
    fuel_litres: float
    fuel_cost: float
    emissions_kg_co2: float
    source: str
    badges: List[str]
    simulation_run_id: str | None = None
    interval_hours: float = 1.0

    def to_telemetry(self) -> dict[str, Any]:
        """Return the additive-free payload required by telemetry.schema.json."""
        return {
            "site_id": self.site_id,
            "recorded_at": self.recorded_at.astimezone(timezone.utc).isoformat(),
            "solar_kw": self.solar_kw,
            "battery_kw": self.battery_kw,
            "diesel_kw": self.diesel_kw,
            "load_kw": self.load_kw,
            "soc_pct": self.soc_pct,
            "diesel_on": self.diesel_on,
            "source": self.source,
        }

def load_site_from_yaml(path: str) -> Site:
    """Load a Site entity from a YAML configuration file.

    Every field must be present — no silent defaults.
    """
    with open(path, 'r') as f:
        data = yaml.safe_load(f)
    schema_path = os.path.abspath(
        os.path.join(os.path.dirname(__file__), '..', '..', 'packages', 'contracts', 'site-config.schema.json')
    )
    with open(schema_path, 'r') as f:
        schema = json.load(f)
    errors = sorted(Draft202012Validator(schema).iter_errors(data), key=lambda error: list(error.path))
    if errors:
        error = errors[0]
        field = '.'.join(str(part) for part in error.path)
        if not field:
            required = re.search(r"'([^']+)' is a required property", error.message)
            field = required.group(1) if required else 'site'
        raise ValueError(f"invalid site configuration field '{field}': {error.message}")

    battery = Battery(**data['battery'])

    dg = data['diesel_generator']
    fuel_curve = FuelCurve(**dg['fuel_curve'])
    diesel_generator = DieselGenerator(
        min_load_kw=dg['min_load_kw'],
        max_load_kw=dg['max_load_kw'],
        fuel_curve=fuel_curve,
        start_cost=dg['start_cost'],
        min_uptime_h=dg['min_uptime_h'],
        min_downtime_h=dg['min_downtime_h'],
    )

    load = Load(**data['load'])

    return Site(
        name=data['name'],
        latitude=data['latitude'],
        longitude=data['longitude'],
        timezone=data['timezone'],
        battery=battery,
        diesel_generator=diesel_generator,
        load=load,
        fuel_cost_per_litre=data['fuel_cost_per_litre'],
        emission_factor_kg_co2_per_litre=data['emission_factor_kg_co2_per_litre'],
    )
