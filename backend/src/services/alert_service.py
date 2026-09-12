"""Development-only in-memory alert management service."""

from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime

from src.errors import InvalidStateTransitionError, ResourceNotFoundError
from src.schemas.alerts import (
    Alert,
    AlertCreateRequest,
    AlertSeverity,
    AlertStatus,
)


class AlertNotFoundError(ResourceNotFoundError):
    """Raised when an alert does not exist."""


class AlertTransitionError(InvalidStateTransitionError):
    """Raised when an alert state transition is not allowed."""


class InMemoryAlertService:
    """Typed in-memory alert store with explicit lifecycle rules."""

    def __init__(self, seed_demo: bool = True) -> None:
        self._alerts: dict[str, Alert] = {}
        self._next_id = 3
        if seed_demo:
            self._alerts = {
                "alr_001": self._demo_alert("alr_001", AlertStatus.ACTIVE),
                "alr_002": self._demo_alert("alr_002", AlertStatus.ACTIVE),
            }

    def create(self, request: AlertCreateRequest) -> Alert:
        alert_id = f"alr_{self._next_id:03d}"
        self._next_id += 1
        alert = Alert(
            id=alert_id,
            site_id=request.site_id,
            severity=request.severity,
            title=request.title.strip(),
            message=request.message.strip(),
            created_at=datetime.now(UTC),
        )
        self._alerts[alert_id] = alert
        return deepcopy(alert)

    def get(self, alert_id: str) -> Alert:
        alert = self._alerts.get(alert_id)
        if alert is None:
            raise AlertNotFoundError(f"Alert '{alert_id}' was not found")
        return deepcopy(alert)

    def list(
        self,
        *,
        site_id: str | None = None,
        severity: AlertSeverity | None = None,
        status: AlertStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[int, list[Alert]]:
        matching = [
            alert
            for alert in self._alerts.values()
            if (site_id is None or alert.site_id == site_id)
            and (severity is None or alert.severity == severity)
            and (status is None or alert.status == status)
        ]
        return len(matching), [deepcopy(alert) for alert in matching[offset : offset + limit]]

    def acknowledge(self, alert_id: str) -> Alert:
        alert = self._get_for_transition(alert_id)
        if alert.status is AlertStatus.RESOLVED:
            raise AlertTransitionError("Resolved alerts cannot be acknowledged")
        if alert.status is AlertStatus.ACKNOWLEDGED:
            raise AlertTransitionError("Alert is already acknowledged")
        alert.status = AlertStatus.ACKNOWLEDGED
        alert.acknowledged_at = datetime.now(UTC)
        return deepcopy(alert)

    def resolve(self, alert_id: str) -> Alert:
        alert = self._get_for_transition(alert_id)
        if alert.status is AlertStatus.RESOLVED:
            raise AlertTransitionError("Alert is already resolved")
        alert.status = AlertStatus.RESOLVED
        alert.resolved_at = datetime.now(UTC)
        return deepcopy(alert)

    def _get_for_transition(self, alert_id: str) -> Alert:
        alert = self._alerts.get(alert_id)
        if alert is None:
            raise AlertNotFoundError(f"Alert '{alert_id}' was not found")
        return alert

    @staticmethod
    def _demo_alert(alert_id: str, status: AlertStatus) -> Alert:
        return Alert(
            id=alert_id,
            site_id="demo-site",
            severity=AlertSeverity.WARNING,
            status=status,
            title="Demo battery alert",
            message="Development-only seeded alert.",
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
        )


alert_service = InMemoryAlertService()
