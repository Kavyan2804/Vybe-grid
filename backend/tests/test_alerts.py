"""Tests for alerts API router (/api/alerts/*)."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app


@pytest.fixture()
def client():
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


@pytest.mark.asyncio
async def test_acknowledge_alert_success(client: AsyncClient) -> None:
    """POST /api/alerts/{id}/acknowledge returns 200 with state=acknowledged."""
    resp = await client.post("/api/alerts/alr_001/acknowledge")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == "alr_001"
    assert data["state"] == "acknowledged"


@pytest.mark.asyncio
async def test_resolve_alert_success(client: AsyncClient) -> None:
    """POST /api/alerts/{id}/resolve returns 200 with state=resolved."""
    resp = await client.post("/api/alerts/alr_002/resolve")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == "alr_002"
    assert data["state"] == "resolved"
