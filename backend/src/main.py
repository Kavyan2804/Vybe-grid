"""FastAPI application entry point and centralized error handling."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any, AsyncIterator

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from src.api.alerts import router as alerts_router
from src.api.events import router as events_router
from src.api.forecasts import router as forecasts_router
from src.api.health import router as health_router
from src.api.overview import router as overview_router
from src.api.plans import router as plans_router
from src.api.savings import router as savings_router
from src.api.sites import router as sites_router
from src.api.telemetry import router as telemetry_router
from src.api.tick import router as tick_router
from src.config.settings import get_settings
from src.errors import BackendError
from src.openapi import OPENAPI_TAGS
from src.scheduler.tick import RollingScheduler
from src.services.optimizer_bridge import scheduled_tick

_logger = logging.getLogger("gridpilot.main")
_scheduler: RollingScheduler | None = None


@asynccontextmanager
async def _lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Start the rolling-horizon scheduler on boot, stop it cleanly on shutdown.

    This is the piece that was missing through Phase 2 and Phase 3: the optimizer and the
    real database both existed, but nothing ever called one on a schedule against the other.
    See docs/architecture/optimizer_bridge notes in `src/services/optimizer_bridge.py`.
    """
    global _scheduler
    settings = get_settings()
    _scheduler = RollingScheduler(tick_callback=scheduled_tick)
    _scheduler.schedule_site(settings.default_site_id)
    _scheduler.start()
    _logger.info(
        "rolling-horizon scheduler started site_id=%s interval_minutes=%s",
        settings.default_site_id,
        _scheduler.interval_minutes,
    )
    try:
        yield
    finally:
        if _scheduler is not None:
            _scheduler.shutdown()


app = FastAPI(
    title="GridPilot Backend API",
    version="0.2.0",
    summary="Rolling-horizon microgrid dispatch — API, scheduler and realtime layer.",
    description=(
        "Serves the frozen API_CONTRACT.md surface over the real Postgres database. The "
        "rolling-horizon optimizer runs on a schedule (see `src/services/optimizer_bridge.py`) "
        "against the digital twin (Simulated tier — PRD.md §9); every value it produces is "
        "badged SIMULATED, never presented as live hardware telemetry. `/plans/mock` remains "
        "for development only and is explicitly marked with solver_status='mock'."
    ),
    openapi_tags=OPENAPI_TAGS,
    lifespan=_lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _error_response(
    request: Request,
    *,
    status_code: int,
    error: str,
    message: str,
    field_errors: list[dict[str, Any]] | None = None,
    detail: dict[str, Any] | None = None,
) -> JSONResponse:
    content = {
        "error": error,
        "message": message,
        "field_errors": field_errors or [],
        "path": request.url.path,
        "timestamp": datetime.now(UTC).isoformat(),
        "request_id": request.headers.get("x-request-id"),
        "detail": detail or {},
    }
    return JSONResponse(status_code=status_code, content=content)


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    detail = exc.detail if isinstance(exc.detail, dict) else {}
    status_code = exc.status_code
    error = detail.get("error") or {
        400: "bad_request",
        404: "not_found",
        409: "conflict",
    }.get(status_code, "http_error")
    message = detail.get("message") or str(exc.detail)
    return _error_response(
        request,
        status_code=status_code,
        error=error,
        message=message,
        field_errors=detail.get("field_errors"),
        detail=detail.get("detail"),
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    return _error_response(
        request,
        status_code=422,
        error="validation_error",
        message="Request validation failed.",
        field_errors=[dict(error) for error in exc.errors()],
    )


@app.exception_handler(BackendError)
async def backend_error_handler(request: Request, exc: BackendError) -> JSONResponse:
    return _error_response(
        request,
        status_code=exc.status_code,
        error=exc.error_code,
        message=str(exc),
        field_errors=getattr(exc, "field_errors", []),
    )


@app.exception_handler(Exception)
async def internal_error_handler(request: Request, _exc: Exception) -> JSONResponse:
    return _error_response(
        request,
        status_code=500,
        error="internal_error",
        message="An unexpected internal error occurred.",
    )


app.include_router(health_router, prefix="/api")
app.include_router(overview_router, prefix="/api")
app.include_router(plans_router, prefix="/api")
app.include_router(telemetry_router, prefix="/api")
app.include_router(forecasts_router, prefix="/api")
app.include_router(savings_router, prefix="/api")
app.include_router(alerts_router, prefix="/api")
app.include_router(events_router, prefix="/api")
app.include_router(sites_router, prefix="/api")
app.include_router(tick_router, prefix="/api")
