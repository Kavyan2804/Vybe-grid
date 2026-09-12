"""Manual rolling-horizon tick trigger — for demo/dev use.

The scheduler ticks once per `TICK_INTERVAL_MINUTES` (default 60), which is realistic for
production but far too slow to *watch* change. This calls the exact same code path
(`optimizer_bridge.scheduled_tick`) on demand, so a manually-triggered tick is
indistinguishable from a scheduled one — same DB writes, same realtime events published.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from src.config.settings import get_settings
from src.openapi import OPENAPI_ERROR_RESPONSES
from src.services.optimizer_bridge import scheduled_tick

router = APIRouter(tags=["scheduler"])


@router.post(
    "/tick",
    summary="Run one rolling-horizon tick now",
    description="Trigger the same tick the scheduler runs hourly, immediately. Dev/demo only.",
    responses=OPENAPI_ERROR_RESPONSES,
)
async def trigger_tick(
    site_id: str = Query(default="", description="Defaults to DEFAULT_SITE_ID from settings.")
) -> dict:
    settings = get_settings()
    active_site_id = site_id.strip() if site_id.strip() else settings.default_site_id

    summary = await scheduled_tick(active_site_id)
    if summary is None:
        raise HTTPException(
            status_code=500,
            detail={
                "error": "tick_failed",
                "message": f"The rolling-horizon tick for '{active_site_id}' failed — check the backend log.",
                "detail": {},
            },
        )
    return summary
