"""Tests for the in-memory site service and CRUD API."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app
from src.services.site_store import (
    InMemorySiteService,
    SiteAlreadyExistsError,
    SiteNotFoundError,
)
from tests.test_site_schemas import valid_site_payload


@pytest.fixture()
def service() -> InMemorySiteService:
    return InMemorySiteService(seed_demo=False)


def test_service_crud_and_duplicate_protection(service: InMemorySiteService) -> None:
    from src.schemas.sites import Site

    site = Site.model_validate(valid_site_payload())
    created = service.create(site)
    assert service.get(created.site_id).site_id == "village-alpha"
    assert len(service.list()) == 1

    created.metadata.name = "Changed locally"
    assert service.get("village-alpha").metadata.name == "Village Alpha"
    with pytest.raises(SiteAlreadyExistsError):
        service.create(site)

    updated = site.model_copy(deep=True)
    updated.metadata.name = "Updated village"
    assert service.update("village-alpha", updated).metadata.name == "Updated village"

    service.delete("village-alpha")
    assert service.list() == []
    with pytest.raises(SiteNotFoundError):
        service.get("village-alpha")


@pytest.mark.asyncio
async def test_site_crud_api_status_codes() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = valid_site_payload()
        payload["site_id"] = "api-site"
        response = await client.post("/api/sites", json=payload)
        assert response.status_code == 201

        duplicate = await client.post("/api/sites", json=payload)
        assert duplicate.status_code == 409

        listed = await client.get("/api/sites")
        assert listed.status_code == 200
        assert any(item["site_id"] == "api-site" for item in listed.json())

        fetched = await client.get("/api/sites/api-site")
        assert fetched.status_code == 200

        payload["metadata"]["name"] = "Updated API site"
        updated = await client.put("/api/sites/api-site", json=payload)
        assert updated.status_code == 200
        assert updated.json()["metadata"]["name"] == "Updated API site"

        deleted = await client.delete("/api/sites/api-site")
        assert deleted.status_code == 204
        missing = await client.get("/api/sites/api-site")
        assert missing.status_code == 404


@pytest.mark.asyncio
async def test_site_api_rejects_invalid_payload_and_missing_update() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        invalid = valid_site_payload()
        invalid["location"]["latitude"] = 100
        assert (await client.post("/api/sites", json=invalid)).status_code == 422

        valid = valid_site_payload()
        valid["site_id"] = "missing-site"
        response = await client.put("/api/sites/not-present", json=valid)
        assert response.status_code == 404
