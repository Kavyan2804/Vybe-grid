"""Site repository — basic CRUD."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models.sites import Site


class SiteRepository:
    """Thin repository over the ``sites`` table."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, site: Site) -> Site:
        self._session.add(site)
        await self._session.flush()
        return site

    async def get_by_id(self, site_id: str) -> Site | None:
        return await self._session.get(Site, site_id)

    async def list_all(self) -> list[Site]:
        stmt = select(Site).order_by(Site.id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
