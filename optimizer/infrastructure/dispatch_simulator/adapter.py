"""Physics-based digital twin implementing the simulated DispatchPort tier."""

from __future__ import annotations

import random
from collections.abc import Callable
from datetime import datetime, timezone

from optimizer.domain.entities import ActualState, DispatchDecision, Site
from optimizer.domain.ports import DispatchPort


class SimulatorDispatchAdapter(DispatchPort):
    """Execute a planned hour against seeded, unbiased solar and load noise."""

    def __init__(
        self,
        *,
        seed: int | None = None,
        solar_noise_std: float = 0.05,
        load_noise_std: float = 0.03,
        simulation_run_id: str | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if solar_noise_std < 0 or load_noise_std < 0:
            raise ValueError("noise standard deviations must be non-negative")
        self._random = random.Random(seed)
        self.solar_noise_std = solar_noise_std
        self.load_noise_std = load_noise_std
        self.simulation_run_id = simulation_run_id
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def execute(
        self, site: Site, decision: DispatchDecision, current_soc_pct: float
    ) -> ActualState:
        """Simulate one hour using the optimizer's efficiency and fuel curve."""
        battery = site.battery
        eta = battery.round_trip_efficiency ** 0.5
        current_energy = battery.capacity_kwh * (current_soc_pct / 100.0)
        min_energy = battery.capacity_kwh * (battery.soc_min_pct / 100.0)
        max_energy = battery.capacity_kwh * (battery.soc_max_pct / 100.0)

        realized_solar = self._realize(decision.solar_kw, self.solar_noise_std)
        realized_load = self._realize(decision.load_kw, self.load_noise_std)
        battery_kw, next_energy = self._apply_battery(
            decision.battery_kw, current_energy, min_energy, max_energy, battery, eta
        )
        diesel_kw = self._diesel_output(site, decision)
        supply_kw = realized_solar + max(0.0, -battery_kw) + diesel_kw - max(0.0, battery_kw)
        unmet_load_kw = max(0.0, realized_load - supply_kw)
        fuel_litres = self._fuel_litres(site, diesel_kw)
        recorded_at = self._clock()
        if recorded_at.tzinfo is None:
            raise ValueError("simulator clock must return a timezone-aware datetime")

        return ActualState(
            site_id=site.name,
            recorded_at=recorded_at.astimezone(timezone.utc),
            solar_kw=round(realized_solar, 6),
            battery_kw=round(battery_kw, 6),
            diesel_kw=round(diesel_kw, 6),
            load_kw=round(realized_load, 6),
            load_served_kw=round(realized_load - unmet_load_kw, 6),
            unmet_load_kw=round(unmet_load_kw, 6),
            soc_pct=round(100.0 * next_energy / battery.capacity_kwh, 6),
            diesel_on=diesel_kw > 0.0,
            fuel_litres=round(fuel_litres, 6),
            fuel_cost=round(fuel_litres * site.fuel_cost_per_litre, 6),
            emissions_kg_co2=round(fuel_litres * site.emission_factor_kg_co2_per_litre, 6),
            source="simulator",
            badges=["SIMULATED"],
            simulation_run_id=self.simulation_run_id,
        )

    def _realize(self, planned_kw: float, noise_std: float) -> float:
        if planned_kw <= 0.0:
            return 0.0
        return max(0.0, planned_kw * (1.0 + self._random.gauss(0.0, noise_std)))

    @staticmethod
    def _apply_battery(
        requested_kw: float,
        current_energy: float,
        min_energy: float,
        max_energy: float,
        battery: object,
        eta: float,
    ) -> tuple[float, float]:
        if requested_kw >= 0.0:
            charge_kw = min(requested_kw, battery.max_charge_kw)
            accepted_kwh = min(charge_kw * eta, max_energy - current_energy)
            return accepted_kwh / eta, current_energy + accepted_kwh

        discharge_kw = min(abs(requested_kw), battery.max_discharge_kw)
        available_kwh = min(discharge_kw / eta, current_energy - min_energy)
        return -(available_kwh * eta), current_energy - available_kwh

    @staticmethod
    def _diesel_output(site: Site, decision: DispatchDecision) -> float:
        if not decision.diesel_on:
            return 0.0
        diesel = site.diesel_generator
        return min(max(decision.diesel_kw, diesel.min_load_kw), diesel.max_load_kw)

    @staticmethod
    def _fuel_litres(site: Site, diesel_kw: float) -> float:
        if diesel_kw <= 0.0:
            return 0.0
        diesel = site.diesel_generator
        ratio = (diesel_kw - diesel.min_load_kw) / (diesel.max_load_kw - diesel.min_load_kw)
        curve = diesel.fuel_curve
        litres_per_kwh = curve.litres_per_kwh_min_load + ratio * (
            curve.litres_per_kwh_max_load - curve.litres_per_kwh_min_load
        )
        return diesel_kw * litres_per_kwh
