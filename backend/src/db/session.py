"""Async session factory and FastAPI dependency.

Usage in a FastAPI router::

    from src.db.session import get_db_session

    @router.get("/example")
    async def example(session: AsyncSession = Depends(get_db_session)):
        ...
"""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from src.config.settings import settings

engine = create_async_engine(
    settings.database_url,
    echo=False,
    future=True,
)

async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI ``Depends``-compatible async generator.

    Yields an ``AsyncSession``, commits on success, rolls back on error,
    and always closes the session.
    """
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
