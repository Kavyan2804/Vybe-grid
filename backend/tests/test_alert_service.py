"""Tests for the in-memory Phase 3 alert service and legacy behavior."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app
from src.schemas.alerts import AlertCreateRequest, AlertSeverity, AlertState, AlertType
from src.services.alert_service import (
    AlertNotFoundError,
    AlertTransitionError,
    InMemoryAlertService,
)


def request(site_id: str = "site-a") -> AlertCreateRequest:
    return AlertCreateRequest(
        site_id=site_id,
        severity=AlertSeverity.CRITICAL,
        title="Power failure",
        message="Backup generation is required.",
    )


class _FakeClock:
    def __init__(self, value: datetime) -> None:
        self.value = value

    def __call__(self) -> datetime:
        return self.value


def raise_alert(
    service: InMemoryAlertService,
    *,
    subject: str | None = "battery",
    raised_at: datetime | None = None,
):
    return service.raise_alert(
        site_id="site-a",
        alert_type=AlertType.LOW_SOC_RESERVE,
        subject=subject,
        severity=AlertSeverity.WARNING,
        title="Low reserve",
        message="Battery reserve is below target.",
        raised_at=raised_at,
    )


def test_creates_alert_with_separate_raised_and_received_timestamps() -> None:
    received = datetime(2026, 1, 1, 12, tzinfo=UTC)
    raised = received - timedelta(minutes=5)
    service = InMemoryAlertService(seed_demo=False, clock=lambda: received)

    alert = raise_alert(service, raised_at=raised)

    assert alert.state is AlertState.CREATED
    assert alert.raised_at == raised
    assert alert.received_at == received
    assert alert.resolved_at is None


def test_duplicate_active_alert_is_suppressed() -> None:
    service = InMemoryAlertService(seed_demo=False)

    first = raise_alert(service)
    duplicate = raise_alert(service)

    assert duplicate.id == first.id
    assert service.list_active_alerts() == [first]


def test_different_subjects_create_separate_alerts() -> None:
    service = InMemoryAlertService(seed_demo=False)

    first = raise_alert(service, subject="battery-a")
    second = raise_alert(service, subject="battery-b")

    assert first.id != second.id
    assert len(service.list_active_alerts()) == 2


def test_acknowledge_and_resolve_follow_lifecycle() -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    service = InMemoryAlertService(seed_demo=False, clock=lambda: now)
    alert = raise_alert(service)

    acknowledged = service.acknowledge(alert.id)
    resolved = service.resolve(alert.id)

    assert acknowledged.state is AlertState.ACKNOWLEDGED
    assert resolved.state is AlertState.RESOLVED
    assert resolved.resolved_at == now
    assert service.list_active_alerts() == []


def test_invalid_transition_and_missing_id_raise_compatible_errors() -> None:
    service = InMemoryAlertService(seed_demo=False)
    alert = raise_alert(service)
    service.resolve(alert.id)

    with pytest.raises(AlertTransitionError, match="cannot be acknowledged"):
        service.acknowledge(alert.id)
    with pytest.raises(AlertTransitionError, match="already resolved"):
        service.resolve(alert.id)
    with pytest.raises(AlertNotFoundError):
        service.resolve("missing")
    with pytest.raises(AlertNotFoundError):
        service.acknowledge("missing")


def test_resolution_cooldown_suppresses_retrigger() -> None:
    clock = _FakeClock(datetime(2026, 1, 1, tzinfo=UTC))
    service = InMemoryAlertService(seed_demo=False, clock=clock)
    first = raise_alert(service)
    service.resolve(first.id)

    clock.value += timedelta(seconds=59)
    retriggered = raise_alert(service)

    assert retriggered.id == first.id
    assert len(service.list()[1]) == 1


def test_cooldown_expiry_creates_new_alert() -> None:
    clock = _FakeClock(datetime(2026, 1, 1, tzinfo=UTC))
    service = InMemoryAlertService(seed_demo=False, clock=clock)
    first = raise_alert(service)
    service.resolve(first.id)

    clock.value += timedelta(seconds=60)
    retriggered = raise_alert(service)

    assert retriggered.id != first.id
    assert len(service.list_active_alerts()) == 1


def test_legacy_phase1_create_and_api_behavior_remain_compatible() -> None:
    service = InMemoryAlertService(seed_demo=False)
    service.create(request())
    service.create(request())

    total, items = service.list(site_id="site-a", severity=AlertSeverity.CRITICAL, limit=1)
    assert total == 2
    assert len(items) == 1


@pytest.mark.asyncio
async def test_alert_api_actions_remain_compatible() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        missing = await client.post("/api/alerts/unknown/resolve")
        assert missing.status_code == 404
        created = await client.post(
            "/api/alerts",
            json=request("api-alert-site").model_dump(mode="json"),
        )
        assert created.status_code == 201
        alert_id = created.json()["id"]
        assert (await client.post(f"/api/alerts/{alert_id}/acknowledge")).status_code == 200
        assert (await client.post(f"/api/alerts/{alert_id}/resolve")).status_code == 200
