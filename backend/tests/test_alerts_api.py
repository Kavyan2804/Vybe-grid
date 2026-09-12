"""Focused API tests for Phase 3 alerts and Phase 1 compatibility."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from httpx import ASGITransport, AsyncClient

from src.api import alerts as alerts_api
from src.main import app
from src.schemas.alerts import AlertCreateRequest
from src.services.alert_service import InMemoryAlertService


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch):
    service = InMemoryAlertService(seed_demo=False, clock=lambda: datetime(2026, 1, 1, tzinfo=UTC))
    monkeypatch.setattr(alerts_api, "alert_service", service)
    transport = ASGITransport(app=app, raise_app_exceptions=False)

    async def request_client():
        async with AsyncClient(transport=transport, base_url="http://test") as http_client:
            yield http_client

    return service, request_client


def payload(site_id: str = "site-a") -> dict[str, str]:
    return {
        "site_id": site_id,
        "severity": "warning",
        "title": "Low reserve",
        "message": "Battery reserve is below target.",
    }


@pytest.mark.asyncio
async def test_list_active_alerts_returns_typed_items(client) -> None:
    service, request_client = client
    service.create(AlertCreateRequest(**payload()))

    async for http_client in request_client():
        response = await http_client.get("/api/alerts/active?site_id=site-a")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["site_id"] == "site-a"
    assert body["items"][0]["state"] == "created"
    assert body["items"][0]["raised_at"].endswith("Z")
    assert body["items"][0]["received_at"].endswith("Z")


@pytest.mark.asyncio
async def test_get_alert_and_phase1_create_behavior_remain_compatible(client) -> None:
    _, request_client = client

    async for http_client in request_client():
        created = await http_client.post("/api/alerts", json=payload("compat-site"))
        fetched = await http_client.get(f"/api/alerts/{created.json()['id']}")

    assert created.status_code == 201
    assert fetched.status_code == 200
    assert fetched.json()["site_id"] == "compat-site"
    assert fetched.json()["status"] == "active"


@pytest.mark.asyncio
async def test_acknowledge_and_resolve_alert(client) -> None:
    _, request_client = client

    async for http_client in request_client():
        created = await http_client.post("/api/alerts", json=payload())
        alert_id = created.json()["id"]
        acknowledged = await http_client.post(f"/api/alerts/{alert_id}/acknowledge")
        resolved = await http_client.post(f"/api/alerts/{alert_id}/resolve")

    assert acknowledged.status_code == 200
    assert acknowledged.json() == {"id": alert_id, "state": "acknowledged"}
    assert resolved.status_code == 200
    assert resolved.json() == {"id": alert_id, "state": "resolved"}


@pytest.mark.asyncio
async def test_missing_alert_returns_404(client) -> None:
    _, request_client = client

    async for http_client in request_client():
        response = await http_client.get("/api/alerts/missing")

    assert response.status_code == 404
    assert response.json()["error"] == "alert_not_found"


@pytest.mark.asyncio
async def test_invalid_transition_returns_conflict(client) -> None:
    _, request_client = client

    async for http_client in request_client():
        created = await http_client.post("/api/alerts", json=payload())
        alert_id = created.json()["id"]
        await http_client.post(f"/api/alerts/{alert_id}/resolve")
        response = await http_client.post(f"/api/alerts/{alert_id}/acknowledge")

    assert response.status_code == 409
    assert response.json()["error"] == "invalid_alert_transition"


@pytest.mark.asyncio
async def test_invalid_request_data_uses_validation_error(client) -> None:
    _, request_client = client

    async for http_client in request_client():
        response = await http_client.post(
            "/api/alerts",
            json={
                "site_id": "",
                "severity": "not-a-severity",
                "title": "",
                "message": "",
            },
        )

    assert response.status_code == 422
    assert response.json()["error"] == "validation_error"
    assert response.json()["field_errors"]
