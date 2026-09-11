import time
import pyomo.environ as pyo

try:
    from optimizer.domain.ports import OptimizerPort
except ImportError:
    class OptimizerPort:
        pass

class PyomoHighsOptimizerAdapter(OptimizerPort):
    def solve(self, site, forecast):
        raise NotImplementedError('MILP formulation not yet implemented — Phase 2')
        
    def _smoke_test(self):
        start_time = time.time()
        
        model = pyo.ConcreteModel()
        model.x = pyo.Var(domain=pyo.NonNegativeReals)
        model.y = pyo.Var(domain=pyo.NonNegativeReals)
        
        model.obj = pyo.Objective(expr=model.x + model.y, sense=pyo.minimize)
        model.con = pyo.Constraint(expr=model.x + model.y >= 10)
        
        solver = pyo.SolverFactory('appsi_highs')
        try:
            results = solver.solve(model)
        except Exception:
            solver = pyo.SolverFactory('highs')
            try:
                results = solver.solve(model)
            except Exception:
                solver = pyo.SolverFactory('glpk')
                results = solver.solve(model)
                
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
        
        solver = pyo.SolverFactory('appsi_highs')
        try:
            solver.solve(model)
        except Exception:
            try:
                solver = pyo.SolverFactory('highs')
                solver.solve(model)
            except Exception:
                solver = pyo.SolverFactory('glpk')
                solver.solve(model)
                
        solve_time_ms = (time.time() - start_time) * 1000
        
        return pyo.value(model.obj), solve_time_ms
