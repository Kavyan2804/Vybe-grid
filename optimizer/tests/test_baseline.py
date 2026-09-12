"""Tests for the baseline greedy controller (Task 0.3).

Covers:
- Solar-only load coverage
- Battery discharge on shortfall
- Diesel start when both exhausted
- The key 'cloudy afternoon → evening diesel' failure mode
- No Forecast argument in the function signature (by construction)
"""
import inspect
import pytest

from optimizer.application.baseline_service import decide, MicrogridState
from optimizer.domain.entities import (
    Battery, DieselGenerator, FuelCurve, Load, Site,
)


@pytest.fixture
def site():
    """A test site with generous battery and diesel for clear test behaviour."""
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
            soc_min_pct=20.0,
            soc_max_pct=100.0,
        ),
        diesel_generator=DieselGenerator(
            min_load_kw=20.0,
            max_load_kw=100.0,
            fuel_curve=FuelCurve(
                litres_per_kwh_min_load=0.35,
                litres_per_kwh_max_load=0.28,
            ),
            start_cost=5.0,
            min_uptime_h=3,
            min_downtime_h=1,
        ),
        load=Load(
            critical_kw=[20.0] * 24,
            flexible_kw=[5.0] * 24,
        ),
        fuel_cost_per_litre=1.20,
        emission_factor_kg_co2_per_litre=2.68,
    )


def test_no_forecast_argument():
    """The greedy controller must NOT accept a Forecast — enforced by signature."""
    sig = inspect.signature(decide)
    assert "forecast" not in sig.parameters, (
        "decide() must not have a 'forecast' parameter — "
        "foresight is forbidden by construction"
    )


def test_solar_covers_load(site):
    """When solar exceeds load, diesel stays off and battery charges."""
    state = MicrogridState(soc_pct=50.0, diesel_on=False, diesel_run_hours=0, diesel_off_hours=10)
    decision, new_state = decide(site, state, current_hour_load_kw=10.0, solar_available_kw=30.0)

    assert decision.solar_kw == 10.0
    assert decision.diesel_kw == 0.0
    assert not decision.diesel_on
    # Solar surplus should charge the battery
    assert new_state.soc_pct > 50.0


def test_battery_discharges_on_shortfall(site):
    """When solar is insufficient but battery has charge, battery covers the gap."""
    state = MicrogridState(soc_pct=80.0, diesel_on=False, diesel_run_hours=0, diesel_off_hours=10)
    decision, new_state = decide(site, state, current_hour_load_kw=20.0, solar_available_kw=5.0)

    assert decision.solar_kw == 5.0
    assert decision.diesel_kw == 0.0
    assert not decision.diesel_on
    # Battery discharges → negative battery_kw
    assert decision.battery_kw < 0.0
    assert new_state.soc_pct < 80.0


def test_diesel_starts_when_both_exhausted(site):
    """When solar=0 and battery at min SoC, diesel must start."""
    state = MicrogridState(soc_pct=20.0, diesel_on=False, diesel_run_hours=0, diesel_off_hours=10)
    decision, new_state = decide(site, state, current_hour_load_kw=30.0, solar_available_kw=0.0)

    assert decision.solar_kw == 0.0
    # Battery at min SoC, cannot discharge
    assert decision.diesel_on
    assert decision.diesel_kw >= 20.0  # at least min_load_kw
    assert new_state.diesel_on
    assert new_state.diesel_run_hours == 1


def test_cloudy_afternoon_evening_diesel(site):
    """THE key test: sunny morning → full battery → cloudy afternoon depletes it → diesel for evening.

    This reproduces the exact failure mode the whole product exists to fix:
    the greedy controller has no foresight, so it fully charges by late morning
    and then runs diesel when both solar and battery are exhausted.
    """
    state = MicrogridState(soc_pct=50.0, diesel_on=False, diesel_run_hours=0, diesel_off_hours=10)

    # --- Sunny morning (4 hours): lots of solar, moderate load → battery charges to full ---
    for _ in range(4):
        _, state = decide(site, state, current_hour_load_kw=10.0, solar_available_kw=50.0)

    assert state.soc_pct > 90.0, (
        f"Battery should be near-full after 4h of sun, got {state.soc_pct:.1f}%"
    )

    # --- Cloudy afternoon (6 hours): high load, almost no solar → battery drains ---
    for _ in range(6):
        _, state = decide(site, state, current_hour_load_kw=25.0, solar_available_kw=5.0)

    # --- Evening peak: no solar left, battery likely depleted → diesel fires ---
    decision, state = decide(site, state, current_hour_load_kw=30.0, solar_available_kw=0.0)

    assert decision.diesel_on, (
        "Diesel should be running during the evening peak after a cloudy afternoon"
    )
    assert decision.diesel_kw >= 20.0  # at least min_load_kw
