"""Tests for the consistent API error envelope."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app


def assert_error(response, status_code: int, code: str) -> dict:
    assert response.status_code == status_code
    body = response.json()
    assert body["error"] == code
    assert body["message"]
    assert body["path"].startswith("/api/")
    assert body["timestamp"].endswith("+00:00")
    assert body["request_id"] == "req-test-001"
    assert isinstance(body["field_errors"], list)
    assert "Traceback" not in response.text
    return body


@pytest.mark.asyncio
async def test_validation_error_contains_field_errors_and_metadata() -> None:
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/plans/mock",
            json={"site_id": "demo-site", "horizon_hours": 999},
            headers={"x-request-id": "req-test-001"},
        )
    body = assert_error(response, 422, "validation_error")
    assert body["field_errors"]


@pytest.mark.asyncio
async def test_not_found_and_conflict_errors_use_common_envelope() -> None:
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        missing = await client.get("/api/alerts/not-found", headers={"x-request-id": "req-test-001"})
        assert_error(missing, 404, "alert_not_found")
        created = await client.post(
            "/api/alerts",
            json={"site_id": "error-site", "severity": "warning", "title": "T", "message": "M"},
        )
        alert_id = created.json()["id"]
        await client.post(f"/api/alerts/{alert_id}/resolve")
        conflict = await client.post(
            f"/api/alerts/{alert_id}/acknowledge",
            headers={"x-request-id": "req-test-001"},
        )
        assert_error(conflict, 409, "invalid_alert_transition")


@pytest.mark.asyncio
async def test_bad_request_and_unknown_route_errors_use_common_envelope() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        bad_request = await client.put(
            "/api/sites/demo-site",
            json={
                "site_id": "different",
                "metadata": {"name": "Site", "timezone": "UTC"},
                "location": {"latitude": 1, "longitude": 1},
                "energy_assets": {
                    "assets": [
                        {
                            "asset_id": "solar",
                            "name": "Solar",
                            "asset_type": "solar",
                            "capacity_kw": 1,
                        }
                    ]
                },
                "load_profile": {"peak_demand_kw": 1, "average_demand_kw": 1},
            },
            headers={"x-request-id": "req-test-001"},
        )
        assert_error(bad_request, 400, "site_update_invalid")
        unknown_route = await client.get("/api/does-not-exist", headers={"x-request-id": "req-test-001"})
        assert_error(unknown_route, 404, "not_found")


@pytest.mark.asyncio
async def test_unexpected_errors_are_sanitized(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.api import alerts

    def fail(_request):
        raise RuntimeError("secret implementation detail")

    monkeypatch.setattr(alerts.alert_service, "create", fail)
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/alerts",
            json={"site_id": "error-site", "severity": "info", "title": "T", "message": "M"},
            headers={"x-request-id": "req-test-001"},
        )
    body = assert_error(response, 500, "internal_error")
    assert "secret implementation detail" not in body["message"]
