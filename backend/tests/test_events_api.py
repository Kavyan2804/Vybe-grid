"""Focused tests for the Phase 3 Server-Sent Events endpoint."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime

import pytest
from httpx import ASGITransport, AsyncClient

from src.api import events as events_api
from src.main import app
from src.realtime.broadcaster import (
    InMemoryBroadcaster,
    RealtimeEvent,
    RealtimeEventType,
)


def event(
    site_id: str = "site-a",
    event_type: RealtimeEventType = RealtimeEventType.PLAN_UPDATED,
    event_id: str = "event-1",
    payload: dict[str, object] | None = None,
) -> RealtimeEvent:
    return RealtimeEvent(
        type=event_type,
        site_id=site_id,
        event_id=event_id,
        timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        payload=payload or {"value": 1},
    )


@pytest.fixture
def broadcaster(monkeypatch: pytest.MonkeyPatch) -> InMemoryBroadcaster:
    instance = InMemoryBroadcaster()
    monkeypatch.setattr(events_api, "broadcaster", instance)
    return instance


def test_route_is_registered() -> None:
    assert "/api/events/stream" in app.openapi()["paths"]


@pytest.mark.asyncio
async def test_stream_delivers_only_requested_site_events(
    broadcaster: InMemoryBroadcaster,
) -> None:
    stream = events_api._event_stream("site-a")
    first = asyncio.create_task(stream.__anext__())
    await asyncio.sleep(0)

    broadcaster.publish(event("site-b"))
    broadcaster.publish(event("site-a"))

    assert await first == 'event: plan.updated\ndata: {"value": 1}\n\n'
    await stream.aclose()
    assert broadcaster.subscriber_count == 0


@pytest.mark.asyncio
async def test_stream_formats_multiple_supported_events(
    broadcaster: InMemoryBroadcaster,
) -> None:
    stream = events_api._event_stream("site-a")
    first = asyncio.create_task(stream.__anext__())
    await asyncio.sleep(0)

    broadcaster.publish(event("site-a", RealtimeEventType.PLAN_UPDATED, "plan-1"))
    broadcaster.publish(
        event("site-a", RealtimeEventType.TELEMETRY_UPDATED, "telemetry-1", {"kw": 2})
    )
    broadcaster.publish(
        event("site-a", RealtimeEventType.ALERT_CREATED, "alert-1", {"severity": "warning"})
    )

    assert await first == 'event: plan.updated\ndata: {"value": 1}\n\n'
    assert await stream.__anext__() == 'event: telemetry.updated\ndata: {"kw": 2}\n\n'
    assert await stream.__anext__() == 'event: alert.created\ndata: {"severity": "warning"}\n\n'
    await stream.aclose()


@pytest.mark.asyncio
async def test_stream_cleanup_on_cancellation() -> None:
    broadcaster = InMemoryBroadcaster()
    stream = events_api._event_stream("site-a")
    waiting = asyncio.create_task(stream.__anext__())
    await asyncio.sleep(0)

    waiting.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiting
    await stream.aclose()

    assert broadcaster.subscriber_count == 0


@pytest.mark.asyncio
async def test_http_route_registers_and_validates_site_id() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/events/stream?site_id=")

    assert response.status_code == 422
    assert json.loads(response.text)["error"] == "validation_error"
