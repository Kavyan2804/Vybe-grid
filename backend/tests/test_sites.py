"""Tests for sites API router (/api/sites/*)."""

from __future__ import annotations

import io

import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app


@pytest.fixture()
def client():
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


@pytest.mark.asyncio
async def test_import_site_success(client: AsyncClient) -> None:
    """POST /api/sites/import with valid YAML returns 201 per API_CONTRACT.md §7."""
    valid_yaml = """
site:
  id: site-001
  name: Example Village Microgrid
  timezone: Asia/Kolkata
battery:
  capacity_kwh: 50.0
"""
    files = {
        "file": ("example-site.yml", io.BytesIO(valid_yaml.encode("utf-8")), "application/x-yaml")
    }
    resp = await client.post("/api/sites/import", files=files)
    assert resp.status_code == 201
    data = resp.json()
    assert data["site_id"] == "site-001"
    assert data["config_version"] == 1


@pytest.mark.asyncio
async def test_import_site_custom_id(client: AsyncClient) -> None:
    """POST /api/sites/import extracts custom site id from YAML."""
    custom_yaml = """
id: village-beta
battery:
  capacity_kwh: 100.0
"""
    files = {
        "file": ("site-beta.yml", io.BytesIO(custom_yaml.encode("utf-8")), "application/x-yaml")
    }
    resp = await client.post("/api/sites/import", files=files)
    assert resp.status_code == 201
    data = resp.json()
    assert data["site_id"] == "village-beta"
    assert data["config_version"] == 1


@pytest.mark.asyncio
async def test_import_site_missing_site_id(client: AsyncClient) -> None:
    """POST /api/sites/import without site ID returns 400 validation_error (no silent fallback)."""
    yaml_without_id = """
battery:
  capacity_kwh: 100.0
"""
    files = {
        "file": ("no-id.yml", io.BytesIO(yaml_without_id.encode("utf-8")), "application/x-yaml")
    }
    resp = await client.post("/api/sites/import", files=files)
    assert resp.status_code == 400
    data = resp.json()
    assert data["error"] == "validation_error"
    assert "site id" in data["message"].lower()


@pytest.mark.asyncio
async def test_import_site_invalid_yaml(client: AsyncClient) -> None:
    """POST /api/sites/import with malformed YAML returns 400 Bad Request."""
    broken_yaml = """
site:
  id: [unclosed list
    foo: bar
"""
    files = {
        "file": ("broken.yml", io.BytesIO(broken_yaml.encode("utf-8")), "application/x-yaml")
    }
    resp = await client.post("/api/sites/import", files=files)
    assert resp.status_code == 400
    data = resp.json()
    assert data["error"] == "invalid_yaml"
    assert "message" in data


@pytest.mark.asyncio
async def test_import_site_missing_file(client: AsyncClient) -> None:
    """POST /api/sites/import with missing multipart file returns 422."""
    resp = await client.post("/api/sites/import")
    assert resp.status_code == 422
    data = resp.json()
    assert data["error"] == "validation_error"
