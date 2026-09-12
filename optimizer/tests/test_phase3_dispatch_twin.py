from datetime import datetime, timezone

import pytest

from optimizer.application.rolling_horizon_service import RollingHorizonService
from optimizer.domain.entities import (
    ActualState,
    Battery,
    DieselGenerator,
    DispatchDecision,
    DispatchPlan,
    Forecast,
    FuelCurve,
    Load,
    Site,
)
from optimizer.domain.ports import DispatchPort, ForecastPort, OptimizerPort
from optimizer.infrastructure.db.repositories import (
    InMemoryExecutionRepository,
    InMemoryPlanRepository,
    InMemoryTelemetryRepository,
)
from optimizer.infrastructure.dispatch_simulator.adapter import SimulatorDispatchAdapter


NOW = datetime(2026, 1, 1, 9, tzinfo=timezone.utc)


@pytest.fixture
def site() -> Site:
    return Site(
        name="phase3-site",
        latitude=19.0,
        longitude=72.0,
        timezone="Asia/Kolkata",
        battery=Battery(100, 25, 25, 0.81, 0.1, 20, 90),
        diesel_generator=DieselGenerator(10, 50, FuelCurve(0.35, 0.25), 0, 0, 0),
        load=Load([20] * 24, [0] * 24),
        fuel_cost_per_litre=2.0,
        emission_factor_kg_co2_per_litre=3.0,
    )


def decision(**changes: float) -> DispatchDecision:
    values = dict(
        hour=0, solar_kw=20.0, battery_kw=0.0, diesel_kw=0.0, load_kw=20.0,
        diesel_on=False, soc_pct=50.0, badges=["FORECAST"],
    )
    values.update(changes)
    return DispatchDecision(**values)


def test_seeded_simulator_is_deterministic(site: Site) -> None:
    clock = lambda: NOW
    first = SimulatorDispatchAdapter(seed=7, clock=clock, simulation_run_id="run-1")
    second = SimulatorDispatchAdapter(seed=7, clock=clock, simulation_run_id="run-1")

    assert first.execute(site, decision(), 50.0) == second.execute(site, decision(), 50.0)


def test_realized_solar_and_load_are_unbiased_over_many_seeds(site: Site) -> None:
    solar = []
    load = []
    for seed in range(1_000):
        result = SimulatorDispatchAdapter(seed=seed, clock=lambda: NOW).execute(site, decision(), 50.0)
        solar.append(result.solar_kw)
        load.append(result.load_kw)

    assert sum(solar) / len(solar) == pytest.approx(20.0, abs=0.15)
    assert sum(load) / len(load) == pytest.approx(20.0, abs=0.10)


def test_battery_and_diesel_physics_match_site_parameters(site: Site) -> None:
    result = SimulatorDispatchAdapter(seed=1, solar_noise_std=0, load_noise_std=0, clock=lambda: NOW).execute(
        site, decision(solar_kw=0.0, load_kw=50.0, battery_kw=-25.0, diesel_kw=30.0, diesel_on=True), 50.0
    )

    eta = site.battery.round_trip_efficiency ** 0.5
    expected_soc = 100 * (50 - 25 / eta) / 100
    expected_litres = 30 * (0.35 + (30 - 10) / (50 - 10) * (0.25 - 0.35))
    assert result.soc_pct == pytest.approx(expected_soc)
    assert result.fuel_litres == pytest.approx(expected_litres)
    assert result.fuel_cost == pytest.approx(expected_litres * 2.0)
    assert result.emissions_kg_co2 == pytest.approx(expected_litres * 3.0)
    assert result.unmet_load_kw == 0.0


class SingleForecast(ForecastPort):
    def __init__(self, forecast: Forecast) -> None:
        self.forecast = forecast

    def fetch_forecast(self, site: Site) -> Forecast:
        return self.forecast


class SingleDecisionOptimizer(OptimizerPort):
    def __init__(self, planned: DispatchDecision) -> None:
        self.planned = planned

    def solve(self, site: Site, forecast: Forecast, **_: object) -> DispatchPlan:
        return DispatchPlan(site.name, "forecast-1", [self.planned], NOW, "optimal", 1.0, False)


class HardwareShapedFake(DispatchPort):
    """Second adapter proves the rolling service depends only on DispatchPort."""

    def __init__(self) -> None:
        self.called = False

    def execute(self, site: Site, decision: DispatchDecision, current_soc_pct: float) -> ActualState:
        self.called = True
        return ActualState(
            site.name, NOW, decision.solar_kw, decision.battery_kw, decision.diesel_kw,
            decision.load_kw, decision.load_kw, 0.0, current_soc_pct, decision.diesel_on,
            0.0, 0.0, 0.0, "hardware", ["LIVE"], interval_hours=1.0,
        )


def test_tick_records_timestamp_consistent_execution_via_port(site: Site) -> None:
    forecast = Forecast([20.0], [20.0], "test", False, NOW)
    telemetry = InMemoryTelemetryRepository()
    execution = InMemoryExecutionRepository(telemetry)
    dispatch = HardwareShapedFake()
    service = RollingHorizonService(
        site, SingleForecast(forecast), SingleDecisionOptimizer(decision()), dispatch,
        InMemoryPlanRepository(), telemetry, execution_repository=execution,
    )

    result = service.tick()

    readings = telemetry.list_for_site(site.name)
    assert dispatch.called is True
    assert len(readings) == len(execution.dispatch_logs) == 1
    assert execution.dispatch_logs[0]["hour_index"] == 0
    assert execution.dispatch_logs[0]["executed_at"] == readings[0]["recorded_at"]
    assert result["telemetry"]["recorded_at"] == readings[0]["recorded_at"]
