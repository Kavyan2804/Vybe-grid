"""In-memory, site-scoped realtime event broadcasting."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from enum import Enum
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class RealtimeEventType(str, Enum):
    """Realtime event types currently supported by the backend."""

    PLAN_UPDATED = "plan.updated"
    TELEMETRY_UPDATED = "telemetry.updated"
    ALERT_CREATED = "alert.created"


class RealtimeEvent(BaseModel):
    """A site-scoped event with a JSON-compatible payload."""

    model_config = ConfigDict(extra="forbid")

    type: RealtimeEventType
    site_id: str = Field(..., min_length=1, max_length=64)
    event_id: str | None = Field(None, min_length=1, max_length=160)
    subject: str | None = Field(None, min_length=1, max_length=160)
    timestamp: datetime
    payload: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def require_event_identity_and_timezone(self) -> Self:
        if self.event_id is None and self.subject is None:
            raise ValueError("event_id or subject is required")
        if self.timestamp.tzinfo is None or self.timestamp.utcoffset() is None:
            raise ValueError("timestamp must include an explicit timezone offset")
        try:
            json.dumps(self.payload)
        except (TypeError, ValueError) as exc:
            raise ValueError("payload must be JSON-compatible") from exc
        return self


_CLOSE = object()


class EventSubscription:
    """Async consumer for one site's bounded event queue."""

    def __init__(self, site_id: str, max_queue_size: int) -> None:
        self.site_id = site_id
        self._queue: asyncio.Queue[RealtimeEvent | object] = asyncio.Queue(maxsize=max_queue_size)
        self._closed = False

    async def get(self) -> RealtimeEvent:
        """Wait for the next event, raising StopAsyncIteration after closure."""

        item = await self._queue.get()
        if item is _CLOSE:
            raise StopAsyncIteration
        return item

    def __aiter__(self) -> EventSubscription:
        return self

    async def __anext__(self) -> RealtimeEvent:
        return await self.get()

    def close(self) -> None:
        """Close this subscription and wake any waiting consumer."""

        if self._closed:
            return
        self._closed = True
        self._discard_pending_events()
        self._queue.put_nowait(_CLOSE)

    def _discard_pending_events(self) -> None:
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except asyncio.QueueEmpty:
                break

    def _offer(self, event: RealtimeEvent) -> None:
        if self._closed:
            return
        if self._queue.full():
            try:
                self._queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
        try:
            self._queue.put_nowait(event)
        except asyncio.QueueFull:
            # A close or concurrent cleanup won the race; the event is dropped.
            return


class InMemoryBroadcaster:
    """Bounded, site-isolated in-memory event broadcaster."""

    def __init__(self, *, max_queue_size: int = 100) -> None:
        if max_queue_size < 1:
            raise ValueError("max_queue_size must be at least 1")
        self._max_queue_size = max_queue_size
        self._subscriptions: dict[str, set[EventSubscription]] = {}
        self._closed = False

    def subscribe(self, *, site_id: str) -> EventSubscription:
        """Subscribe to events for exactly one site."""

        if self._closed:
            raise RuntimeError("broadcaster is shut down")
        subscription = EventSubscription(site_id, self._max_queue_size)
        self._subscriptions.setdefault(site_id, set()).add(subscription)
        return subscription

    def unsubscribe(self, subscription: EventSubscription) -> None:
        """Remove and close a subscription; safe to call repeatedly."""

        subscriptions = self._subscriptions.get(subscription.site_id)
        if subscriptions is not None:
            subscriptions.discard(subscription)
            if not subscriptions:
                self._subscriptions.pop(subscription.site_id, None)
        subscription.close()

    def publish(self, event: RealtimeEvent) -> int:
        """Publish to subscribers of the event's site and return delivery count."""

        if self._closed:
            return 0
        subscriptions = tuple(self._subscriptions.get(event.site_id, ()))
        for subscription in subscriptions:
            subscription._offer(event)
        return len(subscriptions)

    def shutdown(self) -> None:
        """Close all subscriptions and reject future subscriptions."""

        if self._closed:
            return
        self._closed = True
        subscriptions = tuple(
            subscription
            for site_subscriptions in self._subscriptions.values()
            for subscription in site_subscriptions
        )
        self._subscriptions.clear()
        for subscription in subscriptions:
            subscription.close()

    @property
    def subscriber_count(self) -> int:
        """Return the number of currently active subscriptions."""

        return sum(len(subscriptions) for subscriptions in self._subscriptions.values())


broadcaster = InMemoryBroadcaster()
