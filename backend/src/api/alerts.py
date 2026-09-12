"""Alert management API routes — Postgres by default, in-memory override for unit tests."""

from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.session import async_session_factory
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
    AlertNotFoundError as MemoryAlertNotFoundError,
)
from src.services.alert_service import (
    AlertTransitionError as MemoryAlertTransitionError,
)
from src.services.alert_service import InMemoryAlertService
from src.services.postgres_alert_service import (
    AlertNotFoundError,
    AlertTransitionError,
    PostgresAlertService,
)

router = APIRouter(tags=["alerts"])

# Unit tests monkeypatch this with an InMemoryAlertService. When None, routes use Postgres.
alert_service: InMemoryAlertService | None = None


async def get_alerts_db_session() -> AsyncIterator[AsyncSession | None]:
    """Open a DB session only when the Postgres-backed path is active."""
    if alert_service is not None:
        yield None
        return
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


def _pg(session: AsyncSession | None) -> PostgresAlertService:
    if session is None:
        raise RuntimeError("Postgres alert service requires a database session")
    return PostgresAlertService(session)


@router.post(
    "/alerts",
    response_model=Alert,
    status_code=status.HTTP_201_CREATED,
    summary="Create an alert",
    responses=OPENAPI_ERROR_RESPONSES,
)
async def create_alert(
    request: AlertCreateRequest,
    session: AsyncSession | None = Depends(get_alerts_db_session),
) -> Alert:
    if alert_service is not None:
        return alert_service.create(request)
    return await _pg(session).create(request)


@router.get(
    "/alerts",
    response_model=AlertListResponse,
    summary="List and filter alerts",
    responses=OPENAPI_ERROR_RESPONSES,
)
async def list_alerts(
    site_id: str | None = Query(None, min_length=1),
    severity: AlertSeverity | None = None,
    status_filter: AlertStatus | None = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    session: AsyncSession | None = Depends(get_alerts_db_session),
) -> AlertListResponse:
    if alert_service is not None:
        total, items = alert_service.list(
            site_id=site_id,
            severity=severity,
            status=status_filter,
            limit=limit,
            offset=offset,
        )
        return AlertListResponse(total=total, items=items)
    total, items = await _pg(session).list(
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
    responses=OPENAPI_ERROR_RESPONSES,
)
async def list_active_alerts(
    site_id: str | None = Query(None, min_length=1),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    session: AsyncSession | None = Depends(get_alerts_db_session),
) -> AlertListResponse:
    if alert_service is not None:
        active = alert_service.list_active_alerts(site_id=site_id)
        return AlertListResponse(total=len(active), items=active[offset : offset + limit])
    active = await _pg(session).list_active_alerts(site_id=site_id)
    return AlertListResponse(total=len(active), items=active[offset : offset + limit])


@router.get(
    "/alerts/{alert_id}",
    response_model=Alert,
    summary="Get an alert",
    responses=OPENAPI_ERROR_RESPONSES,
)
async def get_alert(
    alert_id: str = Path(..., min_length=1),
    session: AsyncSession | None = Depends(get_alerts_db_session),
) -> Alert:
    try:
        if alert_service is not None:
            return alert_service.get(alert_id.strip())
        return await _pg(session).get(alert_id.strip())
    except (AlertNotFoundError, MemoryAlertNotFoundError) as exc:
        raise _not_found(exc) from exc


@router.post(
    "/alerts/{alert_id}/acknowledge",
    response_model=AlertActionResponse,
    summary="Acknowledge an alert",
    responses=OPENAPI_ERROR_RESPONSES,
)
async def acknowledge_alert(
    alert_id: str = Path(..., min_length=1),
    session: AsyncSession | None = Depends(get_alerts_db_session),
) -> AlertActionResponse:
    try:
        if alert_service is not None:
            alert = alert_service.acknowledge(alert_id.strip())
        else:
            alert = await _pg(session).acknowledge(alert_id.strip())
    except (AlertNotFoundError, MemoryAlertNotFoundError) as exc:
        raise _not_found(exc) from exc
    except (AlertTransitionError, MemoryAlertTransitionError) as exc:
        raise _conflict(exc) from exc
    return AlertActionResponse(id=alert.id, state=alert.status)


@router.post(
    "/alerts/{alert_id}/resolve",
    response_model=AlertActionResponse,
    summary="Resolve an alert",
    responses=OPENAPI_ERROR_RESPONSES,
)
async def resolve_alert(
    alert_id: str = Path(..., min_length=1),
    session: AsyncSession | None = Depends(get_alerts_db_session),
) -> AlertActionResponse:
    try:
        if alert_service is not None:
            alert = alert_service.resolve(alert_id.strip())
        else:
            alert = await _pg(session).resolve(alert_id.strip())
    except (AlertNotFoundError, MemoryAlertNotFoundError) as exc:
        raise _not_found(exc) from exc
    except (AlertTransitionError, MemoryAlertTransitionError) as exc:
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
