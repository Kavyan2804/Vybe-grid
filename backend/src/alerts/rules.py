"""Pure Phase 3 alert condition rules.

The rules only evaluate supplied values. Persistence, deduplication, cooldowns,
and event publication belong to the alert service.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.schemas.alerts import AlertType
from src.schemas.common import ProvenanceBadge


class AlertRuleResult(BaseModel):
    """Deterministic alert candidate returned by a rule."""

    model_config = ConfigDict(extra="forbid")

    type: AlertType
    subject: str | None = Field(None, min_length=1, max_length=160)
    title: str
    raised_at: datetime
    provenance: list[ProvenanceBadge] = Field(default_factory=lambda: [ProvenanceBadge.SIMULATED])

    @field_validator("raised_at")
    @classmethod
    def require_timezone_aware_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("raised_at must include an explicit timezone offset")
        return value


def low_soc_reserve(
    *, site_id: str, soc_kwh: float, minimum_reserve_kwh: float, raised_at: datetime
) -> AlertRuleResult | None:
    """Raise when state of charge is at or below the configured reserve."""

    if soc_kwh > minimum_reserve_kwh:
        return None
    return _result(
        AlertType.LOW_SOC_RESERVE,
        site_id,
        "Low state-of-charge reserve",
        raised_at,
    )


def diesel_required_soon(
    *,
    site_id: str,
    hours_until_required: float,
    threshold_hours: float,
    raised_at: datetime,
) -> AlertRuleResult | None:
    """Raise when diesel is required within the configured lead time."""

    if hours_until_required > threshold_hours:
        return None
    return _result(
        AlertType.DIESEL_REQUIRED_SOON,
        site_id,
        "Diesel required soon",
        raised_at,
    )


def critical_load_at_risk(
    *,
    site_id: str,
    critical_load_kw: float,
    available_supply_kw: float,
    minimum_margin_kw: float,
    raised_at: datetime,
) -> AlertRuleResult | None:
    """Raise when available supply cannot maintain the configured critical margin."""

    if available_supply_kw - critical_load_kw >= minimum_margin_kw:
        return None
    return _result(
        AlertType.CRITICAL_LOAD_AT_RISK,
        site_id,
        "Critical load at risk",
        raised_at,
    )


def solver_fallback_active(
    *, site_id: str, fallback_active: bool, raised_at: datetime
) -> AlertRuleResult | None:
    """Raise when dispatch is operating on the solver fallback path."""

    if not fallback_active:
        return None
    return _result(
        AlertType.SOLVER_FALLBACK_ACTIVE,
        site_id,
        "Solver fallback active",
        raised_at,
    )


def forecast_stale(
    *,
    site_id: str,
    forecast_age_minutes: float,
    maximum_age_minutes: float,
    raised_at: datetime,
) -> AlertRuleResult | None:
    """Raise when forecast age exceeds the configured maximum."""

    if forecast_age_minutes <= maximum_age_minutes:
        return None
    return _result(AlertType.FORECAST_STALE, site_id, "Forecast is stale", raised_at)


def baseline_divergence(
    *,
    site_id: str,
    optimized_cost: float,
    baseline_cost: float,
    tolerance: float,
    raised_at: datetime,
) -> AlertRuleResult | None:
    """Raise when optimized operation costs more than baseline beyond tolerance."""

    if optimized_cost <= baseline_cost + tolerance:
        return None
    return _result(
        AlertType.BASELINE_DIVERGENCE,
        site_id,
        "Optimized operation diverged from baseline",
        raised_at,
    )


def _result(
    alert_type: AlertType, site_id: str, title: str, raised_at: datetime
) -> AlertRuleResult:
    return AlertRuleResult(
        type=alert_type,
        subject=site_id,
        title=title,
        raised_at=raised_at,
    )
