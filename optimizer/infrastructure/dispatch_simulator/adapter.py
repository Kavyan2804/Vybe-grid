"""Simulator Dispatch Adapter (ARCHITECTURE.md §2, §8).

The digital twin standing in for real hardware (inverter, battery BMS, generator controller).
Executes hour 0 of a dispatch plan, simulates battery physics and generator state,
and returns actual telemetry conforming to packages/contracts/events/telemetry.schema.json.
"""

from datetime import datetime, timezone
from typing import Dict, Any

from optimizer.domain.entities import Site, DispatchDecision
from optimizer.domain.ports import DispatchPort


class SimulatorDispatchAdapter(DispatchPort):
    """Physics-based digital twin simulator for microgrid dispatch."""

    def __init__(self, add_noise: bool = False, noise_std: float = 0.02) -> None:
        self.add_noise = add_noise
        self.noise_std = noise_std

    def execute(
        self, site: Site, decision: DispatchDecision, current_soc_pct: float
    ) -> Dict[str, Any]:
        """Execute decision for hour 0 and simulate actual microgrid response."""
        battery = site.battery
        capacity_kwh = battery.capacity_kwh
        eta = battery.round_trip_efficiency ** 0.5

        # Current stored energy in kWh
        current_energy_kwh = capacity_kwh * (current_soc_pct / 100.0)

        # Battery dynamics
        battery_kw = decision.battery_kw
        actual_charge_kw = 0.0
        actual_discharge_kw = 0.0

        if battery_kw > 0:  # Charging
            actual_charge_kw = min(battery_kw, battery.max_charge_kw)
            energy_in = actual_charge_kw * eta
            new_energy_kwh = min(capacity_kwh, current_energy_kwh + energy_in)
            actual_battery_kw = (new_energy_kwh - current_energy_kwh) / eta if eta > 0 else 0.0
        elif battery_kw < 0:  # Discharging
            requested_discharge = abs(battery_kw)
            actual_discharge_kw = min(requested_discharge, battery.max_discharge_kw)
            energy_out = actual_discharge_kw / eta
            new_energy_kwh = max(0.0, current_energy_kwh - energy_out)
            actual_battery_kw = -((current_energy_kwh - new_energy_kwh) * eta)
        else:
            new_energy_kwh = current_energy_kwh
            actual_battery_kw = 0.0

        new_soc_pct = max(0.0, min(100.0, (new_energy_kwh / capacity_kwh) * 100.0))

        diesel_kw = decision.diesel_kw if decision.diesel_on else 0.0
        solar_kw = decision.solar_kw
        load_kw = decision.load_kw

        return {
            "site_id": site.name,
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "solar_kw": round(float(solar_kw), 4),
            "battery_kw": round(float(actual_battery_kw), 4),
            "diesel_kw": round(float(diesel_kw), 4),
            "load_kw": round(float(load_kw), 4),
            "soc_pct": round(float(new_soc_pct), 4),
            "diesel_on": bool(decision.diesel_on),
            "source": "simulator",
        }
