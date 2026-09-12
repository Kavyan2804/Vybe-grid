import time
from datetime import datetime, timezone
from typing import Optional, List, Tuple

import pyomo.environ as pyo

try:
    from optimizer.domain.entities import DispatchDecision, DispatchPlan
    from optimizer.domain.ports import OptimizerPort
except ImportError:
    DispatchDecision = DispatchPlan = None

    class OptimizerPort:
        pass


class PyomoHighsOptimizerAdapter(OptimizerPort):
    def solve(
        self,
        site,
        forecast,
        initial_soc_pct: float = 50.0,
        initial_diesel_on: bool = False,
        initial_diesel_run_hours: int = 0,
        initial_diesel_off_hours: int = 10,
        solver_timeout_seconds: float = 20.0,
    ) -> DispatchPlan:
        start_time = time.time()
        horizon = min(24, len(forecast.solar_kw), len(forecast.load_kw))
        if horizon != 24:
            raise ValueError("Phase 2 MILP requires a 24-hour forecast horizon")

        battery = site.battery
        diesel = site.diesel_generator
        eta = battery.round_trip_efficiency ** 0.5
        capacity_kwh = battery.capacity_kwh
        soc_min_kwh = capacity_kwh * battery.soc_min_pct / 100.0
        soc_max_kwh = capacity_kwh * battery.soc_max_pct / 100.0
        initial_soc_kwh = max(soc_min_kwh, min(soc_max_kwh, capacity_kwh * initial_soc_pct / 100.0))

        critical_load = self._series_or_default(site.load.critical_kw, forecast.load_kw, horizon)
        flexible_load = self._series_or_default(site.load.flexible_kw, [0.0] * horizon, horizon)

        # Forecast-uncertainty reserve margin (Task 2.5 [STRETCH])
        # If solar P10 and P90 are available, raise soc_min near-term proportionally to spread
        soc_min_dynamic_kwh = [soc_min_kwh] * (horizon + 1)
        if getattr(forecast, "solar_p10_kw", None) and getattr(forecast, "solar_p90_kw", None):
            p10 = forecast.solar_p10_kw[:horizon]
            p90 = forecast.solar_p90_kw[:horizon]
            spreads = [max(0.0, float(h90) - float(h10)) for h10, h90 in zip(p10, p90)]
            if spreads:
                avg_spread = sum(spreads[:12]) / min(12, len(spreads))
                # Reserve scales with spread, capped so it stays below soc_max
                reserve_kwh = min(0.3 * (soc_max_kwh - soc_min_kwh), avg_spread * 0.5)
                for t in range(min(12, horizon + 1)):
                    soc_min_dynamic_kwh[t] = min(soc_max_kwh - 1e-3, soc_min_kwh + reserve_kwh)

        model = pyo.ConcreteModel()
        model.T = pyo.RangeSet(0, horizon - 1)
        model.S = pyo.RangeSet(0, horizon)

        # Decision variables
        model.diesel_on = pyo.Var(model.T, domain=pyo.Binary)
        model.diesel_start = pyo.Var(model.T, domain=pyo.Binary)
        model.diesel_stop = pyo.Var(model.T, domain=pyo.Binary)
        model.diesel_kw = pyo.Var(model.T, domain=pyo.NonNegativeReals, bounds=(0.0, diesel.max_load_kw))
        model.charge_kw = pyo.Var(
            model.T, domain=pyo.NonNegativeReals, bounds=(0.0, battery.max_charge_kw)
        )
        model.discharge_kw = pyo.Var(
            model.T, domain=pyo.NonNegativeReals, bounds=(0.0, battery.max_discharge_kw)
        )
        model.battery_charging = pyo.Var(model.T, domain=pyo.Binary)
        model.soc_kwh = pyo.Var(model.S, domain=pyo.NonNegativeReals, bounds=(soc_min_kwh, soc_max_kwh))
        model.solar_used_kw = pyo.Var(model.T, domain=pyo.NonNegativeReals)
        model.unmet_flex_kw = pyo.Var(model.T, domain=pyo.NonNegativeReals)

        # Initial SoC constraint
        model.initial_soc = pyo.Constraint(expr=model.soc_kwh[0] == initial_soc_kwh)

        # Dynamic SoC reserve constraint (supports uncertainty margin)
        def soc_min_dynamic_rule(m, s):
            return m.soc_kwh[s] >= soc_min_dynamic_kwh[s]
        model.soc_min_dynamic = pyo.Constraint(model.S, rule=soc_min_dynamic_rule)

        # Diesel min/max load when on
        def diesel_min_rule(m, t):
            return diesel.min_load_kw * m.diesel_on[t] <= m.diesel_kw[t]

        def diesel_max_rule(m, t):
            return m.diesel_kw[t] <= diesel.max_load_kw * m.diesel_on[t]

        # Diesel start/stop transition dynamics (Task 2.2)
        def diesel_start_rule(m, t):
            if t == 0:
                prev_on = 1.0 if initial_diesel_on else 0.0
                return m.diesel_start[0] >= m.diesel_on[0] - prev_on
            return m.diesel_start[t] >= m.diesel_on[t] - m.diesel_on[t - 1]

        def diesel_stop_rule(m, t):
            if t == 0:
                prev_on = 1.0 if initial_diesel_on else 0.0
                return m.diesel_stop[0] >= prev_on - m.diesel_on[0]
            return m.diesel_stop[t] >= m.diesel_on[t - 1] - m.diesel_on[t]

        model.diesel_start_con = pyo.Constraint(model.T, rule=diesel_start_rule)
        model.diesel_stop_con = pyo.Constraint(model.T, rule=diesel_stop_rule)

        # Diesel minimum uptime constraints (Task 2.2)
        min_uptime = max(1, int(round(diesel.min_uptime_h)))
        min_downtime = max(1, int(round(diesel.min_downtime_h)))

        uptime_constraints = {}
        for t in range(horizon):
            end_t = min(horizon, t + min_uptime)
            for tau in range(t, end_t):
                uptime_constraints[(t, tau)] = (t, tau)

        def min_uptime_rule(m, t, tau):
            return m.diesel_on[tau] >= m.diesel_start[t]

        model.min_uptime_set = pyo.Set(dimen=2, initialize=list(uptime_constraints.keys()))
        model.min_uptime_con = pyo.Constraint(model.min_uptime_set, rule=min_uptime_rule)

        # Diesel minimum downtime constraints (Task 2.2)
        downtime_constraints = {}
        for t in range(horizon):
            end_t = min(horizon, t + min_downtime)
            for tau in range(t, end_t):
                downtime_constraints[(t, tau)] = (t, tau)

        def min_downtime_rule(m, t, tau):
            return 1 - m.diesel_on[tau] >= m.diesel_stop[t]

        model.min_downtime_set = pyo.Set(dimen=2, initialize=list(downtime_constraints.keys()))
        model.min_downtime_con = pyo.Constraint(model.min_downtime_set, rule=min_downtime_rule)

        # Initial run/off hours carry-over
        if initial_diesel_on and initial_diesel_run_hours < min_uptime:
            rem_uptime = min(horizon, min_uptime - initial_diesel_run_hours)
            for t in range(rem_uptime):
                model.add_component(f"initial_uptime_{t}", pyo.Constraint(expr=model.diesel_on[t] == 1))
        elif (not initial_diesel_on) and initial_diesel_off_hours < min_downtime:
            rem_downtime = min(horizon, min_downtime - initial_diesel_off_hours)
            for t in range(rem_downtime):
                model.add_component(f"initial_downtime_{t}", pyo.Constraint(expr=model.diesel_on[t] == 0))

        def charge_gate_rule(m, t):
            return m.charge_kw[t] <= battery.max_charge_kw * m.battery_charging[t]

        def discharge_gate_rule(m, t):
            return m.discharge_kw[t] <= battery.max_discharge_kw * (1 - m.battery_charging[t])

        def solar_limit_rule(m, t):
            return m.solar_used_kw[t] <= forecast.solar_kw[t]

        def unmet_flex_limit_rule(m, t):
            return m.unmet_flex_kw[t] <= flexible_load[t]

        def soc_rule(m, t):
            return (
                m.soc_kwh[t + 1]
                == m.soc_kwh[t] + m.charge_kw[t] * eta - m.discharge_kw[t] / eta
            )

        def energy_balance_rule(m, t):
            return (
                m.solar_used_kw[t] + m.discharge_kw[t] + m.diesel_kw[t]
                == critical_load[t] + flexible_load[t] - m.unmet_flex_kw[t] + m.charge_kw[t]
            )

        model.diesel_min = pyo.Constraint(model.T, rule=diesel_min_rule)
        model.diesel_max = pyo.Constraint(model.T, rule=diesel_max_rule)
        model.charge_gate = pyo.Constraint(model.T, rule=charge_gate_rule)
        model.discharge_gate = pyo.Constraint(model.T, rule=discharge_gate_rule)
        model.solar_limit = pyo.Constraint(model.T, rule=solar_limit_rule)
        model.unmet_flex_limit = pyo.Constraint(model.T, rule=unmet_flex_limit_rule)
        model.soc_dynamics = pyo.Constraint(model.T, rule=soc_rule)
        model.energy_balance = pyo.Constraint(model.T, rule=energy_balance_rule)

        fuel_litres_per_hour_at_min = diesel.min_load_kw * diesel.fuel_curve.litres_per_kwh_min_load
        fuel_litres_per_hour_at_max = diesel.max_load_kw * diesel.fuel_curve.litres_per_kwh_max_load
        if diesel.max_load_kw > diesel.min_load_kw:
            fuel_slope = (
                fuel_litres_per_hour_at_max - fuel_litres_per_hour_at_min
            ) / (diesel.max_load_kw - diesel.min_load_kw)
        else:
            fuel_slope = diesel.fuel_curve.litres_per_kwh_max_load
        fuel_intercept = fuel_litres_per_hour_at_min - fuel_slope * diesel.min_load_kw
        flex_penalty = self._flex_penalty(site)

        # Objective: fuel consumption + start cost + battery degradation + flex penalty (Task 2.2 & 2.3)
        def objective_rule(m):
            return sum(
                site.fuel_cost_per_litre
                * (fuel_slope * m.diesel_kw[t] + fuel_intercept * m.diesel_on[t])
                + diesel.start_cost * m.diesel_start[t]
                + battery.degradation_cost_per_kwh_cycled * (m.charge_kw[t] + m.discharge_kw[t])
                + flex_penalty * m.unmet_flex_kw[t]
                for t in m.T
            )

        model.objective = pyo.Objective(rule=objective_rule, sense=pyo.minimize)

        results, solver_name = self._solve_model(model, timeout_seconds=solver_timeout_seconds)
        solve_time_ms = (time.time() - start_time) * 1000
        termination = str(results.solver.termination_condition).lower()
        if "optimal" not in termination and "feasible" not in termination:
            raise RuntimeError(f"MILP solve failed with termination condition: {termination}")

        decisions = []
        for hour in range(horizon):
            charge_kw = pyo.value(model.charge_kw[hour])
            discharge_kw = pyo.value(model.discharge_kw[hour])
            unmet_flex_kw = pyo.value(model.unmet_flex_kw[hour])
            d_on = pyo.value(model.diesel_on[hour]) >= 0.5
            d_kw = round(pyo.value(model.diesel_kw[hour]), 6)
            s_used = round(pyo.value(model.solar_used_kw[hour]), 6)
            b_kw = round(charge_kw - discharge_kw, 6)

            # Generate plain-language reason for explainability (Task 2.6 [STRETCH])
            reason = self._generate_reason(
                hour=hour,
                solar_used=s_used,
                solar_forecast=forecast.solar_kw[hour],
                battery_kw=b_kw,
                diesel_on=d_on,
                diesel_kw=d_kw,
                min_uptime=min_uptime,
                model=model,
            )

            decisions.append(
                DispatchDecision(
                    hour=hour,
                    solar_kw=s_used,
                    battery_kw=b_kw,
                    diesel_kw=d_kw,
                    load_kw=round(critical_load[hour] + flexible_load[hour] - unmet_flex_kw, 6),
                    diesel_on=d_on,
                    soc_pct=round(100.0 * pyo.value(model.soc_kwh[hour + 1]) / capacity_kwh, 6),
                    badges=["FORECAST"],
                    reason=reason,
                )
            )

        forecast_id = f"{forecast.source}:{forecast.fetched_at.isoformat()}"
        return DispatchPlan(
            site_id=site.name,
            forecast_id=forecast_id,
            decisions=decisions,
            created_at=datetime.now(timezone.utc),
            solver_status=f"{solver_name}:{termination}",
            solve_time_ms=solve_time_ms,
            fallback_used=False,
        )

    def _generate_reason(
        self,
        hour: int,
        solar_used: float,
        solar_forecast: float,
        battery_kw: float,
        diesel_on: bool,
        diesel_kw: float,
        min_uptime: int,
        model,
    ) -> str:
        """Produce an explainable one-line rationale for the decision at hour (Task 2.6)."""
        is_start = False
        try:
            is_start = pyo.value(model.diesel_start[hour]) >= 0.5
        except Exception:
            pass

        if diesel_on:
            if is_start:
                return f"Diesel started at {diesel_kw:.1f} kW to serve load shortfall (min uptime: {min_uptime}h)"
            return f"Diesel running at {diesel_kw:.1f} kW maintaining generator commitment"
        if battery_kw > 0.1:
            surplus = solar_forecast - solar_used
            return f"Solar surplus ({surplus:.1f} kW) charging battery at {battery_kw:.1f} kW"
        if battery_kw < -0.1:
            return f"Battery discharging at {abs(battery_kw):.1f} kW avoiding diesel start"
        if solar_used > 0.1:
            return f"Load served directly by solar generation ({solar_used:.1f} kW)"
        return "Idle — system in balance, diesel off"

    @staticmethod
    def _series_or_default(series, default, horizon):
        values = list(series) if series else list(default)
        if len(values) < horizon:
            raise ValueError("site load series must cover the 24-hour optimization horizon")
        return [float(value) for value in values[:horizon]]

    @staticmethod
    def _flex_penalty(site):
        max_fuel_cost = (
            site.diesel_generator.fuel_curve.litres_per_kwh_min_load * site.fuel_cost_per_litre
        )
        return max(10.0, max_fuel_cost * 100.0)

    def _solve_model(self, model, timeout_seconds: float = 20.0):
        last_error = None
        for solver_name in ("appsi_highs", "highs", "glpk"):
            try:
                solver = pyo.SolverFactory(solver_name)
                if solver is None or not solver.available():
                    continue
                # Set solver timeout where supported
                try:
                    if hasattr(solver, "config") and hasattr(solver.config, "time_limit"):
                        solver.config.time_limit = float(timeout_seconds)
                    else:
                        solver.options["time_limit"] = float(timeout_seconds)
                except Exception:
                    pass
                return solver.solve(model), solver_name
            except Exception as exc:
                last_error = exc
        raise RuntimeError("No configured MILP solver could solve the model") from last_error

    def _smoke_test(self):
        start_time = time.time()

        model = pyo.ConcreteModel()
        model.x = pyo.Var(domain=pyo.NonNegativeReals)
        model.y = pyo.Var(domain=pyo.NonNegativeReals)

        model.obj = pyo.Objective(expr=model.x + model.y, sense=pyo.minimize)
        model.con = pyo.Constraint(expr=model.x + model.y >= 10)

        self._solve_model(model)

        solve_time_ms = (time.time() - start_time) * 1000

        return pyo.value(model.obj), solve_time_ms

    def _smoke_test_larger(self):
        start_time = time.time()

        model = pyo.ConcreteModel()
        model.V = pyo.Set(initialize=range(24))
        model.x = pyo.Var(model.V, domain=pyo.NonNegativeReals)

        def obj_rule(m):
            return sum(m.x[i] for i in m.V)

        model.obj = pyo.Objective(rule=obj_rule, sense=pyo.minimize)

        def con_rule(m, i):
            return m.x[i] >= i

        model.con = pyo.Constraint(model.V, rule=con_rule)

        self._solve_model(model)

        solve_time_ms = (time.time() - start_time) * 1000

        return pyo.value(model.obj), solve_time_ms
