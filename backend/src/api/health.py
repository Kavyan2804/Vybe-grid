"""Health check router for GridPilot backend."""

from __future__ import annotations

from fastapi import APIRouter

from src.openapi import OPENAPI_ERROR_RESPONSES

router = APIRouter(tags=["health"])


@router.get(
    "/health",
    summary="Check backend liveness",
    description="Returns `ok` when the local FastAPI process is running.",
    response_description="Liveness status.",
    responses={**OPENAPI_ERROR_RESPONSES},
)
async def get_health() -> dict[str, str]:
    """Liveness probe. Returns 200 when the backend service is running."""
    return {"status": "ok"}
