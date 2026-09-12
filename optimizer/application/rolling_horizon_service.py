"""Rolling Horizon Service (ARCHITECTURE.md §3, §4, §7).

Orchestrates the hourly optimization loop:
1. Fetch latest forecast
2. Read measured starting SoC from telemetry (NEVER from previous plan's own prediction)
3. Solve 24-hour MILP with up/down-time and degradation constraints
4. On timeout or infeasibility, trigger fallback path (SOLVER_FALLBACK_ACTIVE + baseline rule)
5. Persist plan to PlanRepository
6. Hand hour 0 decision to DispatchPort
7. Record actual telemetry to TelemetryRepository
8. Supports --fast-forward mode for backtesting and fast simulations
"""

import time
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Callable

from optimizer.domain.entities import Site, Forecast, DispatchDecision, DispatchPlan
from optimizer.domain.ports import (
    ForecastPort,
    OptimizerPort,
    DispatchPort,
    PlanRepository,
    TelemetryRepository,
    AlertPort,
)
from optimizer.application.baseline_service import decide as baseline_decide, MicrogridState


class RollingHorizonService:
    """Core application orchestrator for rolling-horizon microgrid dispatch."""

    def __init__(
        self,
        site: Site,
        forecast_port: ForecastPort,
        optimizer_port: OptimizerPort,
        dispatch_port: DispatchPort,
        plan_repository: PlanRepository,
        telemetry_repository: TelemetryRepository,
        alert_port: Optional[AlertPort] = None,
        default_initial_soc_pct: float = 50.0,
        solve_timeout_seconds: float = 20.0,
    ) -> None:
        self.site = site
        self.forecast_port = forecast_port
        self.optimizer_port = optimizer_port
        self.dispatch_port = dispatch_port
        self.plan_repository = plan_repository
        self.telemetry_repository = telemetry_repository
        self.alert_port = alert_port
        self.default_initial_soc_pct = default_initial_soc_pct
        self.solve_timeout_seconds = solve_timeout_seconds

        # Shadow baseline state tracked alongside the rolling horizon
        self._baseline_state = MicrogridState(
            soc_pct=default_initial_soc_pct,
            diesel_on=False,
            diesel_run_hours=0,
            diesel_off_hours=10,
        )

    def tick(
        self,
        force_fallback: bool = False,
        provided_forecast: Optional[Forecast] = None,
    ) -> Dict[str, Any]:
        """Execute a single rolling-horizon tick end to end.

        ARCHITECTURE.md §3, §4:
        Starting SoC MUST come from telemetry, never from the previous plan's prediction.
        """
        # 1. Fetch forecast (or use provided scenario forecast)
        forecast = provided_forecast or self.forecast_port.fetch_forecast(self.site)

        # 2. Read latest actual SoC from telemetry (CP-2.2)
        telemetry_soc = self.telemetry_repository.latest_soc(self.site.name)
        starting_soc_pct = (
            telemetry_soc if telemetry_soc is not None else self.default_initial_soc_pct
        )

        plan: DispatchPlan
        fallback_used = False

        # 3. Attempt optimization solve, with fallback protection (CP-2.5)
        if force_fallback:
            plan = self._build_fallback_plan(forecast, starting_soc_pct, reason="forced_fallback")
            fallback_used = True
        else:
            try:
                plan = self.optimizer_port.solve(
                    site=self.site,
                    forecast=forecast,
                    initial_soc_pct=starting_soc_pct,
                    solver_timeout_seconds=self.solve_timeout_seconds,
                )
            except Exception as exc:
                # Task 2.4: Fallback path on timeout or infeasibility
                fallback_used = True
                plan = self._build_fallback_plan(
                    forecast, starting_soc_pct, reason=f"solver_failure: {exc}"
                )

        # 4. Persist plan to PlanRepository
        self.plan_repository.save(plan)

        # 5. Execute hour 0 decision via DispatchPort
        hour_0_decision = plan.decisions[0]
        actual_telemetry = self.dispatch_port.execute(
            site=self.site,
            decision=hour_0_decision,
            current_soc_pct=starting_soc_pct,
        )

        # 6. Record actual telemetry
        self.telemetry_repository.record(actual_telemetry)

        # 7. Run shadow baseline for comparison
        hour_0_load = forecast.load_kw[0] if forecast.load_kw else 10.0
        hour_0_solar = forecast.solar_kw[0] if forecast.solar_kw else 0.0
        baseline_decision, self._baseline_state = baseline_decide(
            site=self.site,
            state=self._baseline_state,
            current_hour_load_kw=hour_0_load,
            solar_available_kw=hour_0_solar,
        )

        return {
            "plan": plan,
            "telemetry": actual_telemetry,
            "starting_soc_pct": starting_soc_pct,
            "fallback_used": fallback_used,
            "baseline_decision": baseline_decision,
        }

    def _build_fallback_plan(
        self,
        forecast: Forecast,
        current_soc_pct: float,
        reason: str,
    ) -> DispatchPlan:
        """Construct a safe fallback plan using the greedy baseline rule (Task 2.4).

        Guarantees critical load is never dropped (unmet critical load = 0).
        Raises SOLVER_FALLBACK_ACTIVE alert.
        """
        if self.alert_port is not None:
            self.alert_port.emit(
                alert_type="SOLVER_FALLBACK_ACTIVE",
                subject=f"Optimizer solver fallback invoked for {self.site.name}",
                payload={"reason": reason, "site_id": self.site.name},
            )

        # Run greedy controller across the forecast horizon to produce a safe 24h plan
        decisions: List[DispatchDecision] = []
        state = MicrogridState(
            soc_pct=current_soc_pct,
            diesel_on=False,
            diesel_run_hours=0,
            diesel_off_hours=10,
        )

        horizon = min(24, len(forecast.solar_kw), len(forecast.load_kw))
        for h in range(horizon):
            load_h = forecast.load_kw[h]
            solar_h = forecast.solar_kw[h]
            dec, state = baseline_decide(self.site, state, load_h, solar_h)
            decisions.append(
                DispatchDecision(
                    hour=h,
                    solar_kw=dec.solar_kw,
                    battery_kw=dec.battery_kw,
                    diesel_kw=dec.diesel_kw,
                    load_kw=dec.load_kw,
                    diesel_on=dec.diesel_on,
                    soc_pct=dec.soc_pct,
                    badges=["BASELINE", "SIMULATED"],
                    reason=f"Fallback rule: {reason}",
                )
            )

        return DispatchPlan(
            site_id=self.site.name,
            forecast_id=f"fallback:{forecast.source}:{datetime.now(timezone.utc).isoformat()}",
            decisions=decisions,
            created_at=datetime.now(timezone.utc),
            solver_status="fallback:greedy_baseline",
            solve_time_ms=0.0,
            fallback_used=True,
        )

    def run_fast_forward(
        self,
        num_ticks: int = 24,
        forecast_provider_fn: Optional[Callable[[int], Forecast]] = None,
    ) -> List[Dict[str, Any]]:
        """Run multiple rolling-horizon ticks sequentially in fast-forward mode (Task 2.1).

        Compresses a simulated day into seconds for backtesting and verification.
        Each tick feeds the simulated telemetry from the previous tick back as starting state.
        """
        results = []
        for tick_idx in range(num_ticks):
            forecast = forecast_provider_fn(tick_idx) if forecast_provider_fn else None
            tick_result = self.tick(provided_forecast=forecast)
            results.append(tick_result)
        return results
