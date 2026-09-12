"""Server-Sent Events API for site-scoped realtime updates."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse

from src.realtime.broadcaster import RealtimeEvent, broadcaster

router = APIRouter(tags=["realtime"])
# Was `broadcaster = InMemoryBroadcaster()` — a second, unrelated instance from the module-level
# singleton in broadcaster.py. Nothing published to the singleton would ever have reached a
# subscriber here; every SSE connection was listening to a broadcaster nothing wrote to.


@router.get(
    "/events/stream",
    summary="Stream site realtime events",
    description=(
        "Stream plan, telemetry, and alert events for one site using "
        "Server-Sent Events. Events are not generated automatically."
    ),
    response_class=StreamingResponse,
)
async def stream_events(
    site_id: str = Query(..., min_length=1, max_length=64),
) -> StreamingResponse:
    """Open a site-scoped Server-Sent Events stream."""

    return StreamingResponse(
        _event_stream(site_id.strip()),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


async def _event_stream(site_id: str) -> AsyncIterator[str]:
    subscription = broadcaster.subscribe(site_id=site_id)
    try:
        async for event in subscription:
            yield _format_event(event)
    finally:
        broadcaster.unsubscribe(subscription)


def _format_event(event: RealtimeEvent) -> str:
    return f"event: {event.type.value}\ndata: {json.dumps(event.payload)}\n\n"
