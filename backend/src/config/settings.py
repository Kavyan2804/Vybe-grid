"""
Application settings — reads from environment / .env file.

Every variable here corresponds to a line in .env.example at the repo root.
Database-session setup is NOT here — that belongs in optimizer/infrastructure/db/
and will be owned by Dhruvi.
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Validated, typed configuration for the GridPilot backend."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",  # ignore NEXT_PUBLIC_* and other dashboard/infra vars
    )

    # ── Database ────────────────────────────────────────────────────────
    database_url: str = "postgresql+asyncpg://gridpilot:gridpilot@localhost:5432/gridpilot"

    # ── Rolling horizon (PRD.md §4, §14) ────────────────────────────────
    tick_interval_minutes: int = 60
    horizon_hours: int = 24
    solve_timeout_seconds: int = 20

    # ── Forecast provider ───────────────────────────────────────────────
    forecast_provider: str = "openmeteo"

    # ── Dispatch target (PRD.md §9) ─────────────────────────────────────
    dispatch_adapter: str = "simulator"

    # ── Site ────────────────────────────────────────────────────────────
    default_site_id: str = "example-site"


def get_settings() -> Settings:
    """Return a cached Settings instance.

    FastAPI endpoints should use ``Depends(get_settings)`` so tests can
    override this with a custom Settings object.
    """
    return _settings


_settings = Settings()

