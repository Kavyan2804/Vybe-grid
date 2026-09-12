import time
from datetime import datetime, timezone

import pyomo.environ as pyo

try:
    from optimizer.domain.entities import DispatchDecision, DispatchPlan
    from optimizer.domain.ports import OptimizerPort
except ImportError:
    DispatchDecision = DispatchPlan = None

    class OptimizerPort:
        pass


class PyomoHighsOptimizerAdapter(OptimizerPort):
    def solve(self, site, forecast, initial_soc_pct=50.0):
        start_time = time.time()
        horizon = min(24, len(forecast.solar_kw), len(forecast.load_kw))
        if horizon != 24:
            raise ValueError("Phase 1 MILP requires a 24-hour forecast horizon")

        battery = site.battery
        diesel = site.diesel_generator
        eta = battery.round_trip_efficiency ** 0.5
        capacity_kwh = battery.capacity_kwh
        soc_min_kwh = capacity_kwh * battery.soc_min_pct / 100.0
        soc_max_kwh = capacity_kwh * battery.soc_max_pct / 100.0
        initial_soc_kwh = capacity_kwh * initial_soc_pct / 100.0

        critical_load = self._series_or_default(site.load.critical_kw, forecast.load_kw, horizon)
        flexible_load = self._series_or_default(site.load.flexible_kw, [0.0] * horizon, horizon)

        model = pyo.ConcreteModel()
        model.T = pyo.RangeSet(0, horizon - 1)
        model.S = pyo.RangeSet(0, horizon)

        model.diesel_on = pyo.Var(model.T, domain=pyo.Binary)
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

        model.initial_soc = pyo.Constraint(expr=model.soc_kwh[0] == initial_soc_kwh)

        def diesel_min_rule(m, t):
            return diesel.min_load_kw * m.diesel_on[t] <= m.diesel_kw[t]

        def diesel_max_rule(m, t):
            return m.diesel_kw[t] <= diesel.max_load_kw * m.diesel_on[t]

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

        def objective_rule(m):
            return sum(
                site.fuel_cost_per_litre
                * (fuel_slope * m.diesel_kw[t] + fuel_intercept * m.diesel_on[t])
                + battery.degradation_cost_per_kwh_cycled * (m.charge_kw[t] + m.discharge_kw[t])
                + flex_penalty * m.unmet_flex_kw[t]
                for t in m.T
            )

        model.objective = pyo.Objective(rule=objective_rule, sense=pyo.minimize)

        results, solver_name = self._solve_model(model)
        solve_time_ms = (time.time() - start_time) * 1000
        termination = str(results.solver.termination_condition).lower()
        if "optimal" not in termination and "feasible" not in termination:
            raise RuntimeError(f"MILP solve failed with termination condition: {termination}")

        decisions = []
        for hour in range(horizon):
            charge_kw = pyo.value(model.charge_kw[hour])
            discharge_kw = pyo.value(model.discharge_kw[hour])
            unmet_flex_kw = pyo.value(model.unmet_flex_kw[hour])
            decisions.append(
                DispatchDecision(
                    hour=hour,
                    solar_kw=round(pyo.value(model.solar_used_kw[hour]), 6),
                    battery_kw=round(charge_kw - discharge_kw, 6),
                    diesel_kw=round(pyo.value(model.diesel_kw[hour]), 6),
                    load_kw=round(critical_load[hour] + flexible_load[hour] - unmet_flex_kw, 6),
                    diesel_on=pyo.value(model.diesel_on[hour]) >= 0.5,
                    soc_pct=round(100.0 * pyo.value(model.soc_kwh[hour + 1]) / capacity_kwh, 6),
                    badges=["FORECAST"],
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

    def _solve_model(self, model):
        last_error = None
        for solver_name in ("appsi_highs", "highs", "glpk"):
            solver = pyo.SolverFactory(solver_name)
            try:
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
