"""Tests for in-memory alert management and API behavior."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app
from src.schemas.alerts import AlertCreateRequest, AlertSeverity, AlertStatus
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


def test_alert_service_supports_filters_and_pagination() -> None:
    service = InMemoryAlertService(seed_demo=False)
    service.create(request())
    service.create(request("site-b"))
    service.create(request())

    total, items = service.list(site_id="site-a", severity=AlertSeverity.CRITICAL, limit=1)
    assert total == 2
    assert len(items) == 1
    assert items[0].site_id == "site-a"
    assert service.list(offset=2, limit=1)[1][0].id.endswith("005")


def test_alert_service_valid_transitions() -> None:
    service = InMemoryAlertService(seed_demo=False)
    alert = service.create(request())

    assert service.acknowledge(alert.id).status is AlertStatus.ACKNOWLEDGED
    assert service.resolve(alert.id).status is AlertStatus.RESOLVED


def test_alert_service_rejects_invalid_transitions_and_unknown_ids() -> None:
    service = InMemoryAlertService(seed_demo=False)
    alert = service.create(request())
    service.resolve(alert.id)

    with pytest.raises(AlertTransitionError, match="cannot be acknowledged"):
        service.acknowledge(alert.id)
    with pytest.raises(AlertTransitionError, match="already resolved"):
        service.resolve(alert.id)
    with pytest.raises(AlertNotFoundError):
        service.resolve("missing")
    with pytest.raises(AlertNotFoundError):
        service.acknowledge("missing")


@pytest.mark.asyncio
async def test_alert_api_create_get_filter_paginate_and_actions() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {
            "site_id": "api-alert-site",
            "severity": "warning",
            "title": "Low reserve",
            "message": "Reserve is below target.",
        }
        created = await client.post("/api/alerts", json=payload)
        assert created.status_code == 201
        alert_id = created.json()["id"]

        fetched = await client.get(f"/api/alerts/{alert_id}")
        assert fetched.status_code == 200
        listed = await client.get(
            "/api/alerts?site_id=api-alert-site&severity=warning&status=active&limit=1"
        )
        assert listed.status_code == 200
        assert listed.json()["total"] == 1
        assert len(listed.json()["items"]) == 1

        acknowledged = await client.post(f"/api/alerts/{alert_id}/acknowledge")
        assert acknowledged.status_code == 200
        assert acknowledged.json()["state"] == "acknowledged"
        resolved = await client.post(f"/api/alerts/{alert_id}/resolve")
        assert resolved.status_code == 200
        assert resolved.json()["state"] == "resolved"


@pytest.mark.asyncio
async def test_alert_api_returns_errors_for_missing_and_invalid_transitions() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        missing = await client.post("/api/alerts/unknown/resolve")
        assert missing.status_code == 404
        created = await client.post("/api/alerts", json=request().model_dump(mode="json"))
        alert_id = created.json()["id"]
        assert (await client.post(f"/api/alerts/{alert_id}/resolve")).status_code == 200
        assert (await client.post(f"/api/alerts/{alert_id}/acknowledge")).status_code == 409
        assert (await client.post(f"/api/alerts/{alert_id}/resolve")).status_code == 409
        invalid = await client.get("/api/alerts?limit=0")
        assert invalid.status_code == 422
