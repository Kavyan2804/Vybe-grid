"""In-memory repository adapters for testing and standalone execution (Clean Architecture).

Implements PlanRepository, TelemetryRepository, and AlertPort from optimizer/domain/ports.py.
Allows full execution of the rolling-horizon loop with zero external database dependencies.
"""

from typing import Dict, Any, List, Optional
from optimizer.domain.entities import ActualState, DispatchDecision, DispatchPlan
from optimizer.domain.ports import AlertPort, ExecutionRepository, PlanRepository, TelemetryRepository


class InMemoryPlanRepository(PlanRepository):
    """In-memory storage for DispatchPlan entities."""

    def __init__(self) -> None:
        self._plans: Dict[str, List[DispatchPlan]] = {}

    def save(self, plan: DispatchPlan) -> None:
        if plan.site_id not in self._plans:
            self._plans[plan.site_id] = []
        self._plans[plan.site_id].append(plan)

    def latest(self, site_id: str) -> Optional[DispatchPlan]:
        plans = self._plans.get(site_id, [])
        return plans[-1] if plans else None

    def list_for_site(self, site_id: str) -> List[DispatchPlan]:
        return list(self._plans.get(site_id, []))


class InMemoryTelemetryRepository(TelemetryRepository):
    """In-memory storage for actual telemetry readings."""

    def __init__(self) -> None:
        self._readings: Dict[str, List[Dict[str, Any]]] = {}

    def record(self, reading: Dict[str, Any]) -> None:
        site_id = reading.get("site_id", "default")
        if site_id not in self._readings:
            self._readings[site_id] = []
        self._readings[site_id].append(dict(reading))

    def latest_soc(self, site_id: str) -> Optional[float]:
        """Return the latest recorded SoC in percent."""
        readings = self._readings.get(site_id, [])
        if not readings:
            return None
        return float(readings[-1].get("soc_pct", 50.0))

    def list_for_site(self, site_id: str) -> List[Dict[str, Any]]:
        return list(self._readings.get(site_id, []))


class InMemoryAlertSink(AlertPort):
    """In-memory sink recording alerts emitted by services."""

    def __init__(self) -> None:
        self.alerts: List[Dict[str, Any]] = []

    def emit(
        self, alert_type: str, subject: str, payload: Optional[Dict[str, Any]] = None
    ) -> None:
        self.alerts.append({
            "type": alert_type,
            "subject": subject,
            "payload": payload or {},
        })


class InMemoryExecutionRepository(ExecutionRepository):
    """In-memory stand-in for the Phase 3 telemetry/dispatch-log unit of work."""

    def __init__(self, telemetry_repository: InMemoryTelemetryRepository) -> None:
        self._telemetry_repository = telemetry_repository
        self.dispatch_logs: List[Dict[str, Any]] = []

    def record_execution(
        self, plan: DispatchPlan, decision: DispatchDecision, actual: ActualState
    ) -> None:
        telemetry = actual.to_telemetry()
        self._telemetry_repository.record(telemetry)
        self.dispatch_logs.append({
            "site_id": plan.site_id,
            "plan_forecast_id": plan.forecast_id,
            "hour_index": decision.hour,
            "executed_at": telemetry["recorded_at"],
            "decision": decision,
        })
