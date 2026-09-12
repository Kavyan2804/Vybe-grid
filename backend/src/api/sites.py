"""Sites API router per API_CONTRACT.md §7."""

from __future__ import annotations

import yaml
from fastapi import APIRouter, Body, File, HTTPException, UploadFile, status

from src.openapi import OPENAPI_ERROR_RESPONSES
from src.schemas.sites import Site, SiteImportResponse
from src.services.site_store import (
    SiteAlreadyExistsError,
    SiteNotFoundError,
    site_service,
)

router = APIRouter(tags=["sites"])


@router.post(
    "/sites",
    response_model=Site,
    status_code=status.HTTP_201_CREATED,
    summary="Create a site configuration",
    description="Validate, normalize, and store a site in the local development-only in-memory service.",
    response_description="The normalized site configuration.",
    responses={
        **OPENAPI_ERROR_RESPONSES,
        201: {"description": "Site created.", "content": {"application/json": {"example": {"site_id": "demo-site"}}}},
    },
)
async def create_site(
    site: Site = Body(
        ...,
        openapi_examples={
            "minimal": {
                "summary": "A valid local site",
                "value": {
                    "site_id": "village-alpha",
                    "metadata": {"name": "Village Alpha", "timezone": "UTC"},
                    "location": {"latitude": 23.2, "longitude": 69.6},
                    "energy_assets": {
                        "assets": [
                            {
                                "asset_id": "solar-01",
                                "name": "Solar array",
                                "asset_type": "solar",
                                "capacity_kw": 120,
                            }
                        ]
                    },
                    "load_profile": {"peak_demand_kw": 180, "average_demand_kw": 75},
                },
            }
        },
    ),
) -> Site:
    """Create and normalize a site in the local in-memory store."""
    try:
        return site_service.create(site)
    except SiteAlreadyExistsError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": "site_exists", "message": str(exc), "detail": {}},
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "site_invalid", "message": str(exc), "detail": {}},
        ) from exc


@router.get(
    "/sites",
    response_model=list[Site],
    summary="List site configurations",
    description="List normalized site configurations currently held by the local in-memory service.",
    response_description="All stored site configurations.",
    responses=OPENAPI_ERROR_RESPONSES,
)
async def list_sites() -> list[Site]:
    """List all locally stored site configurations."""
    return site_service.list()


@router.get(
    "/sites/{site_id}",
    response_model=Site,
    summary="Get a site configuration",
    description="Retrieve one normalized site configuration by its identifier.",
    response_description="The requested site configuration.",
    responses=OPENAPI_ERROR_RESPONSES,
)
async def get_site(site_id: str) -> Site:
    """Get one locally stored site configuration."""
    try:
        return site_service.get(site_id)
    except SiteNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "site_not_found", "message": str(exc), "detail": {}},
        ) from exc


@router.put(
    "/sites/{site_id}",
    response_model=Site,
    summary="Replace a site configuration",
    description="Validate and replace a site in the local in-memory service. The path and payload IDs must match.",
    response_description="The updated normalized site configuration.",
    responses=OPENAPI_ERROR_RESPONSES,
)
async def update_site(
    site_id: str,
    site: Site = Body(..., description="Complete replacement site configuration"),
) -> Site:
    """Replace and normalize one locally stored site configuration."""
    try:
        return site_service.update(site_id, site)
    except SiteNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "site_not_found", "message": str(exc), "detail": {}},
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "site_update_invalid", "message": str(exc), "detail": {}},
        ) from exc


@router.delete(
    "/sites/{site_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a site configuration",
    description="Delete a site from the local development-only in-memory service.",
    response_description="The site was deleted.",
    responses=OPENAPI_ERROR_RESPONSES,
)
async def delete_site(site_id: str) -> None:
    """Delete one locally stored site configuration."""
    try:
        site_service.delete(site_id)
    except SiteNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "site_not_found", "message": str(exc), "detail": {}},
        ) from exc


@router.post(
    "/sites/import",
    response_model=SiteImportResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Import a YAML site configuration",
    description="Parse a YAML upload and return a development-only import acknowledgement.",
    response_description="Imported site identifier and configuration version.",
    responses=OPENAPI_ERROR_RESPONSES,
)
async def import_site_config(
    file: UploadFile = File(..., description="Multipart YAML file containing site configuration")
) -> SiteImportResponse:
    """Import and version a microgrid site configuration YAML file.

    Per API_CONTRACT.md §7:
    Returns 201 with site_id and bumped config_version.
    Config changes are append-only and versioned, never overwritten in place.
    """
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "missing_filename",
                "message": "Uploaded file must have a valid filename.",
                "detail": {},
            },
        )

    try:
        raw_bytes = await file.read()
        content = raw_bytes.decode("utf-8")
        parsed_yaml = yaml.safe_load(content)

        if not isinstance(parsed_yaml, dict):
            raise TypeError("YAML root must be a dictionary/mapping.")
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "invalid_yaml",
                "message": f"Failed to parse YAML configuration: {exc}",
                "detail": {"filename": file.filename},
            },
        ) from exc

    # Extract site_id from parsed YAML (checks site.id or id)
    site_id = (
        parsed_yaml.get("site", {}).get("id")
        if isinstance(parsed_yaml.get("site"), dict)
        else parsed_yaml.get("id")
    )
    if not site_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "validation_error",
                "message": "Site configuration YAML must specify a site ID ('site.id' or 'id').",
                "detail": {},
            },
        )

    # -----------------------------------------------------------------------
    # Phase 1 Temporary Response:
    #
    # TODO (Aarin / Contracts): Validate `parsed_yaml` against
    #   packages/contracts/site-config.schema.json using jsonschema.validate().
    #
    # TODO (Dhruvi): Integrate with database:
    #   1. Query `sites` table for existing site_id to get current version.
    #   2. Bump config_version = current_version + 1 (or 1 for new site).
    #   3. Insert into `site_config_history` (site_id, version, config, changed_at).
    #   4. Upsert `sites` (id, name, timezone, config_version, config).
    # -----------------------------------------------------------------------
    return SiteImportResponse(
        site_id=str(site_id),
        config_version=1,
    )
