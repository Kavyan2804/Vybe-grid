from abc import ABC, abstractmethod
from typing import Dict, Any, Protocol, Sequence, Optional
from .entities import Site, Forecast, DispatchDecision, DispatchPlan


class ForecastPort(ABC):
    @abstractmethod
    def fetch_forecast(self, site: Site) -> Forecast:
        pass


class HistoricalSolarPort(Protocol):
    """Historical solar observations used for backtesting, never live dispatch."""

    def fetch_hourly_irradiance(
        self, site: Site, start_date: str, end_date: str
    ) -> Sequence[float]:
        ...


class OptimizerPort(ABC):
    @abstractmethod
    def solve(
        self,
        site: Site,
        forecast: Forecast,
        initial_soc_pct: float = 50.0,
        initial_diesel_on: bool = False,
        initial_diesel_run_hours: int = 0,
        initial_diesel_off_hours: int = 10,
        solver_timeout_seconds: float = 20.0,
    ) -> DispatchPlan:
        pass


class DispatchPort(ABC):
    @abstractmethod
    def execute(
        self, site: Site, decision: DispatchDecision, current_soc_pct: float
    ) -> Dict[str, Any]:
        pass


class PlanRepository(Protocol):
    """Persistence port for dispatch plans (PLANNED domain)."""

    def save(self, plan: DispatchPlan) -> None:
        ...

    def latest(self, site_id: str) -> Optional[DispatchPlan]:
        ...


class TelemetryRepository(Protocol):
    """Persistence port for actual telemetry readings (ACTUAL domain)."""

    def record(self, reading: Dict[str, Any]) -> None:
        ...

    def latest_soc(self, site_id: str) -> Optional[float]:
        """Return latest measured SoC in kWh or percent."""
        ...


class AlertPort(Protocol):
    """Notification port for system alerts (e.g. SOLVER_FALLBACK_ACTIVE)."""

    def emit(
        self, alert_type: str, subject: str, payload: Optional[Dict[str, Any]] = None
    ) -> None:
        ...
