"""Alert repository — CRUD + lifecycle transitions."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.exceptions import DuplicateResourceError
from src.db.models.alerts import Alert, AlertState, AlertType


class AlertRepository:
    """Thin repository over the ``alerts`` table."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, alert: Alert) -> Alert:
        self._session.add(alert)
        try:
            await self._session.flush()
        except IntegrityError as e:
            err_str = str(e.orig)
            if "UniqueViolationError" in err_str or "23505" in err_str:
                raise DuplicateResourceError(f"Duplicate alert key: {alert.id}") from e
            raise
        return alert

    async def get_by_id(self, alert_id: str) -> Alert | None:
        return await self._session.get(Alert, alert_id)

    async def find_duplicate(
        self,
        site_id: str,
        alert_type: AlertType,
        subject: str | None,
    ) -> Alert | None:
        """Return an existing non-resolved alert with the same dedup key.

        Dedup key: ``(site_id, type, subject)`` — mirrors the partial unique
        index ``alerts_open_uniq`` on the DB (DATA_MODEL.md §5).

        Kavyan calls this *before* attempting an insert to avoid relying
        solely on catching ``IntegrityError``.  The DB constraint is still
        the authoritative guard; this method lets the service layer produce
        a friendlier response than a raw constraint violation.
        """
        stmt = (
            select(Alert)
            .where(Alert.site_id == site_id)
            .where(Alert.type == alert_type)
            .where(Alert.subject == subject)
            .where(Alert.state != AlertState.RESOLVED)
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_for_site(
        self,
        site_id: str,
        *,
        state: AlertState | None = None,
        limit: int = 50,
    ) -> list[Alert]:
        stmt = select(Alert).where(Alert.site_id == site_id)
        if state is not None:
            stmt = stmt.where(Alert.state == state)
        stmt = stmt.order_by(Alert.raised_at.desc()).limit(limit)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def acknowledge(self, alert_id: str) -> Alert | None:
        alert = await self.get_by_id(alert_id)
        if alert is None:
            return None
        alert.state = AlertState.ACKNOWLEDGED
        await self._session.flush()
        return alert

    async def resolve(
        self, alert_id: str, resolved_at: str | None = None
    ) -> Alert | None:
        alert = await self.get_by_id(alert_id)
        if alert is None:
            return None
        alert.state = AlertState.RESOLVED
        if resolved_at is not None:
            alert.resolved_at = resolved_at
        await self._session.flush()
        return alert
