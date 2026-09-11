"""Dispatch-log repository — basic CRUD."""

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
