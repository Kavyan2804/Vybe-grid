"""Application settings — reads from environment with dev defaults."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Central configuration.

    DATABASE_URL must use the ``postgresql+asyncpg://`` scheme for the
    async runtime.  ``database_url_sync`` derives the psycopg2 variant
    that Alembic uses for migrations.
    """

    database_url: str = (
        "postgresql+asyncpg://gridpilot:gridpilot@localhost:5432/gridpilot"
    )

    # Convenience: Alembic needs a sync driver URL.
    @property
    def database_url_sync(self) -> str:
        return self.database_url.replace(
            "postgresql+asyncpg", "postgresql+psycopg2"
        )

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
