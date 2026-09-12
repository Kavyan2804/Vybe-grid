"""Phase 3 DB tests — DATA_MODEL.md §0 invariants.

Covers:
  8.1  Planned/actual immutability
  8.2  Actual/baseline separation
  8.3  Baseline timestamp alignment
  8.4  Alert deduplication (SQLSTATE 23505, various cross-site/type/subject combos)
  8.5  Day-boundary timestamps and range queries
  8.6  FK violations and repository CRUD for Phase 3 tables
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.exceptions import DuplicateResourceError, ReferenceError
from src.db.models.alerts import Alert, AlertState, AlertType
from src.db.models.baseline import BaselineDispatchLog, BaselineTelemetry
from src.db.models.dispatch_log import DispatchLog
from src.db.models.dispatch_plans import DispatchPlan
from src.db.models.forecasts import Forecast
from src.db.models.sites import Site, SiteConfigHistory
from src.db.models.telemetry import Telemetry
from src.db.repositories.alerts import AlertRepository
from src.db.repositories.baseline import (
    BaselineDispatchLogRepository,
    BaselineTelemetryRepository,
)
from src.db.repositories.dispatch_log import DispatchLogRepository
from src.db.repositories.dispatch_plans import DispatchPlanRepository
from src.db.repositories.sites import SiteRepository
from src.db.repositories.telemetry import TelemetryRepository


# ---------------------------------------------------------------------------
# Shared fixtures / helpers
# ---------------------------------------------------------------------------

def _utc(*args) -> datetime:
    """Build a UTC datetime without import noise at each call site."""
    return datetime(*args, tzinfo=timezone.utc)


async def _seed_site(session: AsyncSession, site_id: str = "p3-site") -> Site:
    site = Site(
        id=site_id,
        name="Phase 3 Test Site",
        timezone="UTC",
        config_version=1,
        config={"battery": {"capacity_kwh": 100, "efficiency": 0.92}},
    )
    session.add(site)
    await session.flush()
    return site


async def _seed_forecast(session: AsyncSession, site_id: str) -> Forecast:
    forecast = Forecast(
        site_id=site_id,
        issued_at=_utc(2026, 9, 12, 8, 0),
        horizon_hours=24,
        source="openmeteo",
        stale=False,
        series=[{"hour": 0, "ghi_w_m2": 400, "load_forecast_kw": 3.0, "solar_p50_kw": 2.0}],
    )
    session.add(forecast)
    await session.flush()
    return forecast


async def _seed_plan(
    session: AsyncSession,
    site_id: str,
    forecast_id: int,
    tick_at: datetime,
    *,
    diesel_kw: float = 5.0,
) -> DispatchPlan:
    plan = DispatchPlan(
        site_id=site_id,
        tick_at=tick_at,
        forecast_id=forecast_id,
        config_version=1,
        starting_soc_kwh=50.0,
        series=[{"hour": 0, "diesel_kw": diesel_kw}],
        objective_cost=100.0,
        solver_status="optimal",
        solve_ms=200,
        source="milp",
    )
    session.add(plan)
    await session.flush()
    return plan


async def _seed_telemetry(
    session: AsyncSession,
    site_id: str,
    at: datetime,
    *,
    diesel_kw: float,
    soc_kwh: float = 50.0,
    source: str = "simulator",
) -> Telemetry:
    row = Telemetry(
        site_id=site_id,
        at=at,
        soc_kwh=soc_kwh,
        diesel_on=diesel_kw > 0,
        diesel_kw=diesel_kw,
        batt_kw=0.0,
        solar_kw=2.0,
        load_kw=3.0,
        source=source,
        config_version=1,
    )
    session.add(row)
    await session.flush()
    return row


def _make_alert(
    alert_id: str,
    site_id: str,
    state: AlertState,
    alert_type: AlertType = AlertType.DIESEL_REQUIRED_SOON,
    subject: str | None = "gen-1",
) -> Alert:
    now = _utc(2026, 9, 12, 10, 0)
    return Alert(
        id=alert_id,
        site_id=site_id,
        type=alert_type,
        subject=subject,
        state=state,
        title="Test alert",
        raised_at=now,
        received_at=now,
        resolved_at=now if state == AlertState.RESOLVED else None,
        provenance={"badges": ["FORECAST"]},
    )


# ---------------------------------------------------------------------------
# 8.1  Planned / actual immutability
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_planned_and_actual_are_separate_rows(db_session: AsyncSession) -> None:
    """Plan row for tick T and telemetry row for tick T are independent.

    Plan diesel=10, actual diesel=15 — both survive; updating actual
    leaves plan untouched.
    """
    site = await _seed_site(db_session, "immutable-site")
    forecast = await _seed_forecast(db_session, site.id)
    tick = _utc(2026, 9, 12, 10, 0)

    plan = await _seed_plan(db_session, site.id, forecast.id, tick, diesel_kw=10.0)
    actual = await _seed_telemetry(db_session, site.id, tick, diesel_kw=15.0)

    # Both independently correct
    plan_repo = DispatchPlanRepository(db_session)
    tel_repo = TelemetryRepository(db_session)

    fetched_plan = await plan_repo.get_by_id(plan.id)
    fetched_actual = await tel_repo.get_by_id(actual.id)
    assert fetched_plan is not None
    assert fetched_actual is not None
    assert fetched_plan.series[0]["diesel_kw"] == pytest.approx(10.0)
    assert fetched_actual.diesel_kw == pytest.approx(15.0)

    # Update actual diesel
    fetched_actual.diesel_kw = 20.0
    await db_session.flush()

    # Plan is still untouched
    re_fetched_plan = await plan_repo.get_by_id(plan.id)
    assert re_fetched_plan.series[0]["diesel_kw"] == pytest.approx(10.0)


# ---------------------------------------------------------------------------
# 8.2  Actual / baseline separation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_actual_and_baseline_are_independent(db_session: AsyncSession) -> None:
    """Actual diesel=15, baseline diesel=20 — both independently queryable."""
    site = await _seed_site(db_session, "separation-site")
    tick = _utc(2026, 9, 12, 10, 0)

    actual = await _seed_telemetry(db_session, site.id, tick, diesel_kw=15.0)
    baseline = BaselineTelemetry(
        site_id=site.id,
        at=tick,
        soc_kwh=50.0,
        diesel_on=True,
        diesel_kw=20.0,
        batt_kw=0.0,
        solar_kw=2.0,
        load_kw=3.0,
        source="baseline",
        config_version=1,
    )
    db_session.add(baseline)
    await db_session.flush()

    tel_repo = TelemetryRepository(db_session)
    bsl_repo = BaselineTelemetryRepository(db_session)

    fetched_actual = await tel_repo.get_by_id(actual.id)
    fetched_baseline = await bsl_repo.get_by_id(baseline.id)

    assert fetched_actual.diesel_kw == pytest.approx(15.0)
    assert fetched_baseline.diesel_kw == pytest.approx(20.0)


# ---------------------------------------------------------------------------
# 8.3  Baseline timestamp alignment
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_baseline_timestamps_align_with_actual(db_session: AsyncSession) -> None:
    """actual(site, 10:00, solar=X) and baseline(site, 10:00, solar=X) share timestamp.

    The DB must not resample or mutate either side.
    """
    site = await _seed_site(db_session, "align-site")
    tick = _utc(2026, 9, 12, 10, 0)

    actual = Telemetry(
        site_id=site.id,
        at=tick,
        soc_kwh=50.0,
        diesel_on=False,
        diesel_kw=0.0,
        batt_kw=1.0,
        solar_kw=4.0,
        load_kw=3.0,
        source="simulator",
        config_version=1,
    )
    baseline = BaselineTelemetry(
        site_id=site.id,
        at=tick,  # exact same timestamp
        soc_kwh=48.0,
        diesel_on=True,
        diesel_kw=2.0,
        batt_kw=0.0,
        solar_kw=4.0,  # same realized solar
        load_kw=3.0,   # same realized load
        source="baseline",
        config_version=1,
    )
    db_session.add(actual)
    db_session.add(baseline)
    await db_session.flush()

    tel_repo = TelemetryRepository(db_session)
    bsl_repo = BaselineTelemetryRepository(db_session)

    rows_actual = await tel_repo.list_for_site(site.id, start_time=tick, end_time=_utc(2026, 9, 12, 11, 0))
    rows_baseline = await bsl_repo.list_for_site(site.id, start_time=tick, end_time=_utc(2026, 9, 12, 11, 0))

    assert len(rows_actual) == 1
    assert len(rows_baseline) == 1
    # Timestamps stored identically
    assert rows_actual[0].at == rows_baseline[0].at


# ---------------------------------------------------------------------------
# 8.4  Alert deduplication — SQLSTATE 23505 + cross-combos
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_duplicate_open_alert_raises_23505(db_session: AsyncSession) -> None:
    """Duplicate open alert key must fail with SQLSTATE 23505."""
    site = await _seed_site(db_session, "dedup-site-8-4")

    repo = AlertRepository(db_session)
    alert1 = _make_alert("alr_8_4_a", site.id, AlertState.CREATED)
    await repo.create(alert1)

    alert2 = _make_alert("alr_8_4_b", site.id, AlertState.CREATED)
    with pytest.raises(DuplicateResourceError) as exc_info:
        await repo.create(alert2)
    assert "Duplicate alert key" in str(exc_info.value)


@pytest.mark.asyncio
async def test_resolved_then_new_open_allowed(db_session: AsyncSession) -> None:
    """Same key resolved + new active → allowed."""
    site = await _seed_site(db_session, "reopen-site")

    resolved = _make_alert("alr_res", site.id, AlertState.RESOLVED)
    db_session.add(resolved)
    await db_session.flush()

    new_open = _make_alert("alr_new", site.id, AlertState.CREATED)
    db_session.add(new_open)
    await db_session.flush()  # must not raise


@pytest.mark.asyncio
async def test_different_subject_same_type_allowed(db_session: AsyncSession) -> None:
    """Same site+type, different subject → both open allowed."""
    site = await _seed_site(db_session, "multi-subject-site")

    a1 = _make_alert("alr_subj_1", site.id, AlertState.CREATED, subject="gen-1")
    a2 = _make_alert("alr_subj_2", site.id, AlertState.CREATED, subject="gen-2")
    db_session.add(a1)
    db_session.add(a2)
    await db_session.flush()  # must not raise


@pytest.mark.asyncio
async def test_different_site_same_type_subject_allowed(db_session: AsyncSession) -> None:
    """Different site, same type+subject → both open allowed."""
    site_a = await _seed_site(db_session, "cross-site-a")
    site_b = await _seed_site(db_session, "cross-site-b")

    a = _make_alert("alr_cross_a", site_a.id, AlertState.CREATED)
    b = _make_alert("alr_cross_b", site_b.id, AlertState.CREATED)
    db_session.add(a)
    db_session.add(b)
    await db_session.flush()  # must not raise


@pytest.mark.asyncio
async def test_find_duplicate_returns_open_alert(db_session: AsyncSession) -> None:
    """find_duplicate returns the open alert, returns None when resolved."""
    site = await _seed_site(db_session, "find-dup-site")
    repo = AlertRepository(db_session)

    alert = _make_alert("alr_fd_1", site.id, AlertState.CREATED)
    db_session.add(alert)
    await db_session.flush()

    found = await repo.find_duplicate(site.id, AlertType.DIESEL_REQUIRED_SOON, "gen-1")
    assert found is not None
    assert found.id == "alr_fd_1"

    # Resolve it → find_duplicate returns None
    await repo.resolve("alr_fd_1")
    not_found = await repo.find_duplicate(site.id, AlertType.DIESEL_REQUIRED_SOON, "gen-1")
    assert not_found is None


# ---------------------------------------------------------------------------
# 8.5  Day-boundary timestamps — range queries isolate dates
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_day_boundary_range_queries(db_session: AsyncSession) -> None:
    """Range query [2026-09-12, 2026-09-13) isolates only that day's telemetry.

    Timestamps: 23:00, 23:30 on day 12; 00:00, 00:30 on day 13.
    """
    site = await _seed_site(db_session, "boundary-site")
    repo = TelemetryRepository(db_session)

    timestamps = [
        _utc(2026, 9, 12, 23, 0),
        _utc(2026, 9, 12, 23, 30),
        _utc(2026, 9, 13, 0, 0),
        _utc(2026, 9, 13, 0, 30),
    ]
    for ts in timestamps:
        await _seed_telemetry(db_session, site.id, ts, diesel_kw=0.0)

    day12_start = _utc(2026, 9, 12, 0, 0)
    day13_start = _utc(2026, 9, 13, 0, 0)
    day14_start = _utc(2026, 9, 14, 0, 0)

    rows_day12 = await repo.list_for_site(site.id, start_time=day12_start, end_time=day13_start)
    rows_day13 = await repo.list_for_site(site.id, start_time=day13_start, end_time=day14_start)

    # Day 12: 23:00 and 23:30 only (exclusive upper bound excludes 00:00)
    assert len(rows_day12) == 2
    for row in rows_day12:
        assert row.at.date() == _utc(2026, 9, 12).date()

    # Day 13: 00:00 and 00:30 only
    assert len(rows_day13) == 2
    for row in rows_day13:
        assert row.at.date() == _utc(2026, 9, 13).date()


# ---------------------------------------------------------------------------
# 8.6  FK violations and CRUD round-trips for Phase 3 tables
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fk_violation_on_nonexistent_site(db_session: AsyncSession) -> None:
    """Inserting telemetry for a non-existent site_id must fail SQLSTATE 23503."""
    row = Telemetry(
        site_id="ghost-site",  # does not exist
        at=_utc(2026, 9, 12, 10, 0),
        soc_kwh=50.0,
        diesel_on=False,
        diesel_kw=0.0,
        batt_kw=0.0,
        solar_kw=0.0,
        load_kw=0.0,
        source="simulator",
        config_version=1,
    )
    repo = TelemetryRepository(db_session)
    with pytest.raises(ReferenceError) as exc_info:
        await repo.create(row)
    assert "Invalid reference in telemetry" in str(exc_info.value)


@pytest.mark.asyncio
async def test_baseline_telemetry_crud(db_session: AsyncSession) -> None:
    """CRUD round-trip for baseline_telemetry."""
    site = await _seed_site(db_session, "bsl-tel-crud")
    repo = BaselineTelemetryRepository(db_session)
    tick = _utc(2026, 9, 12, 10, 0)

    row = BaselineTelemetry(
        site_id=site.id,
        at=tick,
        soc_kwh=48.0,
        diesel_on=True,
        diesel_kw=5.0,
        batt_kw=0.0,
        solar_kw=2.0,
        load_kw=3.0,
        source="baseline",
        config_version=1,
    )
    created = await repo.create(row)
    fetched = await repo.get_by_id(created.id)
    assert fetched is not None
    assert fetched.diesel_kw == pytest.approx(5.0)
    assert fetched.source == "baseline"


@pytest.mark.asyncio
async def test_baseline_dispatch_log_crud(db_session: AsyncSession) -> None:
    """CRUD round-trip for baseline_dispatch_log."""
    site = await _seed_site(db_session, "bsl-log-crud")
    forecast = await _seed_forecast(db_session, site.id)
    plan = await _seed_plan(db_session, site.id, forecast.id, _utc(2026, 9, 12, 10, 0))
    repo = BaselineDispatchLogRepository(db_session)

    log = BaselineDispatchLog(
        plan_id=plan.id,
        hour_index=0,
        executed_at=_utc(2026, 9, 12, 10, 0),
        decision={"diesel_on": True, "diesel_kw": 5.0},
    )
    created = await repo.create(log)
    fetched = await repo.get_by_id(created.id)
    assert fetched is not None
    assert fetched.decision["diesel_kw"] == 5.0


@pytest.mark.asyncio
async def test_site_get_config_at(db_session: AsyncSession) -> None:
    """get_config_at returns the config version active at the given timestamp."""
    site = await _seed_site(db_session, "config-at-site")
    repo = SiteRepository(db_session)

    v1_time = _utc(2026, 9, 10, 0, 0)
    v2_time = _utc(2026, 9, 12, 0, 0)

    v1 = SiteConfigHistory(site_id=site.id, version=1, config={"a": 1}, changed_at=v1_time)
    v2 = SiteConfigHistory(site_id=site.id, version=2, config={"a": 2}, changed_at=v2_time)
    db_session.add(v1)
    db_session.add(v2)
    await db_session.flush()

    # At 2026-09-11: v1 should be returned
    at_v1 = await repo.get_config_at(site.id, _utc(2026, 9, 11, 12, 0))
    assert at_v1 is not None
    assert at_v1.version == 1

    # At 2026-09-13: v2 should be returned
    at_v2 = await repo.get_config_at(site.id, _utc(2026, 9, 13, 12, 0))
    assert at_v2 is not None
    assert at_v2.version == 2


# ---------------------------------------------------------------------------
# 8.x  Baseline list_for_site range query
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_baseline_telemetry_list_range(db_session: AsyncSession) -> None:
    """list_for_site correctly filters baseline_telemetry by time range."""
    site = await _seed_site(db_session, "bsl-range-site")
    repo = BaselineTelemetryRepository(db_session)

    ticks = [
        _utc(2026, 9, 12, 10, 0),
        _utc(2026, 9, 12, 11, 0),
        _utc(2026, 9, 12, 12, 0),
    ]
    for tick in ticks:
        db_session.add(BaselineTelemetry(
            site_id=site.id, at=tick, soc_kwh=50.0, diesel_on=False,
            diesel_kw=0.0, batt_kw=0.0, solar_kw=2.0, load_kw=3.0,
            source="baseline", config_version=1,
        ))
    await db_session.flush()

    rows = await repo.list_for_site(
        site.id,
        start_time=_utc(2026, 9, 12, 10, 0),
        end_time=_utc(2026, 9, 12, 12, 0),  # exclusive — 12:00 not included
    )
    assert len(rows) == 2
    assert rows[0].at == _utc(2026, 9, 12, 10, 0)
    assert rows[1].at == _utc(2026, 9, 12, 11, 0)
