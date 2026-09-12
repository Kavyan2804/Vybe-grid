"""Align alert_type enum with packages/contracts/events/alert.schema.json.

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-13
"""

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

_NEW = (
    "CRITICAL_LOAD_AT_RISK",
    "LOW_SOC_RESERVE",
    "DIESEL_REQUIRED_SOON",
    "SOLVER_FALLBACK_ACTIVE",
    "FORECAST_STALE",
    "BASELINE_DIVERGENCE",
)

_OLD = (
    "DIESEL_REQUIRED_SOON",
    "SOC_LOW",
    "SOLAR_FORECAST_STALE",
    "SOLVER_FALLBACK_ACTIVE",
    "SOLVER_INFEASIBLE",
    "DIESEL_RUNTIME_EXCEEDED",
)


def upgrade() -> None:
    bind = op.get_bind()
    # Recreate the enum so greenfield (0001 already correct) and legacy DBs both converge.
    op.execute("ALTER TABLE alerts ALTER COLUMN type TYPE text USING type::text")
    op.execute("DROP TYPE IF EXISTS alert_type")
    values = ", ".join(f"'{v}'" for v in _NEW)
    op.execute(f"CREATE TYPE alert_type AS ENUM ({values})")
    op.execute(
        """
        UPDATE alerts SET type = CASE type
            WHEN 'SOC_LOW' THEN 'LOW_SOC_RESERVE'
            WHEN 'SOLAR_FORECAST_STALE' THEN 'FORECAST_STALE'
            WHEN 'SOLVER_INFEASIBLE' THEN 'SOLVER_FALLBACK_ACTIVE'
            WHEN 'DIESEL_RUNTIME_EXCEEDED' THEN 'DIESEL_REQUIRED_SOON'
            ELSE type
        END
        """
    )
    op.execute(
        "ALTER TABLE alerts ALTER COLUMN type TYPE alert_type USING type::alert_type"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE alerts ALTER COLUMN type TYPE text USING type::text")
    op.execute("DROP TYPE IF EXISTS alert_type")
    values = ", ".join(f"'{v}'" for v in _OLD)
    op.execute(f"CREATE TYPE alert_type AS ENUM ({values})")
    op.execute(
        """
        UPDATE alerts SET type = CASE type
            WHEN 'LOW_SOC_RESERVE' THEN 'SOC_LOW'
            WHEN 'FORECAST_STALE' THEN 'SOLAR_FORECAST_STALE'
            WHEN 'CRITICAL_LOAD_AT_RISK' THEN 'SOLVER_INFEASIBLE'
            WHEN 'BASELINE_DIVERGENCE' THEN 'DIESEL_RUNTIME_EXCEEDED'
            ELSE type
        END
        """
    )
    op.execute(
        "ALTER TABLE alerts ALTER COLUMN type TYPE alert_type USING type::alert_type"
    )
