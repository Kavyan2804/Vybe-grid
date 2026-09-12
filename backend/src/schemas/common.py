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
    field_errors: list[dict[str, Any]] = Field(
        default_factory=list, description="Optional validation errors associated with fields"
    )
    path: str = Field(..., description="Request path")
    timestamp: str = Field(..., description="UTC timestamp when the error was returned")
    request_id: str | None = Field(None, description="Request correlation ID, when supplied")
    detail: dict[str, Any] = Field(default_factory=dict, description="Additional error context")

    model_config = {
        "json_schema_extra": {
            "example": {
                "error": "validation_error",
                "message": "Request validation failed.",
                "field_errors": [
                    {
                        "type": "greater_than",
                        "loc": ["body", "horizon_hours"],
                        "msg": "Input should be less than or equal to 168",
                    }
                ],
                "path": "/api/plans/mock",
                "timestamp": "2026-01-15T10:30:00+00:00",
                "request_id": "req-123",
                "detail": {},
            }
        }
    }
