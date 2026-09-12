"""Telemetry repository.

Key query: ``latest_soc(site_id)`` — the only legal source of a tick's
starting state (DATA_MODEL.md §3).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.exceptions import ReferenceError
from src.db.models.telemetry import Telemetry


class TelemetryRepository:
    """Thin repository over the ``telemetry`` table."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, reading: Telemetry) -> Telemetry:
        self._session.add(reading)
        try:
            await self._session.flush()
        except IntegrityError as e:
            err_str = str(e.orig)
            if "ForeignKeyViolationError" in err_str or "23503" in err_str:
                raise ReferenceError(f"Invalid reference in telemetry: {err_str}") from e
            raise
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

    async def list_for_site(
        self,
        site_id: str,
        *,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        limit: int = 500,
    ) -> list[Telemetry]:
        """Return telemetry rows for *site_id*, chronologically ascending.

        *start_time* and *end_time* are inclusive/exclusive bounds on ``at``:
        ``[start_time, end_time)``.  Used by the ledger service for savings
        comparisons (DATA_MODEL.md §4).
        """
        stmt = select(Telemetry).where(Telemetry.site_id == site_id)
        if start_time is not None:
            stmt = stmt.where(Telemetry.at >= start_time)
        if end_time is not None:
            stmt = stmt.where(Telemetry.at < end_time)
        stmt = stmt.order_by(Telemetry.at.asc()).limit(limit)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
