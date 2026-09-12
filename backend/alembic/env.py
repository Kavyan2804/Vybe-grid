"""Alembic environment configuration.

Reads ``DATABASE_URL`` from the environment and converts the async
``postgresql+asyncpg`` scheme to the sync ``postgresql+psycopg2`` variant
that Alembic's synchronous migration runner requires.
"""

import os
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# Make sure ``src`` is importable so models can be discovered.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.db.base import Base  # noqa: E402
import src.db.models  # noqa: E402, F401 — triggers model registration on Base.metadata

# Alembic Config object — provides access to alembic.ini values.
config = context.config

# Set up Python logging from alembic.ini.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Target metadata for ``--autogenerate``.
target_metadata = Base.metadata


def _get_sync_url() -> str:
    """Return a psycopg2 URL derived from the DATABASE_URL env var."""
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        raise RuntimeError(
            "DATABASE_URL environment variable is not set.  "
            "Example: DATABASE_URL=postgresql+asyncpg://gridpilot:gridpilot@localhost:5432/gridpilot"
        )
    # Alembic runs synchronously — swap the async driver for psycopg2.
    return url.replace("postgresql+asyncpg", "postgresql+psycopg2")


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode — emit SQL to stdout."""
    url = _get_sync_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against a live database."""
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = _get_sync_url()

    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
