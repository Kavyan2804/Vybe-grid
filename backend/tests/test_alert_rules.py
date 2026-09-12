"""Tests for Phase 3 alert models and pure rules."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from src.alerts.rules import (
    baseline_divergence,
    critical_load_at_risk,
    diesel_required_soon,
    forecast_stale,
    low_soc_reserve,
    solver_fallback_active,
)
from src.schemas.alerts import Alert, AlertSeverity, AlertState, AlertType
from src.schemas.common import ProvenanceBadge

AT = datetime(2026, 1, 1, tzinfo=UTC)
NAIVE_AT = AT.replace(tzinfo=None)


def test_each_rule_returns_its_contract_type() -> None:
    results = [
        low_soc_reserve(site_id="site-a", soc_kwh=10, minimum_reserve_kwh=10, raised_at=AT),
        diesel_required_soon(
            site_id="site-a", hours_until_required=1, threshold_hours=2, raised_at=AT
        ),
        critical_load_at_risk(
            site_id="site-a",
            critical_load_kw=10,
            available_supply_kw=9,
            minimum_margin_kw=0,
            raised_at=AT,
        ),
        solver_fallback_active(site_id="site-a", fallback_active=True, raised_at=AT),
        forecast_stale(
            site_id="site-a", forecast_age_minutes=61, maximum_age_minutes=60, raised_at=AT
        ),
        baseline_divergence(
            site_id="site-a", optimized_cost=11, baseline_cost=10, tolerance=0, raised_at=AT
        ),
    ]

    assert [result.type for result in results if result is not None] == list(AlertType)
    assert all(result is not None and result.raised_at == AT for result in results)


def test_rules_return_no_alert_when_conditions_are_safe() -> None:
    assert (
        low_soc_reserve(site_id="site-a", soc_kwh=11, minimum_reserve_kwh=10, raised_at=AT) is None
    )
    assert (
        diesel_required_soon(
            site_id="site-a", hours_until_required=3, threshold_hours=2, raised_at=AT
        )
        is None
    )
    assert (
        critical_load_at_risk(
            site_id="site-a",
            critical_load_kw=10,
            available_supply_kw=11,
            minimum_margin_kw=1,
            raised_at=AT,
        )
        is None
    )
    assert solver_fallback_active(site_id="site-a", fallback_active=False, raised_at=AT) is None
    assert (
        forecast_stale(
            site_id="site-a", forecast_age_minutes=60, maximum_age_minutes=60, raised_at=AT
        )
        is None
    )
    assert (
        baseline_divergence(
            site_id="site-a", optimized_cost=10, baseline_cost=10, tolerance=0, raised_at=AT
        )
        is None
    )


def test_rules_are_deterministic_and_include_provenance() -> None:
    kwargs = {"site_id": "site-a", "soc_kwh": 5, "minimum_reserve_kwh": 10, "raised_at": AT}
    first = low_soc_reserve(**kwargs)
    second = low_soc_reserve(**kwargs)

    assert first == second
    assert first is not None
    assert first.provenance == [ProvenanceBadge.SIMULATED]


def test_rule_result_rejects_naive_timestamp() -> None:
    with pytest.raises(ValidationError, match="explicit timezone offset"):
        solver_fallback_active(
            site_id="site-a",
            fallback_active=True,
            raised_at=NAIVE_AT,
        )


def test_phase3_alert_model_has_typed_fields_and_timezone_validation() -> None:
    alert = Alert(
        id="alert-1",
        site_id="site-a",
        type=AlertType.FORECAST_STALE,
        subject="forecast-1",
        state=AlertState.CREATED,
        severity=AlertSeverity.WARNING,
        title="Forecast is stale",
        message="Forecast age exceeded the configured limit.",
        created_at=AT,
        raised_at=AT,
        received_at=AT,
        provenance=[ProvenanceBadge.SIMULATED],
    )

    assert alert.type is AlertType.FORECAST_STALE
    assert alert.state is AlertState.CREATED
    assert alert.provenance == [ProvenanceBadge.SIMULATED]

    with pytest.raises(ValidationError, match="explicit timezone offset"):
        Alert(
            id="alert-2",
            site_id="site-a",
            severity=AlertSeverity.WARNING,
            title="Invalid",
            message="Invalid timestamp",
            created_at=AT,
            raised_at=NAIVE_AT,
        )


def test_alert_lifecycle_rejects_invalid_transitions() -> None:
    alert = Alert(
        id="alert-1",
        site_id="site-a",
        severity=AlertSeverity.INFO,
        title="Test",
        message="Test alert",
        created_at=AT,
    )

    acknowledged = alert.transition_to(AlertState.ACKNOWLEDGED)
    resolved = acknowledged.transition_to(AlertState.RESOLVED)
    assert acknowledged.state is AlertState.ACKNOWLEDGED
    assert resolved.state is AlertState.RESOLVED

    with pytest.raises(ValueError, match="invalid alert transition"):
        resolved.transition_to(AlertState.ACKNOWLEDGED)
