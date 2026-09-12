"""Plans API router per API_CONTRACT.md §2."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Query

from src.config.settings import get_settings
from src.openapi import OPENAPI_ERROR_RESPONSES
from src.schemas.plans import DispatchPlanResponse, MockPlan, MockPlanRequest
from src.services.mock_plan_service import MockPlanNotFoundError, mock_plan_service

router = APIRouter(tags=["plans"])


@router.post(
    "/plans/mock",
    response_model=MockPlan,
    status_code=201,
    summary="Create a deterministic mock plan",
    description="Generate and store a deterministic development-only plan. This is not optimizer output.",
    response_description="The generated mock plan with solver_status='mock'.",
    responses=OPENAPI_ERROR_RESPONSES,
)
async def create_mock_plan(request: MockPlanRequest) -> MockPlan:
    """Create a deterministic development-only mock plan."""
    return mock_plan_service.create_plan(request)


@router.get(
    "/plans/mock",
    response_model=list[MockPlan],
    summary="List mock plans for a site",
    description="List deterministic development-only plans stored for the requested site.",
    response_description="Matching mock plans.",
    responses=OPENAPI_ERROR_RESPONSES,
)
async def list_mock_plans(site_id: str = Query(..., min_length=1)) -> list[MockPlan]:
    """List development-only mock plans for a site."""
    return mock_plan_service.list_for_site(site_id)


@router.get(
    "/plans/mock/latest",
    response_model=MockPlan,
    summary="Get the latest mock plan",
    description="Retrieve the newest deterministic development-only plan for a site.",
    response_description="The latest mock plan.",
    responses=OPENAPI_ERROR_RESPONSES,
)
async def get_latest_mock_plan(site_id: str = Query(..., min_length=1)) -> MockPlan:
    """Retrieve the latest development-only mock plan for a site."""
    try:
        return mock_plan_service.latest_for_site(site_id)
    except MockPlanNotFoundError as exc:
        from fastapi import HTTPException

        raise HTTPException(
            status_code=404,
            detail={"error": "mock_plan_not_found", "message": str(exc), "detail": {}},
        ) from exc


@router.get(
    "/plans/mock/{plan_id}",
    response_model=MockPlan,
    summary="Get a mock plan",
    description="Retrieve one deterministic development-only plan by ID.",
    response_description="The requested mock plan.",
    responses=OPENAPI_ERROR_RESPONSES,
)
async def get_mock_plan(plan_id: str) -> MockPlan:
    """Retrieve one development-only mock plan by ID."""
    try:
        return mock_plan_service.get_plan(plan_id)
    except MockPlanNotFoundError as exc:
        from fastapi import HTTPException

        raise HTTPException(
            status_code=404,
            detail={"error": "mock_plan_not_found", "message": str(exc), "detail": {}},
        ) from exc


@router.get(
    "/plans/latest",
    response_model=DispatchPlanResponse,
    summary="Get the Phase 1 placeholder plan",
    description="Return the existing Phase 1 placeholder response. It is pending optimizer integration and contains no dispatch series.",
    response_description="Placeholder plan marked pending_integration.",
    responses=OPENAPI_ERROR_RESPONSES,
)
async def get_latest_plan(
    site_id: str = Query(
        default="",
        description="Site ID to query. Defaults to DEFAULT_SITE_ID from settings.",
    )
) -> DispatchPlanResponse:
    """Fetch the most recent 24-hour dispatch plan for a microgrid site.

    Per API_CONTRACT.md §2:
    Returns the latest solved dispatch plan with hourly series and provenance badges.
    """
    settings = get_settings()
    active_site_id = site_id.strip() if site_id.strip() else settings.default_site_id

    # -----------------------------------------------------------------------
    # Phase 1 Temporary Response:
    #
    # TODO (Dhruvi): Integrate with database PlanRepository:
    #   plan = await plan_repository.latest(site_id=active_site_id)
    #   if not plan:
    #       raise HTTPException(status_code=404, detail={"error": "not_found", "message": f"Site or plan '{active_site_id}' not found."})
    #
    # TODO (Aarin): Integrate with rolling_horizon_service / OptimizerPort:
    #   Trigger or read actual 24-hour MILP solved plan with real series.
    #
    # Strictly adheres to PRD.md §3 (no fabricated numbers or fake curves).
    # -----------------------------------------------------------------------
    return DispatchPlanResponse(
        plan_id=f"plan_{active_site_id}_phase1",
        site_id=active_site_id,
        tick_at=datetime.now(UTC).isoformat(),
        starting_soc_kwh=0.0,
        series=[],
        objective_cost=0.0,
        solver_status="pending_integration",
        solve_ms=0,
    )
