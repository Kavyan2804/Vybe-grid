"""Telemetry API router per API_CONTRACT.md §3 — the ACTUAL domain, read-only."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.repositories.telemetry import TelemetryRepository
from src.db.session import get_db_session
from src.openapi import OPENAPI_ERROR_RESPONSES

router = APIRouter(tags=["telemetry"])


class TelemetryPointResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    at: str
    soc_kwh: float
    diesel_on: bool
    diesel_kw: float
    batt_kw: float
    solar_kw: float
    load_kw: float
    source: str


class TelemetryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    site_id: str
    points: list[TelemetryPointResponse]


@router.get(
    "/telemetry",
    response_model=TelemetryResponse,
    summary="Actual telemetry for a site",
    description="Historical ACTUAL-domain readings — never the plan. Defaults to the last 24 hours.",
    responses=OPENAPI_ERROR_RESPONSES,
)
async def get_telemetry(
    site_id: str = Query(..., min_length=1),
    start_at: datetime | None = Query(None, description="Inclusive ISO-8601 timestamp with offset."),
    end_at: datetime | None = Query(None, description="Exclusive ISO-8601 timestamp with offset."),
    limit: int = Query(500, ge=1, le=2000),
    session: AsyncSession = Depends(get_db_session),
) -> TelemetryResponse:
    repo = TelemetryRepository(session)
    now = datetime.now(timezone.utc)
    start = start_at or (now - timedelta(hours=24))
    end = end_at or (now + timedelta(seconds=1))

    rows = await repo.list_for_site(site_id, start_time=start, end_time=end, limit=limit)
    return TelemetryResponse(
        site_id=site_id,
        points=[
            TelemetryPointResponse(
                at=row.at.isoformat(),
                soc_kwh=row.soc_kwh,
                diesel_on=row.diesel_on,
                diesel_kw=row.diesel_kw,
                batt_kw=row.batt_kw,
                solar_kw=row.solar_kw,
                load_kw=row.load_kw,
                source=row.source,
            )
            for row in rows
        ],
    )
