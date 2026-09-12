"""Site repository — CRUD + config history.

Provides ``get_current`` and ``get_at(timestamp)`` needed by the ledger
service to resolve which config version was in force for a given tick.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models.sites import Site, SiteConfigHistory


class SiteRepository:
    """Thin repository over the ``sites`` and ``site_config_history`` tables."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, site: Site) -> Site:
        self._session.add(site)
        await self._session.flush()
        return site

    async def get_by_id(self, site_id: str) -> Site | None:
        return await self._session.get(Site, site_id)

    # Alias used by Kavyan's ledger service
    get_current = get_by_id

    async def list_all(self) -> list[Site]:
        stmt = select(Site).order_by(Site.id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_config_at(
        self, site_id: str, timestamp: datetime
    ) -> SiteConfigHistory | None:
        """Return the config snapshot that was active at *timestamp*.

        Selects the ``site_config_history`` row with the largest
        ``changed_at <= timestamp``.  Returns ``None`` if no config existed
        before *timestamp* (unexpected for production data; the caller
        should treat this as a data-integrity warning).

        Used by the ledger service to detect config-change boundaries in
        savings comparisons (DATA_MODEL.md §1).
        """
        stmt = (
            select(SiteConfigHistory)
            .where(SiteConfigHistory.site_id == site_id)
            .where(SiteConfigHistory.changed_at <= timestamp)
            .order_by(SiteConfigHistory.changed_at.desc())
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def add_config_history(
        self, entry: SiteConfigHistory
    ) -> SiteConfigHistory:
        self._session.add(entry)
        await self._session.flush()
        return entry
