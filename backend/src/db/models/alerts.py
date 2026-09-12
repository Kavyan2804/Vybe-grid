"""Alert model — DATA_MODEL.md §5.

Enums:
  ``alert_type``  — the six types from PRD.md §11.
                    ⚠ ASSUMPTION: these values are inferred; verify against PRD.md §11.
  ``alert_state`` — lifecycle: created → acknowledged → resolved.
"""

import enum

from sqlalchemy import (
    Enum,
    ForeignKey,
    Index,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column

from src.db.base import Base


class AlertType(str, enum.Enum):
    """The six alert types from PRD.md §11 / packages/contracts/events/alert.schema.json."""

    CRITICAL_LOAD_AT_RISK = "CRITICAL_LOAD_AT_RISK"
    LOW_SOC_RESERVE = "LOW_SOC_RESERVE"
    DIESEL_REQUIRED_SOON = "DIESEL_REQUIRED_SOON"
    SOLVER_FALLBACK_ACTIVE = "SOLVER_FALLBACK_ACTIVE"
    FORECAST_STALE = "FORECAST_STALE"
    BASELINE_DIVERGENCE = "BASELINE_DIVERGENCE"


class AlertState(str, enum.Enum):
    """Alert lifecycle: created → acknowledged → resolved."""

    CREATED = "created"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"


# Postgres enum types — created in the migration.
alert_type_enum = Enum(
    AlertType,
    name="alert_type",
    values_callable=lambda x: [e.value for e in x],
    create_constraint=True,
    metadata=Base.metadata,
    schema=None,
)
alert_state_enum = Enum(
    AlertState,
    name="alert_state",
    values_callable=lambda x: [e.value for e in x],
    create_constraint=True,
    metadata=Base.metadata,
    schema=None,
)


class Alert(Base):
    """An operational alert for a site.

    Columns taken verbatim from DATA_MODEL.md §5 ``alerts`` table.
    """

    __tablename__ = "alerts"
    __table_args__ = (
        # Partial unique index — at most one non-resolved alert per
        # (site_id, type, subject).  DATA_MODEL.md §5:
        #   CREATE UNIQUE INDEX alerts_open_uniq ON alerts (site_id, type, subject)
        #     WHERE state <> 'resolved';
        Index(
            "alerts_open_uniq",
            "site_id",
            "type",
            "subject",
            unique=True,
            postgresql_where=text("state <> 'resolved'"),
        ),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)  # e.g. "alr_..."
    site_id: Mapped[str] = mapped_column(
        Text, ForeignKey("sites.id", ondelete="CASCADE"), nullable=False
    )
    type: Mapped[AlertType] = mapped_column(
        alert_type_enum, nullable=False
    )
    subject: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )  # e.g. a counter or slot equivalent, if applicable
    state: Mapped[AlertState] = mapped_column(
        alert_state_enum, nullable=False
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    raised_at: Mapped[str] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False
    )  # clock of the thing that raised it
    received_at: Mapped[str] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False
    )  # server clock
    resolved_at: Mapped[str | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )  # starts the cooldown
    provenance: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True
    )  # which inputs produced it, with badges
