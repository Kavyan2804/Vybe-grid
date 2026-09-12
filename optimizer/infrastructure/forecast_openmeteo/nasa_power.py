"""NASA POWER historical solar adapter for backtesting only.

NASA POWER is keyless. This adapter intentionally exposes historical irradiance
and is not a ForecastPort, so it cannot be used by live dispatch ingestion.
"""

from datetime import date
from typing import Sequence

import httpx

from optimizer.domain.entities import Site
from optimizer.domain.ports import HistoricalSolarPort


class NasaPowerHistoricalAdapter(HistoricalSolarPort):
    """Fetch hourly all-sky surface shortwave irradiance from NASA POWER."""

    base_url = "https://power.larc.nasa.gov/api/temporal/hourly/point"

    def __init__(self, timeout: float = 20.0) -> None:
        self.timeout = timeout

    def fetch_hourly_irradiance(
        self, site: Site, start_date: str, end_date: str
    ) -> Sequence[float]:
        _validate_date(start_date)
        _validate_date(end_date)
        if start_date > end_date:
            raise ValueError("start_date must be on or before end_date")

        response = httpx.get(
            self.base_url,
            params={
                "parameters": "ALLSKY_SFC_SW_DWN",
                "community": "RE",
                "longitude": site.longitude,
                "latitude": site.latitude,
                "start": start_date.replace("-", ""),
                "end": end_date.replace("-", ""),
                "format": "JSON",
                "time-standard": "utc",
            },
            timeout=self.timeout,
        )
        response.raise_for_status()
        try:
            values = response.json()["properties"]["parameter"]["ALLSKY_SFC_SW_DWN"]
        except (KeyError, TypeError) as exc:
            raise ValueError("NASA POWER response lacks hourly irradiance data") from exc

        ordered = []
        for timestamp in sorted(values):
            value = values[timestamp]
            if value is None or value < 0:
                raise ValueError(f"NASA POWER returned invalid irradiance at {timestamp}")
            ordered.append(float(value))
        if not ordered:
            raise ValueError("NASA POWER returned no hourly irradiance data")
        return ordered


def _validate_date(value: str) -> None:
    try:
        date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"date must be YYYY-MM-DD: {value}") from exc
