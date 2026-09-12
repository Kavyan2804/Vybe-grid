"""Dispatch-log repository — basic CRUD + range query."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models.dispatch_log import DispatchLog


class DispatchLogRepository:
    """Thin repository over the ``dispatch_log`` table."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, log_entry: DispatchLog) -> DispatchLog:
        self._session.add(log_entry)
        await self._session.flush()
        return log_entry

    async def get_by_id(self, log_id: int) -> DispatchLog | None:
        return await self._session.get(DispatchLog, log_id)

    async def get_for_plan(self, plan_id: int) -> list[DispatchLog]:
        stmt = (
            select(DispatchLog)
            .where(DispatchLog.plan_id == plan_id)
            .order_by(DispatchLog.hour_index)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_for_site(
        self,
        site_id: str,
        *,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        limit: int = 500,
    ) -> list[DispatchLog]:
        """Return dispatch-log entries whose plan belongs to *site_id*.

        Joins through ``dispatch_plans`` to filter by site and time window
        ``[start_time, end_time)`` on ``executed_at``.
        """
        from src.db.models.dispatch_plans import DispatchPlan

        stmt = (
            select(DispatchLog)
            .join(DispatchPlan, DispatchLog.plan_id == DispatchPlan.id)
            .where(DispatchPlan.site_id == site_id)
        )
        if start_time is not None:
            stmt = stmt.where(DispatchLog.executed_at >= start_time)
        if end_time is not None:
            stmt = stmt.where(DispatchLog.executed_at < end_time)
        stmt = stmt.order_by(DispatchLog.executed_at.asc()).limit(limit)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
