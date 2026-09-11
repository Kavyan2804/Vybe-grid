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
