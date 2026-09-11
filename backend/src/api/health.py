"""Health check router for GridPilot backend."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
async def get_health() -> dict[str, str]:
    """Liveness probe. Returns 200 when the backend service is running."""
    return {"status": "ok"}

