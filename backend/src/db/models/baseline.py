"""Baseline models — DATA_MODEL.md §3.

Same shape as ``telemetry`` / ``dispatch_log``, ``source`` defaults to
``'baseline'``.  Populated every tick by ``baseline_service`` starting
Phase 3 — schema only in Phase 1.
"""

from sqlalchemy import (
    BigInteger,
    Boolean,
    ForeignKey,
    Integer,
    Real,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column

from src.db.base import Base


class BaselineTelemetry(Base):
    """Shadow telemetry from the greedy-baseline controller.

    Identical shape to ``telemetry``, source fixed to ``'baseline'``.
    """

    __tablename__ = "baseline_telemetry"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    site_id: Mapped[str] = mapped_column(
        Text, ForeignKey("sites.id", ondelete="CASCADE"), nullable=False
    )
    at: Mapped[str] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    soc_kwh: Mapped[float] = mapped_column(Real, nullable=False)
    diesel_on: Mapped[bool] = mapped_column(Boolean, nullable=False)
    diesel_kw: Mapped[float] = mapped_column(Real, nullable=False)
    batt_kw: Mapped[float] = mapped_column(Real, nullable=False)
    solar_kw: Mapped[float] = mapped_column(Real, nullable=False)
    load_kw: Mapped[float] = mapped_column(Real, nullable=False)
    source: Mapped[str] = mapped_column(
        Text, nullable=False, server_default="baseline"
    )
    config_version: Mapped[int] = mapped_column(Integer, nullable=False)


class BaselineDispatchLog(Base):
    """Shadow dispatch log from the greedy-baseline controller.

    Identical shape to ``dispatch_log``.
    """

    __tablename__ = "baseline_dispatch_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    plan_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("dispatch_plans.id", ondelete="CASCADE"),
        nullable=False,
    )
    hour_index: Mapped[int] = mapped_column(Integer, nullable=False)
    executed_at: Mapped[str] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    decision: Mapped[dict] = mapped_column(JSONB, nullable=False)
