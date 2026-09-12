"""Tests for the backend foundation — health endpoint and error shape."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app


@pytest.fixture()
def client():
    """Async test client bound to the FastAPI app — no server needed."""
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


# ── Health endpoint ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_health_returns_200(client: AsyncClient) -> None:
    resp = await client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body == {"status": "ok"}


# ── Error shape (API_CONTRACT.md §9) ────────────────────────────────────


@pytest.mark.asyncio
async def test_404_matches_error_contract(client: AsyncClient) -> None:
    """A request to a non-existent path returns the standard error shape."""
    resp = await client.get("/api/nonexistent")
    assert resp.status_code == 404
    body = resp.json()
    assert "error" in body
    assert "message" in body
    assert "detail" in body
    assert body["error"] == "not_found"


# ── Settings ────────────────────────────────────────────────────────────


def test_settings_loads_defaults() -> None:
    """Settings should load with sensible defaults when no .env is present."""
    from src.config.settings import Settings

    s = Settings()
    assert s.tick_interval_minutes == 60
    assert s.horizon_hours == 24
    assert s.solve_timeout_seconds == 20
    assert s.default_site_id == "example-site"
    assert s.dispatch_adapter == "simulator"
    assert s.forecast_provider == "openmeteo"

