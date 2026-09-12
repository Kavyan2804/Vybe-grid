"""Backend rolling scheduler using APScheduler (Phase 2 Task 2.1).

Schedules periodic rolling-horizon optimization ticks for configured sites.
"""

from typing import Optional, Dict, Any, Callable
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from src.config.settings import get_settings


class RollingScheduler:
    """Manages periodic rolling-horizon optimization ticks via APScheduler."""

    def __init__(
        self,
        tick_callback: Optional[Callable[..., Any]] = None,
        interval_minutes: Optional[int] = None,
    ) -> None:
        self.settings = get_settings()
        self.interval_minutes = (
            interval_minutes
            if interval_minutes is not None
            else self.settings.tick_interval_minutes
        )
        self.tick_callback = tick_callback
        self.scheduler = AsyncIOScheduler()
        self._is_running = False

    def schedule_site(self, site_id: str) -> None:
        """Register a rolling-horizon job for a site."""
        job_id = f"tick_{site_id}"
        if self.scheduler.get_job(job_id):
            self.scheduler.remove_job(job_id)

        self.scheduler.add_job(
            self._execute_tick,
            trigger=IntervalTrigger(minutes=self.interval_minutes),
            id=job_id,
            args=[site_id],
            replace_existing=True,
        )

    async def _execute_tick(self, site_id: str) -> None:
        """Invoke tick callback for a site."""
        if self.tick_callback is not None:
            if callable(self.tick_callback):
                import inspect
                if inspect.iscoroutinefunction(self.tick_callback):
                    await self.tick_callback(site_id)
                else:
                    self.tick_callback(site_id)

    def start(self) -> None:
        """Start background scheduler."""
        if not self._is_running:
            self.scheduler.start()
            self._is_running = True

    def shutdown(self) -> None:
        """Stop background scheduler."""
        if self._is_running:
            self.scheduler.shutdown(wait=False)
            self._is_running = False
