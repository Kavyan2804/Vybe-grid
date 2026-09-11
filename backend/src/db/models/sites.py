"""Sites & site-config-history models — DATA_MODEL.md §1."""

from sqlalchemy import (
    BigInteger,
    ForeignKey,
    Integer,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import Base


class Site(Base):
    """A microgrid site.

    Columns taken verbatim from DATA_MODEL.md §1 ``sites`` table.
    """

    __tablename__ = "sites"

    id: Mapped[str] = mapped_column(Text, primary_key=True)  # e.g. "site-001"
    name: Mapped[str] = mapped_column(Text, nullable=False)
    timezone: Mapped[str] = mapped_column(Text, nullable=False)  # IANA, e.g. "Asia/Kolkata"
    config_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    config: Mapped[dict] = mapped_column(JSONB, nullable=False)  # battery, diesel, load-shape params
    created_at: Mapped[str] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    # Relationships
    config_history: Mapped[list["SiteConfigHistory"]] = relationship(
        back_populates="site", cascade="all, delete-orphan"
    )


class SiteConfigHistory(Base):
    """Immutable snapshot of a site config at a given version.

    DATA_MODEL.md §1 ``site_config_history``.
    """

    __tablename__ = "site_config_history"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    site_id: Mapped[str] = mapped_column(
        Text, ForeignKey("sites.id", ondelete="CASCADE"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    config: Mapped[dict] = mapped_column(JSONB, nullable=False)  # full snapshot
    changed_at: Mapped[str] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    # Relationships
    site: Mapped["Site"] = relationship(back_populates="config_history")
