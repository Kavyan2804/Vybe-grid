"""Postgres-backed alert service used by the HTTP API.

Maps `src.db.models.alerts.Alert` rows onto the API schema in
`src.schemas.alerts`, so ticks that write via `PostgresAlertSink` are visible
to `GET /api/alerts*` without a second in-memory store.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models.alerts import Alert as AlertORM
from src.db.models.alerts import AlertState as OrmAlertState
from src.db.models.alerts import AlertType as OrmAlertType
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


class AlertNotFoundError(ResourceNotFoundError):
    """Raised when an alert does not exist."""


class AlertTransitionError(InvalidStateTransitionError):
    """Raised when an alert state transition is not allowed."""


_SEVERITY_BY_TYPE: dict[AlertType, AlertSeverity] = {
    AlertType.CRITICAL_LOAD_AT_RISK: AlertSeverity.CRITICAL,
    AlertType.LOW_SOC_RESERVE: AlertSeverity.WARNING,
    AlertType.DIESEL_REQUIRED_SOON: AlertSeverity.WARNING,
    AlertType.SOLVER_FALLBACK_ACTIVE: AlertSeverity.CRITICAL,
    AlertType.FORECAST_STALE: AlertSeverity.INFO,
    AlertType.BASELINE_DIVERGENCE: AlertSeverity.CRITICAL,
}


class PostgresAlertService:
    """Async alert lifecycle over the shared `alerts` table."""

    def __init__(self, session: AsyncSession, *, cooldown: timedelta = timedelta(seconds=60)) -> None:
        self._session = session
        self._cooldown = cooldown

    async def create(self, request: AlertCreateRequest) -> Alert:
        return await self.raise_alert(
            site_id=request.site_id,
            alert_type=AlertType.LOW_SOC_RESERVE,
            subject=request.site_id,
            severity=request.severity,
            title=request.title,
            message=request.message,
        )

    async def raise_alert(
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
        now = received_at or datetime.now(UTC)
        raised = raised_at or now
        subject_key = subject or site_id

        existing = await self._session.execute(
            select(AlertORM)
            .where(AlertORM.site_id == site_id)
            .where(AlertORM.type == OrmAlertType(alert_type.value))
            .where(AlertORM.subject == subject_key)
            .where(AlertORM.state != OrmAlertState.RESOLVED)
            .limit(1)
        )
        open_row = existing.scalar_one_or_none()
        if open_row is not None:
            return self._to_api(open_row, severity=severity, message=message)

        resolved = await self._session.execute(
            select(AlertORM)
            .where(AlertORM.site_id == site_id)
            .where(AlertORM.type == OrmAlertType(alert_type.value))
            .where(AlertORM.subject == subject_key)
            .where(AlertORM.state == OrmAlertState.RESOLVED)
            .order_by(AlertORM.resolved_at.desc())
            .limit(1)
        )
        recent = resolved.scalar_one_or_none()
        if recent is not None and recent.resolved_at is not None:
            resolved_at = recent.resolved_at
            if getattr(resolved_at, "tzinfo", None) is None:
                resolved_at = resolved_at.replace(tzinfo=UTC)
            if now < resolved_at + self._cooldown:
                return self._to_api(recent, severity=severity, message=message)

        row = AlertORM(
            id=f"alr_{uuid.uuid4().hex[:12]}",
            site_id=site_id,
            type=OrmAlertType(alert_type.value),
            subject=subject_key,
            state=OrmAlertState.CREATED,
            title=title.strip(),
            raised_at=raised,
            received_at=now,
            provenance={
                "badges": [b.value for b in (provenance or [ProvenanceBadge.SIMULATED])],
                "message": message.strip(),
                "severity": severity.value,
            },
        )
        self._session.add(row)
        await self._session.flush()
        return self._to_api(row, severity=severity, message=message)

    async def get(self, alert_id: str) -> Alert:
        row = await self._session.get(AlertORM, alert_id)
        if row is None:
            raise AlertNotFoundError(f"Alert '{alert_id}' was not found")
        return self._to_api(row)

    async def list_active_alerts(self, *, site_id: str | None = None) -> list[Alert]:
        _, items = await self.list(site_id=site_id, status=None, limit=500, offset=0)
        return [alert for alert in items if alert.state is not AlertState.RESOLVED]

    async def list(
        self,
        *,
        site_id: str | None = None,
        severity: AlertSeverity | None = None,
        status: AlertStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[int, list[Alert]]:
        stmt = select(AlertORM)
        if site_id is not None:
            stmt = stmt.where(AlertORM.site_id == site_id)
        if status is AlertStatus.RESOLVED:
            stmt = stmt.where(AlertORM.state == OrmAlertState.RESOLVED)
        elif status is AlertStatus.ACKNOWLEDGED:
            stmt = stmt.where(AlertORM.state == OrmAlertState.ACKNOWLEDGED)
        elif status is AlertStatus.ACTIVE:
            stmt = stmt.where(AlertORM.state != OrmAlertState.RESOLVED)
        stmt = stmt.order_by(AlertORM.raised_at.desc())
        rows = list((await self._session.execute(stmt)).scalars().all())
        alerts = [self._to_api(row) for row in rows]
        if severity is not None:
            alerts = [a for a in alerts if a.severity == severity]
        return len(alerts), alerts[offset : offset + limit]

    async def acknowledge(self, alert_id: str) -> Alert:
        row = await self._session.get(AlertORM, alert_id)
        if row is None:
            raise AlertNotFoundError(f"Alert '{alert_id}' was not found")
        if row.state == OrmAlertState.RESOLVED:
            raise AlertTransitionError("Resolved alerts cannot be acknowledged")
        if row.state == OrmAlertState.ACKNOWLEDGED:
            raise AlertTransitionError("Alert is already acknowledged")
        row.state = OrmAlertState.ACKNOWLEDGED
        await self._session.flush()
        return self._to_api(row)

    async def resolve(self, alert_id: str) -> Alert:
        row = await self._session.get(AlertORM, alert_id)
        if row is None:
            raise AlertNotFoundError(f"Alert '{alert_id}' was not found")
        if row.state == OrmAlertState.RESOLVED:
            raise AlertTransitionError("Alert is already resolved")
        row.state = OrmAlertState.RESOLVED
        row.resolved_at = datetime.now(UTC)
        await self._session.flush()
        return self._to_api(row)

    async def count_open(self, site_id: str) -> int:
        rows = await self.list_active_alerts(site_id=site_id)
        return len(rows)

    @staticmethod
    def _to_api(
        row: AlertORM,
        *,
        severity: AlertSeverity | None = None,
        message: str | None = None,
    ) -> Alert:
        alert_type = AlertType(row.type.value if hasattr(row.type, "value") else row.type)
        provenance_raw = row.provenance if isinstance(row.provenance, dict) else {}
        parsed: list[ProvenanceBadge] = []
        for badge in provenance_raw.get("badges") or ["SIMULATED"]:
            try:
                parsed.append(ProvenanceBadge(badge))
            except ValueError:
                continue
        if not parsed:
            parsed = [ProvenanceBadge.SIMULATED]

        state = AlertState(row.state.value if hasattr(row.state, "value") else row.state)
        status = {
            AlertState.CREATED: AlertStatus.ACTIVE,
            AlertState.ACKNOWLEDGED: AlertStatus.ACKNOWLEDGED,
            AlertState.RESOLVED: AlertStatus.RESOLVED,
        }[state]
        derived_severity = severity or _SEVERITY_BY_TYPE.get(alert_type, AlertSeverity.WARNING)
        if provenance_raw.get("severity"):
            try:
                derived_severity = AlertSeverity(str(provenance_raw["severity"]))
            except ValueError:
                pass
        msg = message or provenance_raw.get("message") or row.title

        raised = row.raised_at
        received = row.received_at
        resolved = row.resolved_at
        if getattr(raised, "tzinfo", None) is None:
            raised = raised.replace(tzinfo=UTC)
        if getattr(received, "tzinfo", None) is None:
            received = received.replace(tzinfo=UTC)
        if resolved is not None and getattr(resolved, "tzinfo", None) is None:
            resolved = resolved.replace(tzinfo=UTC)

        return Alert(
            id=row.id,
            site_id=row.site_id,
            type=alert_type,
            subject=row.subject,
            state=state,
            severity=derived_severity,
            status=status,
            title=row.title,
            message=str(msg),
            created_at=received,
            raised_at=raised,
            received_at=received,
            provenance=parsed,
            acknowledged_at=received if state is AlertState.ACKNOWLEDGED else None,
            resolved_at=resolved,
        )
