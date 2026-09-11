"""Initial schema — all Phase 1 tables.

Every [BUILD] table from DATA_MODEL.md §1–3 and §5:
  - sites, site_config_history
  - forecasts, dispatch_plans
  - telemetry, dispatch_log
  - baseline_telemetry, baseline_dispatch_log
  - alerts

Indexes:
  - dispatch_plans_tick_uniq   UNIQUE (site_id, tick_at)
  - alerts_open_uniq           UNIQUE (site_id, type, subject) WHERE state <> 'resolved'

Revision ID: 0001
Revises: (none)
Create Date: 2026-09-12
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP

# revision identifiers
revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ---------- Enums ----------
    alert_type_enum = sa.Enum(
        "DIESEL_REQUIRED_SOON",
        "SOC_LOW",
        "SOLAR_FORECAST_STALE",
        "SOLVER_FALLBACK_ACTIVE",
        "SOLVER_INFEASIBLE",
        "DIESEL_RUNTIME_EXCEEDED",
        name="alert_type",
    )
    alert_state_enum = sa.Enum(
        "created",
        "acknowledged",
        "resolved",
        name="alert_state",
    )
    alert_type_enum.create(op.get_bind(), checkfirst=True)
    alert_state_enum.create(op.get_bind(), checkfirst=True)

    # ---------- §1  Sites & configuration ----------
    op.create_table(
        "sites",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("timezone", sa.Text(), nullable=False),
        sa.Column("config_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("config", JSONB(), nullable=False),
        sa.Column(
            "created_at",
            TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    op.create_table(
        "site_config_history",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "site_id",
            sa.Text(),
            sa.ForeignKey("sites.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("config", JSONB(), nullable=False),
        sa.Column(
            "changed_at",
            TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    # ---------- §2  PLANNED domain ----------
    op.create_table(
        "forecasts",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "site_id",
            sa.Text(),
            sa.ForeignKey("sites.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("issued_at", TIMESTAMP(timezone=True), nullable=False),
        sa.Column("horizon_hours", sa.Integer(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("stale", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("series", JSONB(), nullable=False),
    )

    op.create_table(
        "dispatch_plans",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "site_id",
            sa.Text(),
            sa.ForeignKey("sites.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("tick_at", TIMESTAMP(timezone=True), nullable=False),
        sa.Column(
            "forecast_id",
            sa.BigInteger(),
            sa.ForeignKey("forecasts.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("config_version", sa.Integer(), nullable=False),
        sa.Column("starting_soc_kwh", sa.Real(), nullable=False),
        sa.Column("series", JSONB(), nullable=False),
        sa.Column("objective_cost", sa.Real(), nullable=True),
        sa.Column("solver_status", sa.Text(), nullable=False),
        sa.Column("solve_ms", sa.Integer(), nullable=True),
        sa.Column("source", sa.Text(), nullable=False),
    )

    op.create_index(
        "dispatch_plans_tick_uniq",
        "dispatch_plans",
        ["site_id", "tick_at"],
        unique=True,
    )

    # ---------- §3  ACTUAL domain ----------
    op.create_table(
        "telemetry",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "site_id",
            sa.Text(),
            sa.ForeignKey("sites.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("at", TIMESTAMP(timezone=True), nullable=False),
        sa.Column("soc_kwh", sa.Real(), nullable=False),
        sa.Column("diesel_on", sa.Boolean(), nullable=False),
        sa.Column("diesel_kw", sa.Real(), nullable=False),
        sa.Column("batt_kw", sa.Real(), nullable=False),
        sa.Column("solar_kw", sa.Real(), nullable=False),
        sa.Column("load_kw", sa.Real(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("config_version", sa.Integer(), nullable=False),
    )

    op.create_table(
        "dispatch_log",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "plan_id",
            sa.BigInteger(),
            sa.ForeignKey("dispatch_plans.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("hour_index", sa.Integer(), nullable=False),
        sa.Column("executed_at", TIMESTAMP(timezone=True), nullable=False),
        sa.Column("decision", JSONB(), nullable=False),
    )

    # ---------- §3  Baseline (schema only in Phase 1) ----------
    op.create_table(
        "baseline_telemetry",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "site_id",
            sa.Text(),
            sa.ForeignKey("sites.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("at", TIMESTAMP(timezone=True), nullable=False),
        sa.Column("soc_kwh", sa.Real(), nullable=False),
        sa.Column("diesel_on", sa.Boolean(), nullable=False),
        sa.Column("diesel_kw", sa.Real(), nullable=False),
        sa.Column("batt_kw", sa.Real(), nullable=False),
        sa.Column("solar_kw", sa.Real(), nullable=False),
        sa.Column("load_kw", sa.Real(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False, server_default="baseline"),
        sa.Column("config_version", sa.Integer(), nullable=False),
    )

    op.create_table(
        "baseline_dispatch_log",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "plan_id",
            sa.BigInteger(),
            sa.ForeignKey("dispatch_plans.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("hour_index", sa.Integer(), nullable=False),
        sa.Column("executed_at", TIMESTAMP(timezone=True), nullable=False),
        sa.Column("decision", JSONB(), nullable=False),
    )

    # ---------- §5  Alerts ----------
    op.create_table(
        "alerts",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column(
            "site_id",
            sa.Text(),
            sa.ForeignKey("sites.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("type", alert_type_enum, nullable=False),
        sa.Column("subject", sa.Text(), nullable=True),
        sa.Column("state", alert_state_enum, nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("raised_at", TIMESTAMP(timezone=True), nullable=False),
        sa.Column("received_at", TIMESTAMP(timezone=True), nullable=False),
        sa.Column("resolved_at", TIMESTAMP(timezone=True), nullable=True),
        sa.Column("provenance", JSONB(), nullable=True),
    )

    op.create_index(
        "alerts_open_uniq",
        "alerts",
        ["site_id", "type", "subject"],
        unique=True,
        postgresql_where=sa.text("state <> 'resolved'"),
    )


def downgrade() -> None:
    op.drop_table("alerts")
    op.drop_table("baseline_dispatch_log")
    op.drop_table("baseline_telemetry")
    op.drop_table("dispatch_log")
    op.drop_table("telemetry")
    op.drop_index("dispatch_plans_tick_uniq", table_name="dispatch_plans")
    op.drop_table("dispatch_plans")
    op.drop_table("forecasts")
    op.drop_table("site_config_history")
    op.drop_table("sites")

    sa.Enum(name="alert_state").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="alert_type").drop(op.get_bind(), checkfirst=True)
