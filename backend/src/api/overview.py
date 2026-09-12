"""Overview API router per API_CONTRACT.md §1 and PHASE_1 Task 1.3.

Reads the real database directly (async, via the existing `src/db/repositories/*`) rather than
going through the mock/in-memory Phase 1 services — the whole point of this endpoint is that it
stops being a placeholder.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.repositories.baseline import BaselineTelemetryRepository
from src.db.repositories.sites import SiteRepository
from src.db.repositories.telemetry import TelemetryRepository
from src.db.session import get_db_session
from src.openapi import OPENAPI_ERROR_RESPONSES
from src.schemas.common import ProvenanceBadge
from src.services.postgres_alert_service import PostgresAlertService

router = APIRouter(tags=["overview"])


class Provenanced(BaseModel):
    """One value plus the badge(s) explaining where it came from (PRD.md §3)."""

    model_config = ConfigDict(extra="forbid")

    value: float
    badges: list[ProvenanceBadge]


class OverviewCurrent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    soc_pct: Provenanced
    diesel_on: bool
    solar_kw: Provenanced
    load_kw: Provenanced


class OverviewToday(BaseModel):
    model_config = ConfigDict(extra="forbid")

    diesel_hours: Provenanced
    fuel_liters_saved_vs_baseline: Provenanced | None
    cost_saved_vs_baseline: Provenanced | None


class OverviewSite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str


class OverviewResponse(BaseModel):
    """Everything the landing page needs in one call — API_CONTRACT.md §1."""

    model_config = ConfigDict(extra="forbid")

    server_time: str
    site: OverviewSite
    current: OverviewCurrent | None
    today: OverviewToday | None
    unread_alerts: int


@router.get(
    "/overview",
    response_model=OverviewResponse,
    summary="Dashboard landing-page summary",
    description=(
        "Current mix, today's diesel-hours, and today's savings vs the shadow baseline, for "
        "one site. Sections the database cannot yet answer are omitted (`null`), never "
        "zero-filled (PRD.md §3 / docs/agent/memory.md 'known in advance')."
    ),
    responses=OPENAPI_ERROR_RESPONSES,
)
async def get_overview(
    site_id: str = Query(..., min_length=1, description="Site identifier."),
    session: AsyncSession = Depends(get_db_session),
) -> OverviewResponse:
    site_repo = SiteRepository(session)
    telemetry_repo = TelemetryRepository(session)
    baseline_repo = BaselineTelemetryRepository(session)

    site_row = await site_repo.get_by_id(site_id)
    site_name = site_row.name if site_row is not None else site_id
    battery_capacity_kwh = (
        float(site_row.config.get("battery", {}).get("capacity_kwh", 0.0))
        if site_row is not None and site_row.config
        else None
    )

    now = datetime.now(timezone.utc)
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    # list_for_site orders ascending, so the newest row is the last element, not the first —
    # a wide-enough window plus a generous limit stands in for a dedicated "latest row" query.
    recent = await telemetry_repo.list_for_site(
        site_id, start_time=now - timedelta(days=2), end_time=now + timedelta(seconds=1), limit=2000
    )
    latest = recent[-1] if recent else None

    current = None
    if latest is not None and battery_capacity_kwh:
        current = OverviewCurrent(
            soc_pct=Provenanced(
                value=round(100.0 * latest.soc_kwh / battery_capacity_kwh, 2),
                badges=[ProvenanceBadge.SIMULATED],
            ),
            diesel_on=latest.diesel_on,
            solar_kw=Provenanced(value=latest.solar_kw, badges=[ProvenanceBadge.SIMULATED]),
            load_kw=Provenanced(value=latest.load_kw, badges=[ProvenanceBadge.SIMULATED]),
        )

    today_optimized = await telemetry_repo.list_for_site(site_id, start_time=day_start, end_time=now, limit=500)
    today_baseline = await baseline_repo.list_for_site(site_id, start_time=day_start, end_time=now, limit=500)

    today = None
    if today_optimized:
        diesel_hours = float(sum(1 for point in today_optimized if point.diesel_kw > 0))
        today_block = {
            "diesel_hours": Provenanced(value=diesel_hours, badges=[ProvenanceBadge.SIMULATED]),
            "fuel_liters_saved_vs_baseline": None,
            "cost_saved_vs_baseline": None,
        }
        if today_baseline and site_row is not None and site_row.config:
            fuel_l_per_kwh = float(site_row.config.get("diesel_generator", {}).get("fuel_curve", {}).get("litres_per_kwh_max_load", 0.0))
            fuel_price = float(site_row.config.get("fuel_cost_per_litre", 0.0))
            optimized_kwh = sum(p.diesel_kw for p in today_optimized)
            baseline_kwh = sum(p.diesel_kw for p in today_baseline)
            saved_litres = max(0.0, (baseline_kwh - optimized_kwh) * fuel_l_per_kwh)
            today_block["fuel_liters_saved_vs_baseline"] = Provenanced(
                value=round(saved_litres, 2),
                badges=[ProvenanceBadge.SIMULATED, ProvenanceBadge.BASELINE],
            )
            today_block["cost_saved_vs_baseline"] = Provenanced(
                value=round(saved_litres * fuel_price, 2),
                badges=[ProvenanceBadge.SIMULATED, ProvenanceBadge.BASELINE],
            )
        today = OverviewToday(**today_block)

    unread_alerts = await PostgresAlertService(session).count_open(site_id)

    return OverviewResponse(
        server_time=now.isoformat(),
        site=OverviewSite(id=site_id, name=site_name),
        current=current,
        today=today,
        unread_alerts=unread_alerts,
    )
