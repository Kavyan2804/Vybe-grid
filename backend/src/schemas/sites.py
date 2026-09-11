"""Site schemas per API_CONTRACT.md §7."""

from __future__ import annotations

from pydantic import BaseModel, Field


class SiteImportResponse(BaseModel):
    """Response returned after importing a microgrid site configuration YAML."""

    site_id: str = Field(..., description="Imported site identifier")
    config_version: int = Field(..., ge=1, description="Version number of this configuration")

