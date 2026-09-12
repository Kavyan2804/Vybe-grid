"""Unit coverage for baseline identical-conditions + diesel continuity."""

from datetime import datetime, timezone

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
    InMemoryPlanRepository,
    InMemoryTelemetryRepository,
)


NOW = datetime(2026, 9, 13, 12, tzinfo=timezone.utc)


def _site() -> Site:
    return Site(
        name="continuity-site",
        latitude=19.0,
        longitude=72.0,
        timezone="Asia/Kolkata",
        battery=Battery(100, 25, 25, 0.9, 0.05, 20, 90),
        diesel_generator=DieselGenerator(5, 40, FuelCurve(0.35, 0.28), 10, 2, 1),
        load=Load([15] * 24, [5] * 24),
        fuel_cost_per_litre=1.2,
        emission_factor_kg_co2_per_litre=2.68,
    )


class _FixedForecast(ForecastPort):
    def __init__(self, forecast: Forecast) -> None:
        self.forecast = forecast

    def fetch_forecast(self, site: Site) -> Forecast:
        return self.forecast


class _CaptureSolve(OptimizerPort):
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def solve(self, site, forecast, **kwargs):
        self.calls.append(kwargs)
        decision = DispatchDecision(
            hour=0,
            solar_kw=10.0,
            battery_kw=0.0,
            diesel_kw=10.0,
            load_kw=20.0,
            diesel_on=True,
            soc_pct=kwargs.get("initial_soc_pct", 50.0),
            badges=["FORECAST"],
        )
        return DispatchPlan(site.name, "f1", [decision], NOW, "optimal", 1.0, False)


class _NoisyTwin(DispatchPort):
    def execute(self, site, decision, current_soc_pct):
        return ActualState(
            site_id=site.name,
            recorded_at=NOW,
            solar_kw=decision.solar_kw + 1.5,
            battery_kw=decision.battery_kw,
            diesel_kw=decision.diesel_kw,
            load_kw=decision.load_kw - 0.5,
            load_served_kw=decision.load_kw - 0.5,
            unmet_load_kw=0.0,
            soc_pct=current_soc_pct,
            diesel_on=True,
            fuel_litres=1.0,
            fuel_cost=1.0,
            emissions_kg_co2=2.0,
            source="simulator",
            badges=["SIMULATED"],
        )


def test_baseline_uses_realized_twin_conditions_not_forecast():
    site = _site()
    forecast = Forecast([10.0] * 24, [20.0] * 24, "test", False, NOW)
    optimizer = _CaptureSolve()
    service = RollingHorizonService(
        site,
        _FixedForecast(forecast),
        optimizer,
        _NoisyTwin(),
        InMemoryPlanRepository(),
        InMemoryTelemetryRepository(),
    )
    result = service.tick(provided_forecast=forecast)
    baseline = result["baseline_decision"]
    actual = result["actual_state"]
    # Baseline saw twin-realized solar/load (11.5 / 19.5), not forecast (10 / 20).
    assert actual.solar_kw == 11.5
    assert actual.load_kw == 19.5
    assert baseline.load_kw == actual.load_kw


def test_diesel_state_carries_into_next_solve():
    site = _site()
    forecast = Forecast([0.0] * 24, [25.0] * 24, "test", False, NOW)
    optimizer = _CaptureSolve()
    service = RollingHorizonService(
        site,
        _FixedForecast(forecast),
        optimizer,
        _NoisyTwin(),
        InMemoryPlanRepository(),
        InMemoryTelemetryRepository(),
    )
    service.tick(provided_forecast=forecast)
    service.tick(provided_forecast=forecast)
    assert optimizer.calls[0]["initial_diesel_on"] is False
    assert optimizer.calls[1]["initial_diesel_on"] is True
    assert optimizer.calls[1]["initial_diesel_run_hours"] >= 1
