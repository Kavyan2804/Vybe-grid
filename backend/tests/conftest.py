"""Shared test fixtures — testcontainers + Alembic + async session.

Spins up an ephemeral TimescaleDB container, runs ``alembic upgrade head``,
and yields an ``AsyncSession`` for each test.
"""

import os
import asyncio
from collections.abc import AsyncGenerator, Generator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from testcontainers.postgres import PostgresContainer


# ---------------------------------------------------------------------------
# Container + Alembic (session-scoped — one container per test run)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """Create a single event loop for the entire test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
def pg_container() -> Generator[PostgresContainer, None, None]:
    """Start a TimescaleDB container for the test session."""
    container = (
        PostgresContainer(
            image="timescale/timescaledb:latest-pg16",
            username="gridpilot",
            password="gridpilot",
            dbname="gridpilot",
        )
        .with_exposed_ports(5432)
    )
    container.start()
    yield container
    container.stop()


@pytest.fixture(scope="session")
def database_url(pg_container: PostgresContainer) -> str:
    """Return the async database URL for the testcontainer."""
    host = pg_container.get_container_host_ip()
    port = pg_container.get_exposed_port(5432)
    return f"postgresql+asyncpg://gridpilot:gridpilot@{host}:{port}/gridpilot"


@pytest.fixture(scope="session")
def database_url_sync(pg_container: PostgresContainer) -> str:
    """Return the sync (psycopg2) database URL for Alembic."""
    host = pg_container.get_container_host_ip()
    port = pg_container.get_exposed_port(5432)
    return f"postgresql+psycopg2://gridpilot:gridpilot@{host}:{port}/gridpilot"


@pytest.fixture(scope="session", autouse=True)
def run_migrations(database_url: str) -> None:
    """Run ``alembic upgrade head`` once against the testcontainer."""
    from alembic.config import Config
    from alembic import command

    # Point Alembic at the testcontainer.
    os.environ["DATABASE_URL"] = database_url

    alembic_cfg = Config(
        os.path.join(os.path.dirname(__file__), "..", "alembic.ini")
    )
    alembic_cfg.set_main_option(
        "script_location",
        os.path.join(os.path.dirname(__file__), "..", "alembic"),
    )
    command.upgrade(alembic_cfg, "head")


# ---------------------------------------------------------------------------
# Async session (function-scoped — each test gets a rolled-back transaction)
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def async_engine(database_url: str):
    """Create an async engine pointing at the testcontainer."""
    engine = create_async_engine(database_url, echo=False)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(async_engine) -> AsyncGenerator[AsyncSession, None]:
    """Yield an ``AsyncSession`` that rolls back after each test.

    This keeps tests isolated without the cost of re-creating tables.
    """
    async_session = async_sessionmaker(
        async_engine, class_=AsyncSession, expire_on_commit=False
    )
    async with async_session() as session:
        async with session.begin():
            yield session
            # Roll back — each test sees a clean state.
            await session.rollback()
