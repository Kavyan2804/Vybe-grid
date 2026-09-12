"""Read-only savings comparison API."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict

from src.openapi import OPENAPI_ERROR_RESPONSES
from src.schemas.comparison import DispatchPlanComparison
from src.schemas.savings import SavingsDeltaMetrics, SavingsMetrics
from src.services.savings_facade import (
    SavingsFacade,
    SavingsFacadeError,
    SavingsFacadeResult,
)

router = APIRouter(tags=["savings"])


class SavingsResponse(BaseModel):
    """Typed read-only comparison response for one site and time range."""

    model_config = ConfigDict(extra="forbid")

    comparison: DispatchPlanComparison
    optimized: SavingsMetrics
    baseline: SavingsMetrics
    saved: SavingsDeltaMetrics


_configured_facade: SavingsFacade | None = None


def get_savings_facade() -> SavingsFacade:
    """Return the application-configured facade.

    Fuel conversion values are site/application configuration and are injected by
    the composition root or tests; this endpoint does not invent them.
    """

    if _configured_facade is None:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "savings_service_unavailable",
                "message": "Savings service dependencies are not configured.",
                "detail": {},
            },
        )
    return _configured_facade


@router.get(
    "/savings",
    response_model=SavingsResponse,
    summary="Compare optimized and baseline savings",
    description=(
        "Return a read-only planned-versus-actual savings comparison for a timezone-aware "
        "half-open interval `[start_at, end_at)`. Optimized and baseline telemetry must both "
        "exist for the requested site and timestamps."
    ),
    response_description="The comparison and optimized, baseline, and signed saved metrics.",
    responses=OPENAPI_ERROR_RESPONSES,
)
async def get_savings(
    site_id: str = Query(..., min_length=1, description="Site identifier."),
    start_at: datetime = Query(..., description="Inclusive ISO-8601 timestamp with offset."),
    end_at: datetime = Query(..., description="Exclusive ISO-8601 timestamp with offset."),
    facade: SavingsFacade = Depends(get_savings_facade),
) -> SavingsResponse:
    """Calculate savings without persisting or mutating any ledger data."""

    field_errors: list[dict[str, object]] = []
    for field_name, value in (("start_at", start_at), ("end_at", end_at)):
        if value.tzinfo is None or value.utcoffset() is None:
            field_errors.append(
                {
                    "loc": ["query", field_name],
                    "msg": "Timestamp must include an explicit timezone offset.",
                    "type": "timezone_aware",
                }
            )
    if field_errors:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "validation_error",
                "message": "Request validation failed.",
                "field_errors": field_errors,
                "detail": {},
            },
        )

    try:
        result = facade.calculate(site_id=site_id, start_at=start_at, end_at=end_at)
    except SavingsFacadeError as exc:
        raise _facade_http_exception(exc) from exc

    return _to_response(result)


def _to_response(result: SavingsFacadeResult) -> SavingsResponse:
    return SavingsResponse(
        comparison=result.comparison,
        optimized=result.optimized,
        baseline=result.baseline,
        saved=result.saved,
    )


def _facade_http_exception(exc: SavingsFacadeError) -> HTTPException:
    message = str(exc)
    if "start_at must be earlier" in message:
        return HTTPException(
            status_code=400,
            detail={"error": "invalid_time_range", "message": message, "detail": {}},
        )
    if "No dispatch plan" in message or "dispatch plan has no hours" in message:
        return HTTPException(
            status_code=404,
            detail={"error": "dispatch_plan_not_found", "message": message, "detail": {}},
        )
    if "telemetry are both required" in message:
        return HTTPException(
            status_code=404,
            detail={"error": "telemetry_not_found", "message": message, "detail": {}},
        )
    return HTTPException(
        status_code=409,
        detail={"error": "savings_data_mismatch", "message": message, "detail": {}},
    )
