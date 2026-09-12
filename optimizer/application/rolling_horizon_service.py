"""Rolling Horizon Service (ARCHITECTURE.md §3, §4, §7).

Orchestrates the hourly optimization loop:
1. Fetch latest forecast
2. Read measured starting SoC from telemetry (NEVER from previous plan's own prediction)
3. Solve 24-hour MILP with up/down-time and degradation constraints
4. On timeout or infeasibility, trigger fallback path (SOLVER_FALLBACK_ACTIVE + baseline rule)
5. Persist plan to PlanRepository
6. Hand hour 0 decision to DispatchPort
7. Record actual telemetry to TelemetryRepository
8. Run shadow baseline against identical realized solar/load
9. Supports --fast-forward mode for backtesting and fast simulations
"""

from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Callable

from optimizer.domain.entities import Site, Forecast, DispatchDecision, DispatchPlan
from optimizer.domain.ports import (
    ForecastPort,
    OptimizerPort,
    DispatchPort,
    ExecutionRepository,
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
        execution_repository: Optional[ExecutionRepository] = None,
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
        self.execution_repository = execution_repository
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
        # Optimized-path diesel continuity across ticks (Phase 2 uptime constraints)
        self._diesel_on = False
        self._diesel_run_hours = 0
        self._diesel_off_hours = 10
        self._diesel_state_seeded = False

    def tick(
        self,
        force_fallback: bool = False,
        provided_forecast: Optional[Forecast] = None,
    ) -> Dict[str, Any]:
        """Execute a single rolling-horizon tick end to end.

        ARCHITECTURE.md §3, §4:
        Starting SoC MUST come from telemetry, never from the previous plan's prediction.
        """
        forecast = provided_forecast or self.forecast_port.fetch_forecast(self.site)

        telemetry_soc = self.telemetry_repository.latest_soc(self.site.name)
        starting_soc_pct = (
            telemetry_soc if telemetry_soc is not None else self.default_initial_soc_pct
        )
        self._seed_diesel_state_from_telemetry()

        plan: DispatchPlan
        fallback_used = False

        if force_fallback:
            plan = self._build_fallback_plan(forecast, starting_soc_pct, reason="forced_fallback")
            fallback_used = True
        else:
            try:
                plan = self.optimizer_port.solve(
                    site=self.site,
                    forecast=forecast,
                    initial_soc_pct=starting_soc_pct,
                    initial_diesel_on=self._diesel_on,
                    initial_diesel_run_hours=self._diesel_run_hours,
                    initial_diesel_off_hours=self._diesel_off_hours,
                    solver_timeout_seconds=self.solve_timeout_seconds,
                )
            except Exception as exc:
                fallback_used = True
                plan = self._build_fallback_plan(
                    forecast, starting_soc_pct, reason=f"solver_failure: {exc}"
                )

        self.plan_repository.save(plan)

        hour_0_decision = plan.decisions[0]
        actual_state = self.dispatch_port.execute(
            site=self.site,
            decision=hour_0_decision,
            current_soc_pct=starting_soc_pct,
        )

        actual_telemetry = actual_state.to_telemetry()

        if self.execution_repository is not None:
            self.execution_repository.record_execution(plan, hour_0_decision, actual_state)
        else:
            self.telemetry_repository.record(actual_telemetry)

        self._advance_diesel_state(actual_state.diesel_on)

        # Shadow baseline must see identical realized solar/load (Phase 3 / DATA_MODEL §4).
        baseline_decision, self._baseline_state = baseline_decide(
            site=self.site,
            state=self._baseline_state,
            current_hour_load_kw=actual_state.load_kw,
            solar_available_kw=actual_state.solar_kw,
        )

        return {
            "plan": plan,
            "telemetry": actual_telemetry,
            "actual_state": actual_state,
            "starting_soc_pct": starting_soc_pct,
            "fallback_used": fallback_used,
            "baseline_decision": baseline_decision,
            "hour_0_decision": hour_0_decision,
        }

    def _seed_diesel_state_from_telemetry(self) -> None:
        if self._diesel_state_seeded:
            return
        latest = self.telemetry_repository.latest_diesel_on(self.site.name)
        if latest is not None:
            self._diesel_on = latest
            if latest:
                self._diesel_run_hours = max(1, self._diesel_run_hours)
                self._diesel_off_hours = 0
            else:
                self._diesel_off_hours = max(1, self._diesel_off_hours)
                self._diesel_run_hours = 0
        self._diesel_state_seeded = True

    def _advance_diesel_state(self, diesel_on: bool) -> None:
        if diesel_on:
            self._diesel_run_hours = self._diesel_run_hours + 1 if self._diesel_on else 1
            self._diesel_off_hours = 0
        else:
            self._diesel_off_hours = self._diesel_off_hours + 1 if not self._diesel_on else 1
            self._diesel_run_hours = 0
        self._diesel_on = diesel_on
        self._diesel_state_seeded = True

    def _build_fallback_plan(
        self,
        forecast: Forecast,
        current_soc_pct: float,
        reason: str,
    ) -> DispatchPlan:
        """Construct a safe fallback plan using the greedy baseline rule (Task 2.4)."""
        if self.alert_port is not None:
            self.alert_port.emit(
                alert_type="SOLVER_FALLBACK_ACTIVE",
                subject=self.site.name,
                payload={
                    "reason": reason,
                    "site_id": self.site.name,
                    "title": "Solver fallback active",
                },
            )

        decisions: List[DispatchDecision] = []
        state = MicrogridState(
            soc_pct=current_soc_pct,
            diesel_on=self._diesel_on,
            diesel_run_hours=self._diesel_run_hours,
            diesel_off_hours=self._diesel_off_hours,
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
        """Run multiple rolling-horizon ticks sequentially in fast-forward mode (Task 2.1)."""
        results = []
        for tick_idx in range(num_ticks):
            forecast = forecast_provider_fn(tick_idx) if forecast_provider_fn else None
            tick_result = self.tick(provided_forecast=forecast)
            results.append(tick_result)
        return results
