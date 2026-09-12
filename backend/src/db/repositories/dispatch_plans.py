"""Dispatch-plan repository.

Key query: ``get_latest_for_site(site_id)`` — backs
``GET /api/plans/latest?site_id=`` (API_CONTRACT.md §2).
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models.dispatch_plans import DispatchPlan


class DispatchPlanRepository:
    """Thin repository over the ``dispatch_plans`` table."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, plan: DispatchPlan) -> DispatchPlan:
        self._session.add(plan)
        await self._session.flush()
        return plan

    async def get_by_id(self, plan_id: int) -> DispatchPlan | None:
        return await self._session.get(DispatchPlan, plan_id)

    async def get_latest_for_site(self, site_id: str) -> DispatchPlan | None:
        """Return the most recent dispatch plan for *site_id*.

        This is the query backing ``GET /api/plans/latest?site_id=``.
        """
        stmt = (
            select(DispatchPlan)
            .where(DispatchPlan.site_id == site_id)
            .order_by(DispatchPlan.tick_at.desc())
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_for_site(
        self, site_id: str, *, limit: int = 50
    ) -> list[DispatchPlan]:
        stmt = (
            select(DispatchPlan)
            .where(DispatchPlan.site_id == site_id)
            .order_by(DispatchPlan.tick_at.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
