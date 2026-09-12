from datetime import datetime, timezone

import pytest

from optimizer.domain.entities import Battery, DieselGenerator, Forecast, FuelCurve, Load, Site
from optimizer.infrastructure.optimizer_pyomo.adapter import PyomoHighsOptimizerAdapter

def test_trivial_lp_correct_optimum():
    adapter = PyomoHighsOptimizerAdapter()
    obj_val, _ = adapter._smoke_test()
    assert abs(obj_val - 10.0) < 1e-5

def test_solve_latency_recorded():
    adapter = PyomoHighsOptimizerAdapter()
    _, latency_ms = adapter._smoke_test()
    assert latency_ms > 0

    _, latency_ms_larger = adapter._smoke_test_larger()
    assert latency_ms_larger > 0


def make_site(critical_kw, flexible_kw=None):
    flexible_kw = flexible_kw if flexible_kw is not None else [0.0] * 24
    return Site(
        name="test-site",
        latitude=19.0,
        longitude=72.0,
        timezone="Asia/Kolkata",
        battery=Battery(
            capacity_kwh=100.0,
            max_charge_kw=50.0,
            max_discharge_kw=50.0,
            round_trip_efficiency=0.9,
            degradation_cost_per_kwh_cycled=0.05,
            soc_min_pct=10.0,
            soc_max_pct=100.0,
        ),
        diesel_generator=DieselGenerator(
            min_load_kw=10.0,
            max_load_kw=60.0,
            fuel_curve=FuelCurve(
                litres_per_kwh_min_load=0.35,
                litres_per_kwh_max_load=0.28,
            ),
            start_cost=5.0,
            min_uptime_h=2.0,
            min_downtime_h=1.0,
        ),
        load=Load(
            critical_kw=critical_kw,
            flexible_kw=flexible_kw,
        ),
        fuel_cost_per_litre=1.20,
        emission_factor_kg_co2_per_litre=2.68,
    )


def make_forecast(solar_kw, load_kw=None):
    load_kw = load_kw if load_kw is not None else [0.0] * 24
    return Forecast(
        solar_kw=solar_kw,
        load_kw=load_kw,
        source="test",
        stale=False,
        fetched_at=datetime.now(timezone.utc),
    )


def test_abundant_solar_plan_has_zero_diesel_hours():
    adapter = PyomoHighsOptimizerAdapter()
    site = make_site(critical_kw=[5.0] * 24, flexible_kw=[0.0] * 24)
    forecast = make_forecast(solar_kw=[20.0] * 24)

    plan = adapter.solve(site, forecast, initial_soc_pct=50.0)

    assert len(plan.decisions) == 24
    assert all(decision.diesel_kw == pytest.approx(0.0) for decision in plan.decisions)
    assert not any(decision.diesel_on for decision in plan.decisions)


def test_no_solar_depleted_battery_starts_diesel_and_serves_critical_load():
    adapter = PyomoHighsOptimizerAdapter()
    site = make_site(critical_kw=[15.0] * 24, flexible_kw=[2.0] * 24)
    forecast = make_forecast(solar_kw=[0.0] * 24)

    plan = adapter.solve(site, forecast, initial_soc_pct=10.0)

    assert any(decision.diesel_on for decision in plan.decisions)
    assert all(decision.load_kw >= 15.0 for decision in plan.decisions)


def test_flexible_load_is_curtailable_but_critical_load_is_not():
    adapter = PyomoHighsOptimizerAdapter()
    site = make_site(critical_kw=[20.0] * 24, flexible_kw=[100.0] * 24)
    forecast = make_forecast(solar_kw=[0.0] * 24)

    plan = adapter.solve(site, forecast, initial_soc_pct=10.0)

    assert all(decision.load_kw >= 20.0 for decision in plan.decisions)
    assert any(decision.load_kw < 120.0 for decision in plan.decisions)


def test_infeasible_when_critical_load_exceeds_physical_supply():
    adapter = PyomoHighsOptimizerAdapter()
    site = make_site(critical_kw=[100.0] * 24, flexible_kw=[0.0] * 24)
    forecast = make_forecast(solar_kw=[0.0] * 24)

    with pytest.raises(RuntimeError):
        adapter.solve(site, forecast, initial_soc_pct=10.0)
