"""Forecasts API router per API_CONTRACT.md §4 — the PLANNED domain, read-only."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.repositories.forecasts import ForecastRepository
from src.db.session import get_db_session
from src.openapi import OPENAPI_ERROR_RESPONSES

router = APIRouter(tags=["forecasts"])


class ForecastEntryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hour: int
    solar_kw: float
    load_kw: float
    solar_p10_kw: float | None = None
    solar_p90_kw: float | None = None


class ForecastResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    site_id: str
    issued_at: str
    horizon_hours: int
    source: str
    stale: bool
    series: list[ForecastEntryResponse]


@router.get(
    "/forecasts/latest",
    response_model=ForecastResponse,
    summary="Latest forecast for a site",
    description="The most recently fetched weather/solar/load forecast — badged FORECAST.",
    responses=OPENAPI_ERROR_RESPONSES,
)
async def get_latest_forecast(
    site_id: str = Query(..., min_length=1),
    session: AsyncSession = Depends(get_db_session),
) -> ForecastResponse:
    repo = ForecastRepository(session)
    row = await repo.get_latest_for_site(site_id)
    if row is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "forecast_not_found",
                "message": f"No forecast has been recorded yet for site '{site_id}'.",
                "detail": {},
            },
        )
    return ForecastResponse(
        site_id=row.site_id,
        issued_at=row.issued_at.isoformat(),
        horizon_hours=row.horizon_hours,
        source=row.source,
        stale=row.stale,
        series=[ForecastEntryResponse(**entry) for entry in row.series],
    )
