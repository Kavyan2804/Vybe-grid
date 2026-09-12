"""Tests for the telemetry repository."""

from datetime import datetime, timezone
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models.sites import Site
from src.db.models.telemetry import Telemetry
from src.db.repositories.telemetry import TelemetryRepository

async def _seed_site(session: AsyncSession, site_id: str = "test-site") -> Site:
    site = Site(
        id=site_id,
        name="Test Site",
        timezone="Asia/Kolkata",
        config_version=1,
        config={},
    )
    session.add(site)
    await session.flush()
    return site

@pytest.mark.asyncio
async def test_latest_soc_returns_chronological_latest(db_session: AsyncSession) -> None:
    site = await _seed_site(db_session, "soc-site")
    repo = TelemetryRepository(db_session)
    
    # Insert older telemetry with soc 80
    await repo.create(Telemetry(
        site_id=site.id,
        at=datetime(2026, 1, 1, 9, 0, tzinfo=timezone.utc),
        soc_kwh=80.0,
        diesel_on=False,
        diesel_kw=0.0,
        batt_kw=0.0,
        solar_kw=0.0,
        load_kw=0.0,
        source="simulator",
        config_version=1
    ))

    # Insert newer telemetry with soc 60
    await repo.create(Telemetry(
        site_id=site.id,
        at=datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc),
        soc_kwh=60.0,
        diesel_on=False,
        diesel_kw=0.0,
        batt_kw=0.0,
        solar_kw=0.0,
        load_kw=0.0,
        source="simulator",
        config_version=1
    ))

    # Should return 60.0
    latest_soc = await repo.latest_soc(site.id)
    assert latest_soc == 60.0
