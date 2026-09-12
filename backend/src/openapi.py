"""Shared OpenAPI metadata for the Phase 1 backend."""

from src.schemas.common import ErrorResponse

OPENAPI_ERROR_RESPONSES = {
    400: {
        "model": ErrorResponse,
        "description": "The request is syntactically valid but violates a backend rule.",
    },
    404: {
        "model": ErrorResponse,
        "description": "The requested resource or route was not found.",
    },
    409: {
        "model": ErrorResponse,
        "description": "The request conflicts with the current resource state.",
    },
    422: {
        "model": ErrorResponse,
        "description": "Request body or query parameters failed Pydantic validation.",
    },
    500: {
        "model": ErrorResponse,
        "description": "An unexpected internal error occurred; implementation details are not exposed.",
    },
}

OPENAPI_TAGS = [
    {"name": "health", "description": "Liveness checks for the local Phase 1 backend."},
    {
        "name": "sites",
        "description": "Validated site configuration stored in the development-only in-memory service.",
    },
    {
        "name": "plans",
        "description": "Phase 1 plan endpoints. `/plans/mock` returns deterministic data with solver_status='mock'; it is not optimizer output.",
    },
    {
        "name": "alerts",
        "description": "Alert lifecycle management backed by deterministic in-memory storage.",
    },
]
