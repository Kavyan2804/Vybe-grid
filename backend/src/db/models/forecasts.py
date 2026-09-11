"""Forecast model — DATA_MODEL.md §2 PLANNED domain."""

from sqlalchemy import (
    BigInteger,
    Boolean,
    ForeignKey,
    Integer,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column

from src.db.base import Base


class Forecast(Base):
    """A weather/solar/load forecast fetched for a site.

    Columns taken verbatim from DATA_MODEL.md §2 ``forecasts`` table.
    """

    __tablename__ = "forecasts"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    site_id: Mapped[str] = mapped_column(
        Text, ForeignKey("sites.id", ondelete="CASCADE"), nullable=False
    )
    issued_at: Mapped[str] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False
    )  # when the forecast was fetched
    horizon_hours: Mapped[int] = mapped_column(
        Integer, nullable=False
    )  # 24
    source: Mapped[str] = mapped_column(
        Text, nullable=False
    )  # "openmeteo" | "persistence_fallback"
    stale: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )  # true when reused past its expected refresh interval
    series: Mapped[dict] = mapped_column(
        JSONB, nullable=False
    )  # array of {hour, ghi_w_m2, cloud_cover_pct, ...}
