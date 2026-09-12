"""Test: ``alembic upgrade head`` creates every expected table and enum."""

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


EXPECTED_TABLES = {
    "sites",
    "site_config_history",
    "forecasts",
    "dispatch_plans",
    "telemetry",
    "dispatch_log",
    "baseline_telemetry",
    "baseline_dispatch_log",
    "alerts",
}


@pytest.mark.asyncio
async def test_upgrade_head_creates_all_tables(db_session: AsyncSession) -> None:
    """After ``alembic upgrade head``, all 9 tables from DATA_MODEL.md must exist."""
    result = await db_session.execute(
        text(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_type = 'BASE TABLE'"
        )
    )
    actual_tables = {row[0] for row in result.fetchall()}
    # Filter out alembic's own table
    actual_tables.discard("alembic_version")

    missing = EXPECTED_TABLES - actual_tables
    assert not missing, f"Missing tables after migration: {missing}"


@pytest.mark.asyncio
async def test_enums_exist(db_session: AsyncSession) -> None:
    """The ``alert_type`` and ``alert_state`` Postgres enums must exist."""
    result = await db_session.execute(
        text(
            "SELECT typname FROM pg_type "
            "WHERE typname IN ('alert_type', 'alert_state')"
        )
    )
    actual_enums = {row[0] for row in result.fetchall()}
    assert "alert_type" in actual_enums, "alert_type enum missing"
    assert "alert_state" in actual_enums, "alert_state enum missing"


@pytest.mark.asyncio
async def test_dispatch_plans_tick_uniq_index_exists(db_session: AsyncSession) -> None:
    """The UNIQUE index ``dispatch_plans_tick_uniq`` must exist."""
    result = await db_session.execute(
        text(
            "SELECT indexname FROM pg_indexes "
            "WHERE tablename = 'dispatch_plans' AND indexname = 'dispatch_plans_tick_uniq'"
        )
    )
    row = result.fetchone()
    assert row is not None, "dispatch_plans_tick_uniq index missing"


@pytest.mark.asyncio
async def test_alerts_open_uniq_index_exists(db_session: AsyncSession) -> None:
    """The partial UNIQUE index ``alerts_open_uniq`` must exist."""
    result = await db_session.execute(
        text(
            "SELECT indexname FROM pg_indexes "
            "WHERE tablename = 'alerts' AND indexname = 'alerts_open_uniq'"
        )
    )
    row = result.fetchone()
    assert row is not None, "alerts_open_uniq index missing"
