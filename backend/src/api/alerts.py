"""Alerts API router per API_CONTRACT.md §6."""

from __future__ import annotations

from fastapi import APIRouter, Path, status

from src.schemas.alerts import AlertActionResponse

router = APIRouter(tags=["alerts"])


@router.post(
    "/alerts/{alert_id}/acknowledge",
    response_model=AlertActionResponse,
    status_code=status.HTTP_200_OK,
)
async def acknowledge_alert(
    alert_id: str = Path(..., min_length=1, description="ID of the alert to acknowledge")
) -> AlertActionResponse:
    """Acknowledge an open alert.

    Per API_CONTRACT.md §6:
    Lifecycle transition: created -> acknowledged.
    """
    clean_id = alert_id.strip()

    # -----------------------------------------------------------------------
    # Phase 1 Temporary Response:
    #
    # TODO (Dhruvi): Integrate with database AlertRepository:
    #   1. Fetch alert from database table `alerts` by id.
    #   2. If not found, raise 404 per API_CONTRACT.md §9.
    #   3. Validate current state is 'created' (raise 409 on illegal transition per PRD §11).
    #   4. Update alert.state = 'acknowledged' and commit.
    # -----------------------------------------------------------------------
    return AlertActionResponse(id=clean_id, state="acknowledged")


@router.post(
    "/alerts/{alert_id}/resolve",
    response_model=AlertActionResponse,
    status_code=status.HTTP_200_OK,
)
async def resolve_alert(
    alert_id: str = Path(..., min_length=1, description="ID of the alert to resolve")
) -> AlertActionResponse:
    """Resolve an open or acknowledged alert.

    Per API_CONTRACT.md §6:
    Lifecycle transition: created | acknowledged -> resolved.
    """
    clean_id = alert_id.strip()

    # -----------------------------------------------------------------------
    # Phase 1 Temporary Response:
    #
    # TODO (Dhruvi): Integrate with database AlertRepository:
    #   1. Fetch alert from database table `alerts` by id.
    #   2. If not found, raise 404 per API_CONTRACT.md §9.
    #   3. Validate state != 'resolved' (raise 409 on duplicate resolve).
    #   4. Update alert.state = 'resolved', set resolved_at = now() (starts cooldown per PRD §11).
    #   5. Commit change.
    # -----------------------------------------------------------------------
    return AlertActionResponse(id=clean_id, state="resolved")
