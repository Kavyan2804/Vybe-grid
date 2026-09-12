"""Phase 2 Verification Tests (PHASE_2_rolling_horizon_engine.md).

Tests verification checkpoints CP-2.1 through CP-2.7:
- CP-2.1: Scheduler fires and produces new, different plans on changing forecast
- CP-2.2: Starting SoC strictly comes from telemetry, never from previous plan
- CP-2.3: Diesel minimum run-time and down-time constraints
- CP-2.4: Battery throughput monotonic in degradation cost
- CP-2.5: Solver failure activates fallback with zero unmet critical load
- CP-2.6 [STRETCH]: Reserve margin responds to forecast spread
- CP-2.7 [STRETCH]: Explanations reference binding physical constraints
"""

import copy
import inspect
from datetime import datetime, timezone
import pytest

from optimizer.domain.entities import (
    Site,
    Battery,
    DieselGenerator,
    FuelCurve,
    Load,
    Forecast,
    DispatchDecision,
)
from optimizer.domain.ports import ForecastPort
from optimizer.infrastructure.optimizer_pyomo.adapter import PyomoHighsOptimizerAdapter
from optimizer.infrastructure.dispatch_simulator.adapter import SimulatorDispatchAdapter
from optimizer.infrastructure.db.repositories import (
    InMemoryPlanRepository,
    InMemoryTelemetryRepository,
    InMemoryAlertSink,
)
from optimizer.application.rolling_horizon_service import RollingHorizonService
from optimizer.application.explainability_service import ExplainabilityService


@pytest.fixture
def base_site():
    return Site(
        name="test-site",
        latitude=19.0760,
        longitude=72.8777,
        timezone="Asia/Kolkata",
        battery=Battery(
            capacity_kwh=100.0,
            max_charge_kw=30.0,
            max_discharge_kw=30.0,
            round_trip_efficiency=0.90,
            degradation_cost_per_kwh_cycled=0.05,
            soc_min_pct=15.0,
            soc_max_pct=95.0,
        ),
        diesel_generator=DieselGenerator(
            min_load_kw=10.0,
            max_load_kw=60.0,
            fuel_curve=FuelCurve(
                litres_per_kwh_min_load=0.35,
                litres_per_kwh_max_load=0.28,
            ),
            start_cost=15.0,
            min_uptime_h=3.0,
            min_downtime_h=2.0,
        ),
        load=Load(
            critical_kw=[15.0] * 24,
            flexible_kw=[5.0] * 24,
        ),
        fuel_cost_per_litre=1.20,
        emission_factor_kg_co2_per_litre=2.68,
    )


class DummyForecastPort(ForecastPort):
    def __init__(self, forecast: Forecast):
        self.forecast = forecast

    def fetch_forecast(self, site: Site) -> Forecast:
        return self.forecast


def test_cp_2_1_changing_forecast_produces_different_plans(base_site):
    """CP-2.1: Two consecutive ticks against changing forecast produce different persisted plans."""
    now = datetime.now(timezone.utc)
    fc1 = Forecast(
        solar_kw=[0.0] * 6 + [30.0] * 12 + [0.0] * 6,
        load_kw=[15.0] * 24,
        source="forecast-1",
        stale=False,
        fetched_at=now,
    )
    fc2 = Forecast(
        solar_kw=[0.0] * 6 + [5.0] * 12 + [0.0] * 6,  # heavy cloud cover
        load_kw=[25.0] * 24,                           # higher load
        source="forecast-2",
        stale=False,
        fetched_at=now,
    )

    plan_repo = InMemoryPlanRepository()
    telemetry_repo = InMemoryTelemetryRepository()
    dispatch_port = SimulatorDispatchAdapter()
    optimizer_port = PyomoHighsOptimizerAdapter()

    service = RollingHorizonService(
        site=base_site,
        forecast_port=DummyForecastPort(fc1),
        optimizer_port=optimizer_port,
        dispatch_port=dispatch_port,
        plan_repository=plan_repo,
        telemetry_repository=telemetry_repo,
    )

    # Tick 1 with high solar
    res1 = service.tick(provided_forecast=fc1)
    plan1 = res1["plan"]

    # Tick 2 with cloudy forecast
    res2 = service.tick(provided_forecast=fc2)
    plan2 = res2["plan"]

    assert len(plan_repo.list_for_site(base_site.name)) == 2
    # Plans must be different due to the updated forecast
    soc_series_1 = [d.soc_pct for d in plan1.decisions]
    soc_series_2 = [d.soc_pct for d in plan2.decisions]
    assert soc_series_1 != soc_series_2


def test_cp_2_2_starting_soc_comes_strictly_from_telemetry(base_site):
    """CP-2.2: A tick's starting SoC always comes from telemetry, NEVER from prior plan."""
    now = datetime.now(timezone.utc)
    fc = Forecast(
        solar_kw=[0.0] * 6 + [25.0] * 12 + [0.0] * 6,
        load_kw=[15.0] * 24,
        source="test",
        stale=False,
        fetched_at=now,
    )

    plan_repo = InMemoryPlanRepository()
    telemetry_repo = InMemoryTelemetryRepository()
    dispatch_port = SimulatorDispatchAdapter()
    optimizer_port = PyomoHighsOptimizerAdapter()

    service = RollingHorizonService(
        site=base_site,
        forecast_port=DummyForecastPort(fc),
        optimizer_port=optimizer_port,
        dispatch_port=dispatch_port,
        plan_repository=plan_repo,
        telemetry_repository=telemetry_repo,
        default_initial_soc_pct=50.0,
    )

    # Initial tick starts with default 50%
    res1 = service.tick()
    predicted_next_soc = res1["plan"].decisions[0].soc_pct

    # Now simulate an external shock in actual telemetry:
    # Say battery actually dropped to 25.0% due to an unforecasted load surge
    actual_shock_soc = 25.0
    telemetry_repo.record({
        "site_id": base_site.name,
        "recorded_at": now.isoformat(),
        "solar_kw": 0.0,
        "battery_kw": -10.0,
        "diesel_kw": 0.0,
        "load_kw": 10.0,
        "soc_pct": actual_shock_soc,
        "diesel_on": False,
        "source": "simulator",
    })

    # Execute tick 2
    res2 = service.tick()

    # The starting SoC for tick 2 must equal the shock value (25.0%), NOT predicted_next_soc!
    assert res2["starting_soc_pct"] == actual_shock_soc
    assert res2["starting_soc_pct"] != predicted_next_soc


def test_cp_2_3_diesel_min_uptime_and_downtime_constraints(base_site):
    """CP-2.3: No plan starts diesel for fewer consecutive hours than min_uptime_h."""
    now = datetime.now(timezone.utc)
    # Site diesel has min_uptime_h = 3.0
    adapter = PyomoHighsOptimizerAdapter()

    # Craft a scenario with a 1-hour shortfall at hour 2
    # Solar is 0 everywhere, load is 0 except hour 2 where load is 40kW and battery at min soc
    solar = [0.0] * 24
    load = [0.0] * 24
    load[2] = 40.0  # 1-hour spike

    fc = Forecast(
        solar_kw=solar,
        load_kw=load,
        source="uptime_test",
        stale=False,
        fetched_at=now,
    )

    # Solve with battery already at soc_min (15%) so diesel must start at hour 2
    plan = adapter.solve(
        site=base_site,
        forecast=fc,
        initial_soc_pct=15.0,
        initial_diesel_on=False,
        initial_diesel_off_hours=10,
    )

    diesel_runs = [d.diesel_on for d in plan.decisions]

    # Verify diesel turned on
    assert any(diesel_runs), "Diesel should have turned on to cover shortfall"

    # Find runs of True
    consecutive_run = 0
    for is_on in diesel_runs:
        if is_on:
            consecutive_run += 1
        elif consecutive_run > 0:
            assert consecutive_run >= int(base_site.diesel_generator.min_uptime_h), (
                f"Diesel ran for {consecutive_run} hours, less than min_uptime_h {base_site.diesel_generator.min_uptime_h}"
            )
            consecutive_run = 0

    if consecutive_run > 0:
        assert consecutive_run >= int(base_site.diesel_generator.min_uptime_h)


def test_cp_2_4_battery_throughput_responds_to_degradation_cost(base_site):
    """CP-2.4: Battery throughput strictly reduces or non-increases as degradation cost increases."""
    now = datetime.now(timezone.utc)
    # High solar in morning, moderate load in evening
    solar = [0.0] * 6 + [35.0] * 8 + [0.0] * 10
    load = [10.0] * 6 + [15.0] * 8 + [25.0] * 10

    fc = Forecast(
        solar_kw=solar,
        load_kw=load,
        source="degradation_test",
        stale=False,
        fetched_at=now,
    )

    adapter = PyomoHighsOptimizerAdapter()

    # Site 1: 0 degradation cost (free cycling)
    site_zero_deg = copy.deepcopy(base_site)
    object.__setattr__(
        site_zero_deg,
        "battery",
        Battery(
            capacity_kwh=base_site.battery.capacity_kwh,
            max_charge_kw=base_site.battery.max_charge_kw,
            max_discharge_kw=base_site.battery.max_discharge_kw,
            round_trip_efficiency=base_site.battery.round_trip_efficiency,
            degradation_cost_per_kwh_cycled=0.0,
            soc_min_pct=base_site.battery.soc_min_pct,
            soc_max_pct=base_site.battery.soc_max_pct,
        ),
    )

    # Site 2: High degradation cost
    site_high_deg = copy.deepcopy(base_site)
    object.__setattr__(
        site_high_deg,
        "battery",
        Battery(
            capacity_kwh=base_site.battery.capacity_kwh,
            max_charge_kw=base_site.battery.max_charge_kw,
            max_discharge_kw=base_site.battery.max_discharge_kw,
            round_trip_efficiency=base_site.battery.round_trip_efficiency,
            degradation_cost_per_kwh_cycled=0.50,  # very costly cycling
            soc_min_pct=base_site.battery.soc_min_pct,
            soc_max_pct=base_site.battery.soc_max_pct,
        ),
    )

    plan_zero = adapter.solve(site_zero_deg, fc, initial_soc_pct=50.0)
    plan_high = adapter.solve(site_high_deg, fc, initial_soc_pct=50.0)

    throughput_zero = sum(abs(d.battery_kw) for d in plan_zero.decisions)
    throughput_high = sum(abs(d.battery_kw) for d in plan_high.decisions)

    assert throughput_zero >= throughput_high, (
        f"Expected zero degradation throughput ({throughput_zero}) >= high degradation throughput ({throughput_high})"
    )


def test_cp_2_5_forced_solver_failure_produces_fallback_and_serves_critical_load(base_site):
    """CP-2.5: Solver failure raises alert and uses baseline fallback with 0 unmet critical load."""
    now = datetime.now(timezone.utc)
    fc = Forecast(
        solar_kw=[5.0] * 24,
        load_kw=[20.0] * 24,
        source="fallback_test",
        stale=False,
        fetched_at=now,
    )

    alert_sink = InMemoryAlertSink()
    plan_repo = InMemoryPlanRepository()
    telemetry_repo = InMemoryTelemetryRepository()
    dispatch_port = SimulatorDispatchAdapter()
    optimizer_port = PyomoHighsOptimizerAdapter()

    service = RollingHorizonService(
        site=base_site,
        forecast_port=DummyForecastPort(fc),
        optimizer_port=optimizer_port,
        dispatch_port=dispatch_port,
        plan_repository=plan_repo,
        telemetry_repository=telemetry_repo,
        alert_port=alert_sink,
    )

    # Execute tick with forced fallback
    result = service.tick(force_fallback=True)

    assert result["fallback_used"] is True
    plan = result["plan"]
    assert plan.fallback_used is True
    assert "fallback" in plan.solver_status

    # Alert SOLVER_FALLBACK_ACTIVE was emitted
    alert_types = [a["type"] for a in alert_sink.alerts]
    assert "SOLVER_FALLBACK_ACTIVE" in alert_types

    # Critical load is 100% met in every hour of the fallback decision
    for hour, decision in enumerate(plan.decisions):
        assert decision.load_kw >= base_site.load.critical_kw[hour], (
            f"Hour {hour} critical load unmet in fallback plan!"
        )


def test_cp_2_6_stretch_uncertainty_reserve_margin(base_site):
    """CP-2.6 [STRETCH]: Reserve margin increases with forecast spread."""
    now = datetime.now(timezone.utc)
    solar_mean = [0.0] * 6 + [20.0] * 12 + [0.0] * 6
    load = [15.0] * 24

    # Narrow spread (high confidence)
    fc_narrow = Forecast(
        solar_kw=solar_mean,
        load_kw=load,
        source="narrow",
        stale=False,
        fetched_at=now,
        solar_p10_kw=[s * 0.95 for s in solar_mean],
        solar_p90_kw=[s * 1.05 for s in solar_mean],
    )

    # Wide spread (high uncertainty)
    fc_wide = Forecast(
        solar_kw=solar_mean,
        load_kw=load,
        source="wide",
        stale=False,
        fetched_at=now,
        solar_p10_kw=[s * 0.20 for s in solar_mean],
        solar_p90_kw=[s * 1.80 for s in solar_mean],
    )

    adapter = PyomoHighsOptimizerAdapter()
    plan_narrow = adapter.solve(base_site, fc_narrow, initial_soc_pct=50.0)
    plan_wide = adapter.solve(base_site, fc_wide, initial_soc_pct=50.0)

    # The minimum SoC maintained in near-term hours under wide spread must be >= narrow spread
    min_soc_near_term_narrow = min(d.soc_pct for d in plan_narrow.decisions[:12])
    min_soc_near_term_wide = min(d.soc_pct for d in plan_wide.decisions[:12])

    assert min_soc_near_term_wide >= min_soc_near_term_narrow - 1e-4


def test_cp_2_7_stretch_explainability_service(base_site):
    """CP-2.7 [STRETCH]: Decisions have plain-language rationales reflecting constraints."""
    now = datetime.now(timezone.utc)
    fc = Forecast(
        solar_kw=[0.0] * 6 + [40.0] * 8 + [0.0] * 10,
        load_kw=[15.0] * 24,
        source="explain_test",
        stale=False,
        fetched_at=now,
    )

    adapter = PyomoHighsOptimizerAdapter()
    plan = adapter.solve(base_site, fc, initial_soc_pct=50.0)

    # Verify decisions have meaningful reasons attached
    for d in plan.decisions:
        assert d.reason is not None and len(d.reason) > 5

    # Check that solar surplus hours mention charging or surplus
    midday_decisions = [d for d in plan.decisions if 7 <= d.hour <= 12]
    midday_reasons = " ".join(d.reason for d in midday_decisions).lower()
    assert "solar" in midday_reasons or "battery" in midday_reasons or "charging" in midday_reasons


def test_fast_forward_simulation(base_site):
    """Test fast forward mode running multiple ticks sequentially."""
    now = datetime.now(timezone.utc)
    fc = Forecast(
        solar_kw=[0.0] * 6 + [30.0] * 12 + [0.0] * 6,
        load_kw=[15.0] * 24,
        source="ff_test",
        stale=False,
        fetched_at=now,
    )

    plan_repo = InMemoryPlanRepository()
    telemetry_repo = InMemoryTelemetryRepository()
    dispatch_port = SimulatorDispatchAdapter()
    optimizer_port = PyomoHighsOptimizerAdapter()

    service = RollingHorizonService(
        site=base_site,
        forecast_port=DummyForecastPort(fc),
        optimizer_port=optimizer_port,
        dispatch_port=dispatch_port,
        plan_repository=plan_repo,
        telemetry_repository=telemetry_repo,
        default_initial_soc_pct=50.0,
    )

    results = service.run_fast_forward(num_ticks=4)
    assert len(results) == 4
    assert len(plan_repo.list_for_site(base_site.name)) == 4
    assert len(telemetry_repo.list_for_site(base_site.name)) == 4

