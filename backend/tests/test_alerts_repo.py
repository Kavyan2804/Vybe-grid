"""Tests for the alerts repository — partial unique index enforcement.

Covers:
  - Two "open" alerts with the same (site_id, type, subject) → second fails
  - Two "resolved" alerts with the same key → both succeed (no conflict)
"""

from datetime import datetime, timezone

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.exceptions import DuplicateResourceError
from src.db.models.sites import Site
from src.db.models.alerts import Alert, AlertType, AlertState
from src.db.repositories.alerts import AlertRepository


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _seed_site(session: AsyncSession, site_id: str = "alert-site") -> Site:
    site = Site(
        id=site_id,
        name="Alert Test Site",
        timezone="Asia/Kolkata",
        config_version=1,
        config={},
    )
    session.add(site)
    await session.flush()
    return site


def _make_alert(
    alert_id: str,
    site_id: str,
    state: AlertState,
    subject: str = "gen-1",
) -> Alert:
    now = datetime.now(timezone.utc)
    return Alert(
        id=alert_id,
        site_id=site_id,
        type=AlertType.DIESEL_REQUIRED_SOON,
        subject=subject,
        state=state,
        title="Diesel start planned within 2 hours",
        raised_at=now,
        received_at=now,
        resolved_at=now if state == AlertState.RESOLVED else None,
        provenance={"badges": ["FORECAST"]},
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_partial_unique_index_open_alerts(db_session: AsyncSession) -> None:
    """Two open alerts with the same (site_id, type, subject) must fail."""
    site = await _seed_site(db_session, "open-alert-site")

    repo = AlertRepository(db_session)
    alert_1 = _make_alert("alr_001", site.id, AlertState.CREATED)
    await repo.create(alert_1)

    alert_2 = _make_alert("alr_002", site.id, AlertState.CREATED)
    with pytest.raises(DuplicateResourceError):
        await repo.create(alert_2)


@pytest.mark.asyncio
async def test_acknowledged_alert_also_blocked(db_session: AsyncSession) -> None:
    """An acknowledged alert is still non-resolved, so it blocks a duplicate."""
    site = await _seed_site(db_session, "ack-alert-site")

    repo = AlertRepository(db_session)
    alert_1 = _make_alert("alr_ack_1", site.id, AlertState.ACKNOWLEDGED)
    await repo.create(alert_1)

    alert_2 = _make_alert("alr_ack_2", site.id, AlertState.CREATED)
    with pytest.raises(DuplicateResourceError):
        await repo.create(alert_2)


@pytest.mark.asyncio
async def test_resolved_alerts_no_conflict(db_session: AsyncSession) -> None:
    """Two resolved alerts with the same key must both succeed."""
    site = await _seed_site(db_session, "resolved-alert-site")

    repo = AlertRepository(db_session)
    alert_1 = _make_alert("alr_res_1", site.id, AlertState.RESOLVED)
    alert_2 = _make_alert("alr_res_2", site.id, AlertState.RESOLVED)

    await repo.create(alert_1)
    await repo.create(alert_2)
