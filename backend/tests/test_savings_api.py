"""API tests for the read-only Phase 3 savings endpoint."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient

from src.api import savings as savings_api
from src.main import app
from src.repositories.in_memory import (
    InMemoryDispatchLogRepository,
    InMemoryDispatchPlanRepository,
    InMemoryTelemetryRepository,
)
from src.repositories.protocols import (
    DispatchPlanRecord,
    DispatchPlanSource,
    DispatchSolverStatus,
)
from src.schemas.telemetry import TelemetryPoint, TelemetrySource
from src.services.repository_dependencies import RepositoryDependencies
from src.services.savings_facade import SavingsFacade
from src.services.savings_service import FuelConversion


def _dependencies() -> RepositoryDependencies:
    return RepositoryDependencies(
        telemetry_repository=InMemoryTelemetryRepository(),
        dispatch_plan_repository=InMemoryDispatchPlanRepository(),
        dispatch_log_repository=InMemoryDispatchLogRepository(),
    )


def _facade(dependencies: RepositoryDependencies) -> SavingsFacade:
    return SavingsFacade(
        dependencies,
        FuelConversion(
            fuel_litres_per_kwh=0.25,
            fuel_cost_per_litre=100.0,
            co2_kg_per_litre=2.5,
        ),
    )


def _seed_complete_data(dependencies: RepositoryDependencies) -> datetime:
    at = datetime(2026, 1, 1, tzinfo=UTC)
    dependencies.dispatch_plan_repository.append(
        DispatchPlanRecord(
            id=1,
            site_id="site-a",
            tick_at=at,
            forecast_id=1,
            config_version=1,
            starting_soc_kwh=20.0,
            series=[
                {
                    "hour": 0,
                    "diesel_kw": 2.0,
                    "batt_charge_kw": 1.0,
                    "batt_discharge_kw": 0.0,
                    "solar_used_kw": 4.0,
                    "unmet_flex_kw": 0.0,
                }
            ],
            objective_cost=10.0,
            solver_status=DispatchSolverStatus.OPTIMAL,
            solve_ms=100,
            source=DispatchPlanSource.MILP,
        )
    )
    for point_id, diesel_kw, source in (
        ("optimized-1", 2.0, TelemetrySource.SIMULATOR),
        ("baseline-1", 6.0, TelemetrySource.BASELINE),
    ):
        dependencies.telemetry_repository.append(
            TelemetryPoint(
                id=point_id,
                site_id="site-a",
                at=at,
                soc_kwh=20.0,
                diesel_on=diesel_kw > 0,
                diesel_kw=diesel_kw,
                batt_kw=1.0,
                solar_kw=4.0,
                load_kw=4.0,
                source=source,
                config_version=1,
            )
        )
    return at


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch):
    dependencies = _dependencies()
    monkeypatch.setattr(savings_api, "_configured_facade", _facade(dependencies))

    async def make_client():
        transport = ASGITransport(app=app, raise_app_exceptions=False)
        async with AsyncClient(transport=transport, base_url="http://test") as http_client:
            yield http_client

    return dependencies, make_client


@pytest.mark.asyncio
async def test_successful_response_contains_comparison_and_metrics(client) -> None:
    dependencies, make_client = client
    at = _seed_complete_data(dependencies)

    async for http_client in make_client():
        response = await http_client.get(
            "/api/savings",
            params={
                "site_id": "site-a",
                "start_at": at.isoformat(),
                "end_at": (at + timedelta(hours=1)).isoformat(),
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["comparison"]["hours"][0]["actual_diesel_kw"] == 2.0
    assert body["optimized"]["diesel_energy_kwh"] == 2.0
    assert body["baseline"]["diesel_energy_kwh"] == 6.0
    assert body["saved"]["diesel_energy_kwh"] == 4.0


@pytest.mark.asyncio
async def test_query_validation_rejects_missing_or_naive_timestamps(client) -> None:
    _, make_client = client

    async for http_client in make_client():
        missing = await http_client.get("/api/savings", params={"site_id": "site-a"})
        naive = await http_client.get(
            "/api/savings",
            params={
                "site_id": "site-a",
                "start_at": "2026-01-01T00:00:00",
                "end_at": "2026-01-01T01:00:00",
            },
        )

    assert missing.status_code == 422
    assert naive.status_code == 422
    assert naive.json()["error"] == "validation_error"


@pytest.mark.asyncio
async def test_invalid_range_returns_bad_request(client) -> None:
    _, make_client = client
    at = datetime(2026, 1, 1, tzinfo=UTC)

    async for http_client in make_client():
        response = await http_client.get(
            "/api/savings",
            params={
                "site_id": "site-a",
                "start_at": at.isoformat(),
                "end_at": at.isoformat(),
            },
        )

    assert response.status_code == 400
    assert response.json()["error"] == "invalid_time_range"


@pytest.mark.asyncio
async def test_missing_plan_and_telemetry_are_clear_not_found_errors(client) -> None:
    dependencies, make_client = client
    at = datetime(2026, 1, 1, tzinfo=UTC)

    async for http_client in make_client():
        missing_plan = await http_client.get(
            "/api/savings",
            params={
                "site_id": "site-a",
                "start_at": at.isoformat(),
                "end_at": (at + timedelta(hours=1)).isoformat(),
            },
        )
    assert missing_plan.status_code == 404
    assert missing_plan.json()["error"] == "dispatch_plan_not_found"

    dependencies.dispatch_plan_repository.append(
        DispatchPlanRecord(
            id=1,
            site_id="site-a",
            tick_at=at,
            forecast_id=1,
            config_version=1,
            starting_soc_kwh=20.0,
            series=[{"hour": 0, "diesel_kw": 2.0}],
            objective_cost=10.0,
            solver_status=DispatchSolverStatus.OPTIMAL,
            solve_ms=100,
            source=DispatchPlanSource.MILP,
        )
    )
    async for http_client in make_client():
        missing_telemetry = await http_client.get(
            "/api/savings",
            params={
                "site_id": "site-a",
                "start_at": at.isoformat(),
                "end_at": (at + timedelta(hours=1)).isoformat(),
            },
        )

    assert missing_telemetry.status_code == 404
    assert missing_telemetry.json()["error"] == "telemetry_not_found"
