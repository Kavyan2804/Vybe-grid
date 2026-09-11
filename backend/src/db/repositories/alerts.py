"""Alert repository — CRUD + lifecycle transitions."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models.alerts import Alert, AlertState


class AlertRepository:
    """Thin repository over the ``alerts`` table."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, alert: Alert) -> Alert:
        self._session.add(alert)
        await self._session.flush()
        return alert

    async def get_by_id(self, alert_id: str) -> Alert | None:
        return await self._session.get(Alert, alert_id)

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
