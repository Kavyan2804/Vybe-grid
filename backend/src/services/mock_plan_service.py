"""Development-only deterministic mock plan service."""

from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime

from src.errors import ResourceNotFoundError
from src.schemas.plans import MockPlan, MockPlanRequest, MockSolverStatus


class MockPlanNotFoundError(ResourceNotFoundError):
    """Raised when a mock plan ID does not exist."""


class MockPlanService:
    """Generate and store deterministic plans behind a replaceable service boundary."""

    def __init__(self) -> None:
        self._plans: dict[str, MockPlan] = {}
        self._sequence_by_site: dict[str, int] = {}

    def create_plan(self, request: MockPlanRequest) -> MockPlan:
        sequence = self._sequence_by_site.get(request.site_id, 0) + 1
        self._sequence_by_site[request.site_id] = sequence
        plan_id = f"mock-plan-{request.site_id}-{sequence:03d}"
        dispatch = [
            {
                "hour": hour,
                "solar_kw": float((hour % 6) * 5),
                "wind_kw": float(8 + (hour % 3) * 2),
                "battery_kw": 5.0 if hour % 4 < 2 else -5.0,
                "diesel_kw": 0.0 if hour % 6 else 10.0,
                "load_kw": float(35 + (hour % 5) * 3),
            }
            for hour in range(request.horizon_hours)
        ]
        plan = MockPlan(
            plan_id=plan_id,
            site_id=request.site_id,
            created_at=datetime.now(UTC),
            planning_horizon_hours=request.horizon_hours,
            solver_status=MockSolverStatus.MOCK,
            total_cost=float(request.horizon_hours * 2),
            total_emissions_kg_co2=float(request.horizon_hours),
            dispatch=dispatch,
        )
        self._plans[plan_id] = plan
        return deepcopy(plan)

    def get_plan(self, plan_id: str) -> MockPlan:
        plan = self._plans.get(plan_id)
        if plan is None:
            raise MockPlanNotFoundError(f"Mock plan '{plan_id}' was not found")
        return deepcopy(plan)

    def latest_for_site(self, site_id: str) -> MockPlan:
        plans = self.list_for_site(site_id)
        if not plans:
            raise MockPlanNotFoundError(f"No mock plans were found for site '{site_id}'")
        return plans[-1]

    def list_for_site(self, site_id: str) -> list[MockPlan]:
        return [
            deepcopy(plan)
            for plan in self._plans.values()
            if plan.site_id == site_id
        ]


mock_plan_service = MockPlanService()
