"""Plans API router per API_CONTRACT.md §2."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Query

from src.config.settings import get_settings
from src.schemas.plans import DispatchPlanResponse

router = APIRouter(tags=["plans"])


@router.get("/plans/latest", response_model=DispatchPlanResponse)
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
