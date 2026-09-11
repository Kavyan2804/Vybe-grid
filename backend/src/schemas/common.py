"""Common schemas and value objects per API_CONTRACT.md and PRD.md."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class ProvenanceBadge(str, Enum):
    """Provenance badges per PRD.md §3."""

    LIVE = "LIVE"
    FORECAST = "FORECAST"
    SIMULATED = "SIMULATED"
    BASELINE = "BASELINE"


class ErrorResponse(BaseModel):
    """Canonical error response format per API_CONTRACT.md §9.

    { "error": "machine_readable_code", "message": "human sentence", "detail": {} }
    """

    error: str = Field(..., description="Machine-readable error code")
    message: str = Field(..., description="Human-readable error description")
    detail: dict[str, Any] = Field(
        default_factory=dict, description="Structured contextual error details"
    )
