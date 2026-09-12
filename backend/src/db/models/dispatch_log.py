"""Dispatch-log model — DATA_MODEL.md §3 ACTUAL domain."""

from sqlalchemy import (
    BigInteger,
    ForeignKey,
    Integer,
)
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column

from src.db.base import Base


class DispatchLog(Base):
    """An executed dispatch decision (hour-0 of a plan).

    Columns taken verbatim from DATA_MODEL.md §3 ``dispatch_log`` table.
    """

    __tablename__ = "dispatch_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    plan_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("dispatch_plans.id", ondelete="CASCADE"), nullable=False
    )
    hour_index: Mapped[int] = mapped_column(
        Integer, nullable=False
    )  # always 0 today — a plan's hour 0 is the only hour ever executed
    executed_at: Mapped[str] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False
    )
    decision: Mapped[dict] = mapped_column(
        JSONB, nullable=False
    )  # the exact decision sent to DispatchPort.execute()
