"""Development-only in-memory alert management service."""

from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from datetime import UTC, datetime, timedelta

from src.errors import InvalidStateTransitionError, ResourceNotFoundError
from src.schemas.alerts import (
    Alert,
    AlertCreateRequest,
    AlertSeverity,
    AlertState,
    AlertStatus,
    AlertType,
)
from src.schemas.common import ProvenanceBadge

Clock = Callable[[], datetime]
DeduplicationKey = tuple[str, AlertType, str | None]


class AlertNotFoundError(ResourceNotFoundError):
    """Raised when an alert does not exist."""


class AlertTransitionError(InvalidStateTransitionError):
    """Raised when an alert state transition is not allowed."""


class InMemoryAlertService:
    """Typed in-memory alert store with lifecycle, deduplication, and cooldown."""

    def __init__(
        self,
        seed_demo: bool = True,
        *,
        clock: Clock | None = None,
        cooldown: timedelta = timedelta(seconds=60),
    ) -> None:
        self._alerts: dict[str, Alert] = {}
        self._next_id = 3
        self._clock = clock or (lambda: datetime.now(UTC))
        self._cooldown = cooldown
        if cooldown < timedelta(0):
            raise ValueError("cooldown must be non-negative")
        if seed_demo:
            self._alerts = {
                "alr_001": self._demo_alert("alr_001", AlertStatus.ACTIVE),
                "alr_002": self._demo_alert("alr_002", AlertStatus.ACTIVE),
            }

    def create(
        self,
        request: AlertCreateRequest,
        *,
        alert_type: AlertType | None = None,
        subject: str | None = None,
        raised_at: datetime | None = None,
        received_at: datetime | None = None,
        provenance: list[ProvenanceBadge] | None = None,
    ) -> Alert:
        """Create a legacy API alert, or a deduplicated Phase 3 alert."""

        # Phase 1 callers do not provide a type or subject and historically
        # received one alert per request, so retain that behavior.
        if alert_type is None and subject is None:
            return self._store(
                site_id=request.site_id,
                alert_type=AlertType.LOW_SOC_RESERVE,
                subject=None,
                severity=request.severity,
                title=request.title.strip(),
                message=request.message.strip(),
                raised_at=raised_at,
                received_at=received_at,
                provenance=provenance,
                deduplicate=False,
            )
        return self.raise_alert(
            site_id=request.site_id,
            alert_type=alert_type or AlertType.LOW_SOC_RESERVE,
            subject=subject,
            severity=request.severity,
            title=request.title,
            message=request.message,
            raised_at=raised_at,
            received_at=received_at,
            provenance=provenance,
        )

    def raise_alert(
        self,
        *,
        site_id: str,
        alert_type: AlertType,
        subject: str | None,
        severity: AlertSeverity,
        title: str,
        message: str,
        raised_at: datetime | None = None,
        received_at: datetime | None = None,
        provenance: list[ProvenanceBadge] | None = None,
    ) -> Alert:
        """Raise an alert unless its active key or cooldown blocks a duplicate."""

        now = self._validated_now(received_at)
        key = self._key(site_id, alert_type, subject)
        existing = self._existing_for_key(key)
        if existing is not None:
            if existing.state is not AlertState.RESOLVED:
                return deepcopy(existing)
            if existing.resolved_at is not None and now < existing.resolved_at + self._cooldown:
                return deepcopy(existing)

        return self._store(
            site_id=site_id,
            alert_type=alert_type,
            subject=subject,
            severity=severity,
            title=title.strip(),
            message=message.strip(),
            raised_at=raised_at,
            received_at=now,
            provenance=provenance,
            deduplicate=False,
        )

    def get(self, alert_id: str) -> Alert:
        alert = self._alerts.get(alert_id)
        if alert is None:
            raise AlertNotFoundError(f"Alert '{alert_id}' was not found")
        return deepcopy(alert)

    def list_active_alerts(self, *, site_id: str | None = None) -> list[Alert]:
        """Return created and acknowledged alerts, excluding resolved history."""

        return [
            alert
            for alert in self.list(site_id=site_id)[1]
            if alert.state is not AlertState.RESOLVED
        ]

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

    def acknowledge(self, alert_id: str, *, at: datetime | None = None) -> Alert:
        alert = self._get_for_transition(alert_id)
        if alert.state is AlertState.RESOLVED:
            raise AlertTransitionError("Resolved alerts cannot be acknowledged")
        if alert.state is AlertState.ACKNOWLEDGED:
            raise AlertTransitionError("Alert is already acknowledged")
        acknowledged_at = self._validated_now(at)
        updated = alert.model_copy(
            update={
                "state": AlertState.ACKNOWLEDGED,
                "status": AlertStatus.ACKNOWLEDGED,
                "acknowledged_at": acknowledged_at,
            }
        )
        self._alerts[alert_id] = updated
        return deepcopy(updated)

    def resolve(self, alert_id: str, *, at: datetime | None = None) -> Alert:
        alert = self._get_for_transition(alert_id)
        if alert.state is AlertState.RESOLVED:
            raise AlertTransitionError("Alert is already resolved")
        resolved_at = self._validated_now(at)
        updated = alert.model_copy(
            update={
                "state": AlertState.RESOLVED,
                "status": AlertStatus.RESOLVED,
                "resolved_at": resolved_at,
            }
        )
        self._alerts[alert_id] = updated
        return deepcopy(updated)

    def _store(
        self,
        *,
        site_id: str,
        alert_type: AlertType,
        subject: str | None,
        severity: AlertSeverity,
        title: str,
        message: str,
        raised_at: datetime | None,
        received_at: datetime | None,
        provenance: list[ProvenanceBadge] | None,
        deduplicate: bool,
    ) -> Alert:
        received = self._validated_now(received_at)
        raised = self._validated_timestamp(raised_at or received, "raised_at")
        key = self._key(site_id, alert_type, subject)
        if deduplicate:
            existing = self._existing_for_key(key)
            if existing is not None:
                return deepcopy(existing)
        alert_id = f"alr_{self._next_id:03d}"
        self._next_id += 1
        alert = Alert(
            id=alert_id,
            site_id=site_id,
            type=alert_type,
            subject=subject,
            state=AlertState.CREATED,
            severity=severity,
            status=AlertStatus.ACTIVE,
            title=title,
            message=message,
            created_at=received,
            raised_at=raised,
            received_at=received,
            provenance=provenance or [ProvenanceBadge.SIMULATED],
        )
        self._alerts[alert_id] = alert
        return deepcopy(alert)

    def _existing_for_key(self, key: DeduplicationKey) -> Alert | None:
        for alert in reversed(list(self._alerts.values())):
            if self._key(alert.site_id, alert.type, alert.subject) == key:
                return alert
        return None

    def _get_for_transition(self, alert_id: str) -> Alert:
        alert = self._alerts.get(alert_id)
        if alert is None:
            raise AlertNotFoundError(f"Alert '{alert_id}' was not found")
        return alert

    def _validated_now(self, value: datetime | None) -> datetime:
        return self._validated_timestamp(value or self._clock(), "current time")

    @staticmethod
    def _validated_timestamp(value: datetime, name: str) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError(f"{name} must include an explicit timezone offset")
        return value

    @staticmethod
    def _key(site_id: str, alert_type: AlertType, subject: str | None) -> DeduplicationKey:
        return site_id, alert_type, subject

    @staticmethod
    def _demo_alert(alert_id: str, status: AlertStatus) -> Alert:
        timestamp = datetime(2026, 1, 1, tzinfo=UTC)
        return Alert(
            id=alert_id,
            site_id="demo-site",
            type=AlertType.LOW_SOC_RESERVE,
            subject="battery",
            state=(
                AlertState.ACKNOWLEDGED
                if status is AlertStatus.ACKNOWLEDGED
                else AlertState.CREATED
            ),
            severity=AlertSeverity.WARNING,
            status=status,
            title="Demo battery alert",
            message="Development-only seeded alert.",
            created_at=timestamp,
            raised_at=timestamp,
            received_at=timestamp,
        )


alert_service = InMemoryAlertService()
