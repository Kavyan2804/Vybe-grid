"""Alert management API routes."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models.alerts import AlertState as DbAlertState
from src.db.repositories.alerts import AlertRepository
from src.db.session import get_db_session
from src.openapi import OPENAPI_ERROR_RESPONSES
from src.schemas.alerts import (
    Alert,
    AlertActionResponse,
    AlertCreateRequest,
    AlertListResponse,
    AlertState,
    AlertSeverity,
    AlertStatus,
    AlertType,
)
from src.services.alert_service import (
    AlertNotFoundError,
    AlertTransitionError,
    alert_service,
)
from src.schemas.common import ProvenanceBadge

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
    "/alerts/active",
    response_model=AlertListResponse,
    summary="List active alerts",
    description="List created and acknowledged alerts persisted by the live alert pipeline.",
    response_description="Active alerts from the local in-memory service.",
    responses=OPENAPI_ERROR_RESPONSES,
)
async def list_active_alerts(
    site_id: str | None = Query(None, min_length=1),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_db_session),
) -> AlertListResponse:
    """Return current alerts persisted by the live rolling-horizon process."""
    if not site_id:
        return AlertListResponse(total=0, items=[])
    rows = await AlertRepository(session).list_for_site(site_id, limit=limit + offset)
    active = [row for row in rows if row.state != DbAlertState.RESOLVED]
    items = [_database_alert_to_schema(row) for row in active[offset : offset + limit]]
    return AlertListResponse(total=len(active), items=items)


def _database_alert_to_schema(row) -> Alert:
    """Adapt the database alert contract to the legacy Alerts page schema."""
    type_map = {
        "SOC_LOW": AlertType.LOW_SOC_RESERVE,
        "DIESEL_REQUIRED_SOON": AlertType.DIESEL_REQUIRED_SOON,
        "SOLAR_FORECAST_STALE": AlertType.FORECAST_STALE,
        "SOLVER_FALLBACK_ACTIVE": AlertType.SOLVER_FALLBACK_ACTIVE,
        "SOLVER_INFEASIBLE": AlertType.SOLVER_FALLBACK_ACTIVE,
        "DIESEL_RUNTIME_EXCEEDED": AlertType.DIESEL_REQUIRED_SOON,
    }
    api_type = type_map.get(row.type.value, AlertType.SOLVER_FALLBACK_ACTIVE)
    severity = (
        AlertSeverity.CRITICAL
        if row.type.value in {"SOLVER_INFEASIBLE", "CRITICAL_LOAD_AT_RISK"}
        else AlertSeverity.WARNING
    )
    state = AlertState(row.state.value)
    provenance = [ProvenanceBadge.LIVE]
    if row.provenance and isinstance(row.provenance, dict):
        badges = row.provenance.get("badges")
        if isinstance(badges, list):
            valid_badges = {badge.value for badge in ProvenanceBadge}
            provenance = [
                ProvenanceBadge(badge)
                for badge in badges
                if isinstance(badge, str) and badge in valid_badges
            ] or provenance
    return Alert(
        id=row.id,
        site_id=row.site_id,
        type=api_type,
        subject=row.subject,
        state=state,
        severity=severity,
        status=AlertStatus.ACKNOWLEDGED if state is AlertState.ACKNOWLEDGED else AlertStatus.ACTIVE,
        title=row.title,
        message=f"{row.title} detected for {row.site_id}.",
        created_at=row.received_at or datetime.now(UTC),
        raised_at=row.raised_at,
        received_at=row.received_at,
        provenance=provenance,
        resolved_at=row.resolved_at,
    )


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
