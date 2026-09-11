"""Forecast repository — basic CRUD."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models.forecasts import Forecast


class ForecastRepository:
    """Thin repository over the ``forecasts`` table."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, forecast: Forecast) -> Forecast:
        self._session.add(forecast)
        await self._session.flush()
        return forecast

    async def get_by_id(self, forecast_id: int) -> Forecast | None:
        return await self._session.get(Forecast, forecast_id)

    async def get_latest_for_site(self, site_id: str) -> Forecast | None:
        """Return the most recently issued forecast for *site_id*."""
        stmt = (
            select(Forecast)
            .where(Forecast.site_id == site_id)
            .order_by(Forecast.issued_at.desc())
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()
