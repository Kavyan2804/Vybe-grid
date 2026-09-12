"""Comprehensive isolated coverage for the Phase 1 FastAPI backend."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError

from src.api import alerts as alerts_api
from src.api import plans as plans_api
from src.api import sites as sites_api
from src.main import app
from src.schemas.alerts import AlertSeverity, AlertStatus
from src.schemas.forecasts import ForecastPoint, LoadForecast
from src.schemas.sites import Site
from src.services.alert_service import InMemoryAlertService
from src.services.forecast_validation import (
    ForecastValidationError,
    validate_forecast_points,
)
from src.services.mock_plan_service import MockPlanService
from src.services.site_store import InMemorySiteService


def site_payload(site_id: str = "site-test") -> dict:
    return {
        "site_id": site_id,
        "metadata": {"name": "Test Site", "timezone": "UTC"},
        "location": {"latitude": 23.2, "longitude": 69.6},
        "energy_assets": {
            "assets": [
                {
                    "asset_id": "solar-01",
                    "name": "Solar Array",
                    "asset_type": "solar",
                    "capacity_kw": 100,
                },
                {
                    "asset_id": "battery-01",
                    "name": "Battery",
                    "asset_type": "battery",
                    "capacity_kwh": 200,
                    "max_charge_kw": 50,
                    "max_discharge_kw": 50,
                },
            ]
        },
        "load_profile": {"peak_demand_kw": 120, "average_demand_kw": 60},
    }


@pytest.fixture()
def client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest.fixture(autouse=True)
def isolated_services(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace route-held development services for every test in this module."""

    monkeypatch.setattr(sites_api, "site_service", InMemorySiteService(seed_demo=False))
    monkeypatch.setattr(alerts_api, "alert_service", InMemoryAlertService(seed_demo=False))
    monkeypatch.setattr(plans_api, "mock_plan_service", MockPlanService())


@pytest.mark.asyncio
async def test_site_creation_duplicate_retrieval_update_and_deletion(
    client: AsyncClient,
) -> None:
    async with client:
        created = await client.post("/api/sites", json=site_payload())
        assert created.status_code == 201
        assert created.json()["site_id"] == "site-test"

        duplicate = await client.post("/api/sites", json=site_payload())
        assert duplicate.status_code == 409
        assert duplicate.json()["error"] == "site_exists"

        retrieved = await client.get("/api/sites/site-test")
        assert retrieved.status_code == 200
        assert retrieved.json()["metadata"]["name"] == "Test Site"

        updated_payload = site_payload()
        updated_payload["metadata"]["name"] = "Updated Test Site"
        updated = await client.put("/api/sites/site-test", json=updated_payload)
        assert updated.status_code == 200
        assert updated.json()["metadata"]["name"] == "Updated Test Site"

        deleted = await client.delete("/api/sites/site-test")
        assert deleted.status_code == 204
        assert (await client.get("/api/sites/site-test")).status_code == 404


def test_site_configuration_and_asset_validation() -> None:
    valid = Site.model_validate(site_payload())
    assert valid.energy_assets.assets[0].capacity_kw == 100

    invalid_site = site_payload()
    invalid_site["location"]["latitude"] = 91
    with pytest.raises(ValidationError):
        Site.model_validate(invalid_site)

    invalid_asset = site_payload()
    invalid_asset["energy_assets"]["assets"][0]["capacity_kw"] = 0
    with pytest.raises(ValidationError):
        Site.model_validate(invalid_asset)

    invalid_battery = site_payload()
    invalid_battery["energy_assets"]["assets"][1].update(
        {"min_soc_percentage": 90, "max_soc_percentage": 10}
    )
    with pytest.raises(ValidationError):
        Site.model_validate(invalid_battery)


def test_forecast_validation() -> None:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    points = [
        ForecastPoint(timestamp=start + timedelta(hours=index), value=10, unit="kW")
        for index in range(3)
    ]
    forecast = LoadForecast(site_id="site-test", points=points)
    assert validate_forecast_points(forecast.points) == timedelta(hours=1)

    duplicate = points.copy()
    duplicate[2] = duplicate[1].model_copy()
    with pytest.raises(ForecastValidationError, match="duplicate timestamps"):
        validate_forecast_points(duplicate)

    with pytest.raises(ValidationError):
        ForecastPoint(timestamp=start, value=-1, unit="kW")


@pytest.mark.asyncio
async def test_mock_plan_generation_and_latest_plan_retrieval(client: AsyncClient) -> None:
    async with client:
        first = await client.post(
            "/api/plans/mock", json={"site_id": "site-test", "horizon_hours": 3}
        )
        second = await client.post(
            "/api/plans/mock", json={"site_id": "site-test", "horizon_hours": 4}
        )
        assert first.status_code == 201
        assert second.status_code == 201
        assert first.json()["solver_status"] == "mock"
        assert len(first.json()["dispatch"]) == 3
        assert first.json()["plan_id"].endswith("001")

        latest = await client.get("/api/plans/mock/latest?site_id=site-test")
        assert latest.status_code == 200
        assert latest.json()["plan_id"] == second.json()["plan_id"]

        listed = await client.get("/api/plans/mock?site_id=site-test")
        assert listed.status_code == 200
        assert len(listed.json()) == 2


@pytest.mark.asyncio
async def test_alert_creation_filtering_pagination_and_transitions(
    client: AsyncClient,
) -> None:
    async with client:
        payloads = [
            {
                "site_id": "site-test",
                "severity": "critical",
                "title": "Critical alert",
                "message": "Critical condition",
            },
            {
                "site_id": "site-test",
                "severity": "warning",
                "title": "Warning alert",
                "message": "Warning condition",
            },
            {
                "site_id": "other-site",
                "severity": "critical",
                "title": "Other alert",
                "message": "Other condition",
            },
        ]
        created = [await client.post("/api/alerts", json=payload) for payload in payloads]
        assert all(response.status_code == 201 for response in created)
        alert_id = created[0].json()["id"]

        filtered = await client.get(
            "/api/alerts?site_id=site-test&severity=critical&status=active"
        )
        assert filtered.status_code == 200
        assert filtered.json()["total"] == 1
        assert len(filtered.json()["items"]) == 1

        paginated = await client.get("/api/alerts?limit=1&offset=1")
        assert paginated.status_code == 200
        assert paginated.json()["total"] == 3
        assert len(paginated.json()["items"]) == 1

        acknowledged = await client.post(f"/api/alerts/{alert_id}/acknowledge")
        assert acknowledged.status_code == 200
        assert acknowledged.json()["state"] == AlertStatus.ACKNOWLEDGED.value

        resolved = await client.post(f"/api/alerts/{alert_id}/resolve")
        assert resolved.status_code == 200
        assert resolved.json()["state"] == AlertStatus.RESOLVED.value

        resolved_filter = await client.get("/api/alerts?status=resolved")
        assert resolved_filter.json()["total"] == 1


@pytest.mark.asyncio
async def test_invalid_alert_transitions_and_error_responses(client: AsyncClient) -> None:
    async with client:
        missing = await client.post("/api/alerts/missing/resolve")
        assert missing.status_code == 404
        assert missing.json()["error"] == "alert_not_found"

        created = await client.post(
            "/api/alerts",
            json={
                "site_id": "site-test",
                "severity": AlertSeverity.INFO.value,
                "title": "Info",
                "message": "Information",
            },
        )
        alert_id = created.json()["id"]
        assert (await client.post(f"/api/alerts/{alert_id}/acknowledge")).status_code == 200
        assert (await client.post(f"/api/alerts/{alert_id}/acknowledge")).status_code == 409
        assert (await client.post(f"/api/alerts/{alert_id}/resolve")).status_code == 200
        assert (await client.post(f"/api/alerts/{alert_id}/acknowledge")).status_code == 409
        assert (await client.post(f"/api/alerts/{alert_id}/resolve")).status_code == 409

        invalid_request = await client.post(
            "/api/alerts",
            json={"site_id": "site-test", "severity": "invalid"},
            headers={"x-request-id": "phase1-test"},
        )
        assert invalid_request.status_code == 422
        error = invalid_request.json()
        assert error["error"] == "validation_error"
        assert error["path"] == "/api/alerts"
        assert error["request_id"] == "phase1-test"
        assert error["field_errors"]
        assert "timestamp" in error


@pytest.mark.asyncio
async def test_health_endpoint(client: AsyncClient) -> None:
    async with client:
        response = await client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
