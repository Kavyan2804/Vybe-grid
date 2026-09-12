"""End-to-end integration checks for the completed Phase 3 backend slices."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient

from src.api import alerts as alerts_api
from src.api import events as events_api
from src.api import savings as savings_api
from src.main import app
from src.realtime.broadcaster import (
    InMemoryBroadcaster,
    RealtimeEvent,
    RealtimeEventType,
)
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
from src.schemas.alerts import AlertCreateRequest, AlertSeverity, AlertType
from src.schemas.telemetry import TelemetryPoint, TelemetrySource
from src.services.alert_service import InMemoryAlertService
from src.services.repository_dependencies import RepositoryDependencies
from src.services.savings_facade import SavingsFacade
from src.services.savings_service import FuelConversion

SITE_ID = "phase3-site"
START = datetime(2026, 1, 1, tzinfo=UTC)
END = START + timedelta(hours=1)


def _dependencies() -> RepositoryDependencies:
    return RepositoryDependencies(
        telemetry_repository=InMemoryTelemetryRepository(),
        dispatch_plan_repository=InMemoryDispatchPlanRepository(),
        dispatch_log_repository=InMemoryDispatchLogRepository(),
    )


def _seed_phase3_data(dependencies: RepositoryDependencies) -> None:
    dependencies.dispatch_plan_repository.append(
        DispatchPlanRecord(
            id=101,
            site_id=SITE_ID,
            tick_at=START,
            forecast_id=7,
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
            solve_ms=20,
            source=DispatchPlanSource.MILP,
        )
    )
    for point_id, diesel_kw, source in (
        ("optimized-101", 2.0, TelemetrySource.SIMULATOR),
        ("baseline-101", 6.0, TelemetrySource.BASELINE),
    ):
        dependencies.telemetry_repository.append(
            TelemetryPoint(
                id=point_id,
                site_id=SITE_ID,
                at=START,
                soc_kwh=20.0,
                diesel_on=True,
                diesel_kw=diesel_kw,
                batt_kw=1.0,
                solar_kw=4.0,
                load_kw=4.0,
                source=source,
                config_version=1,
            )
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


@pytest.fixture
def phase3(monkeypatch: pytest.MonkeyPatch):
    dependencies = _dependencies()
    _seed_phase3_data(dependencies)
    monkeypatch.setattr(savings_api, "_configured_facade", _facade(dependencies))
    alert_service = InMemoryAlertService(seed_demo=False, clock=lambda: START)
    monkeypatch.setattr(alerts_api, "alert_service", alert_service)
    realtime_broadcaster = InMemoryBroadcaster()
    monkeypatch.setattr(events_api, "broadcaster", realtime_broadcaster)
    return dependencies, alert_service, realtime_broadcaster


def test_repositories_and_savings_facade_keep_planned_and_actual_data_separate(phase3) -> None:
    dependencies, _, _ = phase3
    plan = dependencies.dispatch_plan_repository.latest_for_site(site_id=SITE_ID)
    optimized = dependencies.telemetry_repository.list_for_site_in_range(
        site_id=SITE_ID, start_at=START, end_at=END, source=TelemetrySource.SIMULATOR
    )
    baseline = dependencies.telemetry_repository.list_for_site_in_range(
        site_id=SITE_ID, start_at=START, end_at=END, source=TelemetrySource.BASELINE
    )
    result = _facade(dependencies).calculate(site_id=SITE_ID, start_at=START, end_at=END)

    assert plan is not None
    assert plan.site_id == SITE_ID
    assert optimized and baseline
    assert {point.site_id for point in optimized + baseline} == {SITE_ID}
    assert {point.at for point in optimized} == {START}
    assert {point.at for point in baseline} == {START}
    assert len(result.comparison.hours) == 1
    assert result.comparison.hours[0].planned_diesel_kw == 2.0
    assert result.optimized.diesel_energy_kwh == 2.0
    assert result.baseline.diesel_energy_kwh == 6.0
    assert result.saved.diesel_energy_kwh == 4.0


@pytest.mark.asyncio
async def test_savings_api_returns_read_only_comparison(phase3) -> None:
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/api/savings",
            params={
                "site_id": SITE_ID,
                "start_at": START.isoformat(),
                "end_at": END.isoformat(),
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"comparison", "optimized", "baseline", "saved"}
    assert body["comparison"]["site_id"] == SITE_ID
    assert body["optimized"]["diesel_energy_kwh"] == 2.0
    assert body["baseline"]["diesel_energy_kwh"] == 6.0
    assert body["saved"]["diesel_energy_kwh"] == 4.0


@pytest.mark.asyncio
async def test_alert_lifecycle_and_duplicate_suppression(phase3) -> None:
    _, alert_service, _ = phase3
    request = AlertCreateRequest(
        site_id=SITE_ID,
        severity=AlertSeverity.WARNING,
        title="Low reserve",
        message="Battery reserve is low.",
    )
    first = alert_service.raise_alert(
        site_id=SITE_ID,
        alert_type=AlertType.LOW_SOC_RESERVE,
        subject="battery",
        severity=request.severity,
        title=request.title,
        message=request.message,
        raised_at=START,
        received_at=START,
    )
    duplicate = alert_service.raise_alert(
        site_id=SITE_ID,
        alert_type=AlertType.LOW_SOC_RESERVE,
        subject="battery",
        severity=request.severity,
        title=request.title,
        message=request.message,
        raised_at=START,
        received_at=START,
    )
    acknowledged = alert_service.acknowledge(first.id, at=START)
    resolved = alert_service.resolve(first.id, at=START)

    assert duplicate.id == first.id
    assert acknowledged.status.value == "acknowledged"
    assert resolved.status.value == "resolved"
    assert len(alert_service.list()[1]) == 1


@pytest.mark.asyncio
async def test_alert_api_lifecycle_is_available_in_same_flow(phase3) -> None:
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        created = await client.post(
            "/api/alerts",
            json={
                "site_id": SITE_ID,
                "severity": "warning",
                "title": "Telemetry alert",
                "message": "A test alert was raised.",
            },
        )
        alert_id = created.json()["id"]
        acknowledged = await client.post(f"/api/alerts/{alert_id}/acknowledge")
        resolved = await client.post(f"/api/alerts/{alert_id}/resolve")

    assert created.status_code == 201
    assert acknowledged.json()["state"] == "acknowledged"
    assert resolved.json()["state"] == "resolved"


@pytest.mark.asyncio
async def test_broadcaster_and_sse_keep_events_site_scoped_and_formatted(phase3) -> None:
    _, _, broadcaster = phase3
    response = await events_api.stream_events(site_id=SITE_ID)
    body_iterator = response.body_iterator
    first = asyncio.create_task(body_iterator.__anext__())
    await asyncio.sleep(0)

    event = RealtimeEvent(
        type=RealtimeEventType.ALERT_CREATED,
        site_id=SITE_ID,
        subject="alert-101",
        timestamp=START,
        payload={"alert_id": "alert-101", "severity": "warning"},
    )
    other_site_event = event.model_copy(update={"site_id": "other-site"})
    assert broadcaster.publish(other_site_event) == 0
    assert broadcaster.publish(event) == 1

    rendered = await first
    assert rendered == (
        'event: alert.created\ndata: {"alert_id": "alert-101", "severity": "warning"}\n\n'
    )
    assert json.loads(rendered.split("data: ", 1)[1].splitlines()[0]) == event.payload
    await body_iterator.aclose()
    assert broadcaster.subscriber_count == 0
