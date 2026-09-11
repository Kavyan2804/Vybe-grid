"""Dispatch-plan model — DATA_MODEL.md §2 PLANNED domain."""

from sqlalchemy import (
    BigInteger,
    ForeignKey,
    Integer,
    Float,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column

from src.db.base import Base


class DispatchPlan(Base):
    """A 24-hour dispatch plan produced by the optimizer.

    Plans are append-only — a revised outlook is a new row at a new
    ``tick_at``, never an update (DATA_MODEL.md §0, §6).

    Columns taken verbatim from DATA_MODEL.md §2 ``dispatch_plans`` table.
    """

    __tablename__ = "dispatch_plans"
    __table_args__ = (
        # Natural key — a rolling loop that fires the same tick twice is a
        # bug this index catches rather than silently duplicating a plan.
        UniqueConstraint("site_id", "tick_at", name="dispatch_plans_tick_uniq"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    site_id: Mapped[str] = mapped_column(
        Text, ForeignKey("sites.id", ondelete="CASCADE"), nullable=False
    )
    tick_at: Mapped[str] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False
    )  # when this solve ran
    forecast_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("forecasts.id", ondelete="SET NULL"), nullable=True
    )  # the exact forecast this plan was solved against
    config_version: Mapped[int] = mapped_column(Integer, nullable=False)
    starting_soc_kwh: Mapped[float] = mapped_column(
        Real, nullable=False
    )  # read from telemetry, never from a previous plan (ARCHITECTURE.md §4)
    series: Mapped[dict] = mapped_column(
        JSONB, nullable=False
    )  # 24 hourly decisions — see API_CONTRACT.md §2
    objective_cost: Mapped[float] = mapped_column(Real, nullable=True)
    solver_status: Mapped[str] = mapped_column(
        Text, nullable=False
    )  # "optimal" | "feasible" | "infeasible" | "timeout"
    solve_ms: Mapped[int] = mapped_column(Integer, nullable=True)
    source: Mapped[str] = mapped_column(
        Text, nullable=False
    )  # "milp" | "fallback" — see ARCHITECTURE.md §7
