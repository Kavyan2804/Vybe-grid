"""SQLAlchemy 2.0 declarative base and shared metadata."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class for all GridPilot ORM models."""

    pass
