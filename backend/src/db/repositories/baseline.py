"""Baseline repositories — DATA_MODEL.md §3.

Provides persistence for the shadow-baseline controller's output.
Both tables have the same shape as their optimized counterparts;
``source`` is fixed to ``'baseline'``.

Population is the responsibility of Aarin's ``baseline_service`` —
these repositories only persist/retrieve.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models.baseline import BaselineTelemetry, BaselineDispatchLog


class BaselineTelemetryRepository:
    """Thin repository over the ``baseline_telemetry`` table."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, reading: BaselineTelemetry) -> BaselineTelemetry:
        self._session.add(reading)
        await self._session.flush()
        return reading

    async def get_by_id(self, telemetry_id: int) -> BaselineTelemetry | None:
        return await self._session.get(BaselineTelemetry, telemetry_id)

    async def list_for_site(
        self,
        site_id: str,
        *,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        limit: int = 500,
    ) -> list[BaselineTelemetry]:
        """Return baseline telemetry rows for *site_id*, chronologically ascending.

        *start_time* and *end_time* are inclusive/exclusive bounds on ``at``:
        ``[start_time, end_time)``.

        The ledger service (Kavyan) joins this with ``telemetry`` on
        ``(site_id, at)`` to compute the savings delta (DATA_MODEL.md §4).
        """
        stmt = select(BaselineTelemetry).where(BaselineTelemetry.site_id == site_id)
        if start_time is not None:
            stmt = stmt.where(BaselineTelemetry.at >= start_time)
        if end_time is not None:
            stmt = stmt.where(BaselineTelemetry.at < end_time)
        stmt = stmt.order_by(BaselineTelemetry.at.asc()).limit(limit)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


class BaselineDispatchLogRepository:
    """Thin repository over the ``baseline_dispatch_log`` table."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, log_entry: BaselineDispatchLog) -> BaselineDispatchLog:
        self._session.add(log_entry)
        await self._session.flush()
        return log_entry

    async def get_by_id(self, log_id: int) -> BaselineDispatchLog | None:
        return await self._session.get(BaselineDispatchLog, log_id)

    async def list_for_site(
        self,
        site_id: str,
        *,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        limit: int = 500,
    ) -> list[BaselineDispatchLog]:
        """Return baseline dispatch-log entries for *site_id*.

        Joins through ``dispatch_plans`` on ``plan_id`` to filter by site.
        Range is on ``executed_at``: ``[start_time, end_time)``.
        """
        from src.db.models.dispatch_plans import DispatchPlan

        stmt = (
            select(BaselineDispatchLog)
            .join(DispatchPlan, BaselineDispatchLog.plan_id == DispatchPlan.id)
            .where(DispatchPlan.site_id == site_id)
        )
        if start_time is not None:
            stmt = stmt.where(BaselineDispatchLog.executed_at >= start_time)
        if end_time is not None:
            stmt = stmt.where(BaselineDispatchLog.executed_at < end_time)
        stmt = stmt.order_by(BaselineDispatchLog.executed_at.asc()).limit(limit)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
