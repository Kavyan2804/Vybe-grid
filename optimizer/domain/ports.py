from abc import ABC, abstractmethod
from typing import Dict, Any, Protocol, Sequence
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
    def solve(self, site: Site, forecast: Forecast, initial_soc_pct: float) -> DispatchPlan:
        pass

class DispatchPort(ABC):
    @abstractmethod
    def execute(self, site: Site, decision: DispatchDecision, current_soc_pct: float) -> Dict[str, Any]:
        pass
