"""
GridPilot — FastAPI application entry point.

Responsibilities of this file:
  1. Create the FastAPI app with metadata.
  2. Wire CORS middleware (dashboard at :3000).
  3. Register standard error handlers (API_CONTRACT.md §9).
  4. Mount modular APIRouters under /api.
  5. Expose GET /api/health probe.

What is NOT here:
  - Database session lifecycle  → Dhruvi (optimizer/infrastructure/db/)
  - APScheduler rolling tick     → Phase 2
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from src.api.alerts import router as alerts_router
from src.api.health import router as health_router
from src.api.plans import router as plans_router
from src.api.sites import router as sites_router

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="GridPilot",
    version="0.1.0",
    description="Rolling-horizon microgrid energy-mix optimizer — backend API.",
)

# ---------------------------------------------------------------------------
# CORS — allow the Next.js dashboard on :3000
# ---------------------------------------------------------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Error handlers per API_CONTRACT.md §9:
#
#   { "error": "machine_readable_code", "message": "human sentence", "detail": {} }
#
#   400 validation · 404 unknown site/plan/alert · 409 illegal lifecycle
#   422 schema rejection · 500 unexpected
# ---------------------------------------------------------------------------


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(
    _request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    """Format HTTPExceptions (both FastAPI and Starlette routing) into canonical error shape."""
    if isinstance(exc.detail, dict) and "error" in exc.detail:
        return JSONResponse(status_code=exc.status_code, content=exc.detail)

    error_code = "not_found" if exc.status_code == 404 else "http_error"
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": error_code,
            "message": str(exc.detail),
            "detail": {},
        },
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    _request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Format request validation errors (422) into canonical error shape."""
    return JSONResponse(
        status_code=422,
        content={
            "error": "validation_error",
            "message": "Request validation failed.",
            "detail": {"errors": exc.errors()},
        },
    )


@app.exception_handler(Exception)
async def internal_error_handler(_request: Request, _exc: Exception) -> JSONResponse:
    """Fallback handler for unhandled server exceptions (500)."""
    return JSONResponse(
        status_code=500,
        content={
            "error": "internal_error",
            "message": "An unexpected error occurred.",
            "detail": {},
        },
    )


# ---------------------------------------------------------------------------
# Mount Modular Routers
# ---------------------------------------------------------------------------

app.include_router(health_router, prefix="/api")
app.include_router(plans_router, prefix="/api")
app.include_router(alerts_router, prefix="/api")
app.include_router(sites_router, prefix="/api")
