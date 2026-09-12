"""Tests for deterministic mock plan generation and API routes."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app
from src.schemas.plans import MockPlanRequest, MockSolverStatus
from src.services.mock_plan_service import MockPlanNotFoundError, MockPlanService


def test_mock_plan_service_generates_deterministic_shape() -> None:
    service = MockPlanService()
    request = MockPlanRequest(site_id="demo-site", horizon_hours=4)

    first = service.create_plan(request)
    second = service.create_plan(request)

    assert first.plan_id == "mock-plan-demo-site-001"
    assert second.plan_id == "mock-plan-demo-site-002"
    assert first.solver_status == MockSolverStatus.MOCK
    assert first.planning_horizon_hours == 4
    assert len(first.dispatch) == 4
    assert first.dispatch[0].solar_kw == 0
    assert first.dispatch[1].wind_kw == 10
    assert first.total_cost == 8
    assert first.total_emissions_kg_co2 == 4


def test_mock_plan_service_retrieves_latest_and_copies_results() -> None:
    service = MockPlanService()
    service.create_plan(MockPlanRequest(site_id="site-a", horizon_hours=2))
    latest = service.create_plan(MockPlanRequest(site_id="site-a", horizon_hours=3))

    assert service.latest_for_site("site-a").plan_id == latest.plan_id
    assert len(service.list_for_site("site-a")) == 2
    fetched = service.get_plan(latest.plan_id)
    fetched.dispatch[0].load_kw = 999
    assert service.get_plan(latest.plan_id).dispatch[0].load_kw != 999

    with pytest.raises(MockPlanNotFoundError):
        service.get_plan("missing")
    with pytest.raises(MockPlanNotFoundError):
        service.latest_for_site("missing-site")


@pytest.mark.asyncio
async def test_mock_plan_api_create_get_latest_and_list() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {"site_id": "api-mock-site", "horizon_hours": 3}
        created = await client.post("/api/plans/mock", json=payload)
        assert created.status_code == 201
        plan = created.json()
        assert plan["solver_status"] == "mock"
        assert plan["planning_horizon_hours"] == 3
        assert len(plan["dispatch"]) == 3

        fetched = await client.get(f"/api/plans/mock/{plan['plan_id']}")
        assert fetched.status_code == 200
        latest = await client.get("/api/plans/mock/latest?site_id=api-mock-site")
        assert latest.status_code == 200
        listed = await client.get("/api/plans/mock?site_id=api-mock-site")
        assert listed.status_code == 200
        assert len(listed.json()) >= 1


@pytest.mark.asyncio
async def test_mock_plan_api_returns_not_found_and_rejects_invalid_request() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        missing = await client.get("/api/plans/mock/not-present")
        assert missing.status_code == 404
        no_latest = await client.get("/api/plans/mock/latest?site_id=not-present")
        assert no_latest.status_code == 404
        invalid = await client.post(
            "/api/plans/mock", json={"site_id": "bad", "horizon_hours": 169}
        )
        assert invalid.status_code == 422
