import asyncio
from datetime import datetime, timezone
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from src.db.models.sites import Site
from src.db.models.forecasts import Forecast
from src.db.models.telemetry import Telemetry
from src.db.models.dispatch_plans import DispatchPlan
from src.db.repositories.dispatch_plans import DispatchPlanRepository
from src.db.repositories.telemetry import TelemetryRepository

DSN = "postgresql+asyncpg://gridpilot:gridpilot@localhost:5433/gridpilot"
engine = create_async_engine(DSN)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)

async def main():
    async with AsyncSessionLocal() as session:
        # Step 8
        print("--- STEP 8 ---")
        repo = DispatchPlanRepository(session)
        # Create site
        session.add(Site(id="example-site-2", name="Test Site", timezone="UTC", config_version=1, config={}))
        await session.flush()
        
        # Create forecast
        session.add(Forecast(site_id="example-site-2", issued_at=datetime(2026,1,1,9,tzinfo=timezone.utc), horizon_hours=24, source="test", stale=False, series={}))
        await session.flush()
        
        # Create telemetry
        session.add(Telemetry(site_id="example-site-2", at=datetime(2026,1,1,9,tzinfo=timezone.utc), soc_kwh=80, diesel_on=False, diesel_kw=0, batt_kw=0, solar_kw=0, load_kw=0, source="simulator", config_version=1))
        session.add(Telemetry(site_id="example-site-2", at=datetime(2026,1,1,10,tzinfo=timezone.utc), soc_kwh=75, diesel_on=False, diesel_kw=0, batt_kw=0, solar_kw=0, load_kw=0, source="simulator", config_version=1))
        session.add(Telemetry(site_id="example-site-2", at=datetime(2026,1,1,11,tzinfo=timezone.utc), soc_kwh=68, diesel_on=False, diesel_kw=0, batt_kw=0, solar_kw=0, load_kw=0, source="simulator", config_version=1))
        await session.flush()
        
        # Create dispatch plan
        plan = DispatchPlan(site_id="example-site-2", tick_at=datetime(2026,1,1,11,tzinfo=timezone.utc), forecast_id=1, config_version=1, starting_soc_kwh=68.0, series={"h1": 1}, objective_cost=100.0, solver_status="optimal", solve_ms=100, source="milp")
        await repo.create(plan)
        await session.commit()
        
        # Read it back
        read_plan = await repo.get_latest_for_site("example-site-2")
        print(f"Read back plan: site_id={read_plan.site_id}, tick_at={read_plan.tick_at}, starting_soc_kwh={read_plan.starting_soc_kwh}")

        # Step 9
        print("--- STEP 9 ---")
        await repo.create(DispatchPlan(site_id="example-site-2", tick_at=datetime(2026,1,1,12,tzinfo=timezone.utc), forecast_id=1, config_version=1, starting_soc_kwh=60.0, series={"h1": 2}, objective_cost=200.0, solver_status="optimal", solve_ms=100, source="milp"))
        await repo.create(DispatchPlan(site_id="example-site-2", tick_at=datetime(2026,1,1,10,30,tzinfo=timezone.utc), forecast_id=1, config_version=1, starting_soc_kwh=70.0, series={"h1": 3}, objective_cost=300.0, solver_status="optimal", solve_ms=100, source="milp"))
        await session.commit()
        
        latest_plan = await repo.get_latest_for_site("example-site-2")
        print(f"Latest plan by tick_at is: tick_at={latest_plan.tick_at}")

        # Step 10 (Telemetry)
        print("--- STEP 10 ---")
        telemetry_repo = TelemetryRepository(session)
        latest_soc = await telemetry_repo.latest_soc("example-site-2")
        print(f"Latest SoC by timestamp is: {latest_soc}")

asyncio.run(main())
