"""Alert management API routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Path, Query, status

from src.openapi import OPENAPI_ERROR_RESPONSES
from src.schemas.alerts import (
    Alert,
    AlertActionResponse,
    AlertCreateRequest,
    AlertListResponse,
    AlertSeverity,
    AlertStatus,
)
from src.services.alert_service import (
    AlertNotFoundError,
    AlertTransitionError,
    alert_service,
)

router = APIRouter(tags=["alerts"])


@router.post(
    "/alerts",
    response_model=Alert,
    status_code=status.HTTP_201_CREATED,
    summary="Create an alert",
    description="Create an active alert in the local development-only in-memory service.",
    response_description="The created active alert.",
    responses=OPENAPI_ERROR_RESPONSES,
)
async def create_alert(request: AlertCreateRequest) -> Alert:
    return alert_service.create(request)


@router.get(
    "/alerts",
    response_model=AlertListResponse,
    summary="List and filter alerts",
    description="Filter alerts by site, severity, and status, then paginate with limit and offset.",
    response_description="Matching alerts and the total count before pagination.",
    responses=OPENAPI_ERROR_RESPONSES,
)
async def list_alerts(
    site_id: str | None = Query(None, min_length=1),
    severity: AlertSeverity | None = None,
    status_filter: AlertStatus | None = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> AlertListResponse:
    total, items = alert_service.list(
        site_id=site_id,
        severity=severity,
        status=status_filter,
        limit=limit,
        offset=offset,
    )
    return AlertListResponse(total=total, items=items)


@router.get(
    "/alerts/{alert_id}",
    response_model=Alert,
    summary="Get an alert",
    description="Retrieve an alert by ID from the local in-memory service.",
    response_description="The requested alert.",
    responses=OPENAPI_ERROR_RESPONSES,
)
async def get_alert(alert_id: str = Path(..., min_length=1)) -> Alert:
    try:
        return alert_service.get(alert_id.strip())
    except AlertNotFoundError as exc:
        raise _not_found(exc) from exc


@router.post(
    "/alerts/{alert_id}/acknowledge",
    response_model=AlertActionResponse,
    summary="Acknowledge an alert",
    description="Transition an active alert to acknowledged. Resolved alerts cannot be acknowledged.",
    response_description="The resulting alert state.",
    responses=OPENAPI_ERROR_RESPONSES,
)
async def acknowledge_alert(alert_id: str = Path(..., min_length=1)) -> AlertActionResponse:
    try:
        alert = alert_service.acknowledge(alert_id.strip())
    except AlertNotFoundError as exc:
        raise _not_found(exc) from exc
    except AlertTransitionError as exc:
        raise _conflict(exc) from exc
    return AlertActionResponse(id=alert.id, state=alert.status)


@router.post(
    "/alerts/{alert_id}/resolve",
    response_model=AlertActionResponse,
    summary="Resolve an alert",
    description="Transition an active or acknowledged alert to resolved.",
    response_description="The resulting alert state.",
    responses=OPENAPI_ERROR_RESPONSES,
)
async def resolve_alert(alert_id: str = Path(..., min_length=1)) -> AlertActionResponse:
    try:
        alert = alert_service.resolve(alert_id.strip())
    except AlertNotFoundError as exc:
        raise _not_found(exc) from exc
    except AlertTransitionError as exc:
        raise _conflict(exc) from exc
    return AlertActionResponse(id=alert.id, state=alert.status)


def _not_found(exc: Exception) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={"error": "alert_not_found", "message": str(exc), "detail": {}},
    )


def _conflict(exc: Exception) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={"error": "invalid_alert_transition", "message": str(exc), "detail": {}},
    )
