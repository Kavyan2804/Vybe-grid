"""Tests for plans API router (/api/plans/*)."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app


@pytest.fixture()
def client():
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


@pytest.mark.asyncio
async def test_get_latest_plan_default_site(client: AsyncClient) -> None:
    """GET /api/plans/latest returns 200 and schema-valid plan for default site."""
    resp = await client.get("/api/plans/latest")
    assert resp.status_code == 200
    data = resp.json()

    # Validate structure strictly matching API_CONTRACT.md §2
    assert "plan_id" in data
    assert data["site_id"] == "example-site"
    assert "tick_at" in data
    assert data["starting_soc_kwh"] == 0.0
    assert data["series"] == []  # No fabricated data in Phase 1
    assert data["objective_cost"] == 0.0
    assert data["solver_status"] == "pending_integration"
    assert data["solve_ms"] == 0


@pytest.mark.asyncio
async def test_get_latest_plan_specific_site(client: AsyncClient) -> None:
    """GET /api/plans/latest?site_id=site-001 returns 200 for specified site."""
    resp = await client.get("/api/plans/latest?site_id=site-001")
    assert resp.status_code == 200
    data = resp.json()
    assert data["site_id"] == "site-001"
    assert data["plan_id"] == "plan_site-001_phase1"
    assert "objective_cost" in data
    assert data["solver_status"] == "pending_integration"
