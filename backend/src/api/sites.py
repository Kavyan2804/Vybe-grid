"""Sites API router per API_CONTRACT.md §7."""

from __future__ import annotations

import yaml
from fastapi import APIRouter, File, HTTPException, UploadFile, status

from src.schemas.sites import SiteImportResponse

router = APIRouter(tags=["sites"])


@router.post(
    "/sites/import",
    response_model=SiteImportResponse,
    status_code=status.HTTP_201_CREATED,
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
