"""Telemetry repository.

Key query: ``latest_soc(site_id)`` — the only legal source of a tick's
starting state (DATA_MODEL.md §3).
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models.telemetry import Telemetry


class TelemetryRepository:
    """Thin repository over the ``telemetry`` table."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, reading: Telemetry) -> Telemetry:
        self._session.add(reading)
        await self._session.flush()
        return reading

    async def get_by_id(self, telemetry_id: int) -> Telemetry | None:
        return await self._session.get(Telemetry, telemetry_id)

    async def latest_soc(self, site_id: str) -> float | None:
        """``SELECT soc_kwh FROM telemetry WHERE site_id = $1 ORDER BY at DESC LIMIT 1``

        The only legal source of a tick's starting state
        (DATA_MODEL.md §3).
        """
        stmt = (
            select(Telemetry.soc_kwh)
            .where(Telemetry.site_id == site_id)
            .order_by(Telemetry.at.desc())
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()
