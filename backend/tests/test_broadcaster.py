"""Tests for the Phase 3 in-memory realtime broadcaster."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from src.realtime.broadcaster import (
    InMemoryBroadcaster,
    RealtimeEvent,
    RealtimeEventType,
)


def event(site_id: str = "site-a", event_id: str = "evt-1") -> RealtimeEvent:
    return RealtimeEvent(
        type=RealtimeEventType.PLAN_UPDATED,
        site_id=site_id,
        event_id=event_id,
        timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        payload={"plan_id": 1, "values": [1.0, True, None]},
    )


NAIVE_TIMESTAMP = datetime(2026, 1, 1, tzinfo=UTC).replace(tzinfo=None)


@pytest.mark.asyncio
async def test_event_publishing_and_async_consumption() -> None:
    broadcaster = InMemoryBroadcaster()
    subscription = broadcaster.subscribe(site_id="site-a")

    assert broadcaster.publish(event()) == 1
    received = await subscription.get()

    assert received == event()
    assert received.model_dump(mode="json")["payload"]["plan_id"] == 1


@pytest.mark.asyncio
async def test_events_are_filtered_by_site() -> None:
    broadcaster = InMemoryBroadcaster()
    site_a = broadcaster.subscribe(site_id="site-a")
    site_b = broadcaster.subscribe(site_id="site-b")

    broadcaster.publish(event("site-a"))

    assert (await site_a.get()).site_id == "site-a"
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(site_b.get(), timeout=0.01)


@pytest.mark.asyncio
async def test_multiple_subscribers_receive_the_same_event() -> None:
    broadcaster = InMemoryBroadcaster()
    first = broadcaster.subscribe(site_id="site-a")
    second = broadcaster.subscribe(site_id="site-a")

    assert broadcaster.publish(event()) == 2
    assert await first.get() == event()
    assert await second.get() == event()


@pytest.mark.asyncio
async def test_unsubscribe_and_cleanup_stop_delivery() -> None:
    broadcaster = InMemoryBroadcaster()
    subscription = broadcaster.subscribe(site_id="site-a")

    broadcaster.unsubscribe(subscription)

    assert broadcaster.subscriber_count == 0
    with pytest.raises(StopAsyncIteration):
        await subscription.get()
    assert broadcaster.publish(event()) == 0


@pytest.mark.asyncio
async def test_bounded_queue_drops_oldest_event_for_slow_subscriber() -> None:
    broadcaster = InMemoryBroadcaster(max_queue_size=2)
    subscription = broadcaster.subscribe(site_id="site-a")

    broadcaster.publish(event(event_id="first"))
    broadcaster.publish(event(event_id="second"))
    broadcaster.publish(event(event_id="third"))

    assert (await subscription.get()).event_id == "second"
    assert (await subscription.get()).event_id == "third"


@pytest.mark.asyncio
async def test_shutdown_wakes_consumers_and_rejects_new_subscribers() -> None:
    broadcaster = InMemoryBroadcaster()
    subscription = broadcaster.subscribe(site_id="site-a")
    waiting = asyncio.create_task(subscription.get())
    await asyncio.sleep(0)

    broadcaster.shutdown()

    with pytest.raises(StopAsyncIteration):
        await waiting
    with pytest.raises(RuntimeError, match="shut down"):
        broadcaster.subscribe(site_id="site-a")
    broadcaster.shutdown()


def test_event_requires_timezone_and_json_compatible_payload() -> None:
    with pytest.raises(ValidationError, match="timezone offset"):
        RealtimeEvent(
            type=RealtimeEventType.ALERT_CREATED,
            site_id="site-a",
            subject="alert-1",
            timestamp=NAIVE_TIMESTAMP,
        )

    with pytest.raises(ValidationError):
        RealtimeEvent(
            type=RealtimeEventType.TELEMETRY_UPDATED,
            site_id="site-a",
            event_id="evt-1",
            timestamp=datetime(2026, 1, 1, tzinfo=UTC),
            payload={"invalid": object()},
        )


def test_supported_event_types_are_exact() -> None:
    assert {event_type.value for event_type in RealtimeEventType} == {
        "plan.updated",
        "telemetry.updated",
        "alert.created",
    }
