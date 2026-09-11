"""Telemetry model — DATA_MODEL.md §3 ACTUAL domain."""

from sqlalchemy import (
    BigInteger,
    Boolean,
    ForeignKey,
    Integer,
    Real,
    Text,
)
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column

from src.db.base import Base


class Telemetry(Base):
    """A single telemetry reading for a site.

    ``TelemetryRepository.latest_soc(site_id)`` is the only legal source
    of a tick's starting state (DATA_MODEL.md §3).

    Columns taken verbatim from DATA_MODEL.md §3 ``telemetry`` table.
    """

    __tablename__ = "telemetry"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    site_id: Mapped[str] = mapped_column(
        Text, ForeignKey("sites.id", ondelete="CASCADE"), nullable=False
    )
    at: Mapped[str] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False
    )
    soc_kwh: Mapped[float] = mapped_column(Real, nullable=False)
    diesel_on: Mapped[bool] = mapped_column(Boolean, nullable=False)
    diesel_kw: Mapped[float] = mapped_column(Real, nullable=False)
    batt_kw: Mapped[float] = mapped_column(
        Real, nullable=False
    )  # signed — positive charging, negative discharging
    solar_kw: Mapped[float] = mapped_column(Real, nullable=False)
    load_kw: Mapped[float] = mapped_column(Real, nullable=False)
    source: Mapped[str] = mapped_column(
        Text, nullable=False
    )  # "simulator" | "hardware" | "fallback"
    config_version: Mapped[int] = mapped_column(Integer, nullable=False)
