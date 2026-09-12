"""Open-Meteo forecast adapter with persistence fallback (Task 0.2).

Fetches hourly GHI, cloud cover, temperature for the next 24h from Open-Meteo.
Falls back to the last successful forecast if the live fetch fails, marking it stale=True.
"""
import json
import os
import httpx
from datetime import datetime
from typing import List

from optimizer.domain.entities import Site, Forecast
from optimizer.domain.ports import ForecastPort
from .synthetic_load import generate_synthetic_load


class OpenMeteoForecastAdapter(ForecastPort):
    """Fetches solar forecasts from Open-Meteo and generates synthetic load profiles.

    Persistence fallback: if the live fetch fails, reuse the last successful
    forecast with stale=True — never silently reused as fresh.
    """

    def __init__(self, fallback_dir: str = "data/forecasts"):
        self.fallback_dir = fallback_dir
        os.makedirs(self.fallback_dir, exist_ok=True)

    def fetch_forecast(self, site: Site) -> Forecast:
        fallback_file = os.path.join(
            self.fallback_dir,
            f"{site.name.replace(' ', '_')}_latest.json",
        )
        now = datetime.now()
        is_weekend = now.weekday() >= 5
        load_kw = generate_synthetic_load(is_weekend)

        try:
            url = (
                f"https://api.open-meteo.com/v1/forecast"
                f"?latitude={site.latitude}"
                f"&longitude={site.longitude}"
                f"&hourly=temperature_2m,cloud_cover,direct_radiation"
                f"&timezone={site.timezone}"
            )
            response = httpx.get(url, timeout=10)
            response.raise_for_status()
            data = response.json()

            # Convert GHI (direct_radiation as proxy) to estimated solar power.
            # Assume 50 kW solar capacity, 1000 W/m² standard irradiance,
            # 0.85 performance ratio.
            solar_capacity_kw = 50.0
            radiation = data["hourly"]["direct_radiation"][:24]
            solar_kw = [
                min(solar_capacity_kw, (r / 1000.0) * solar_capacity_kw * 0.85)
                for r in radiation
            ]

            forecast = Forecast(
                solar_kw=solar_kw,
                load_kw=load_kw,
                source="open-meteo & synthetic",
                stale=False,
                fetched_at=now,
            )

            # Save for fallback use
            with open(fallback_file, "w") as f:
                json.dump(
                    {
                        "solar_kw": forecast.solar_kw,
                        "load_kw": forecast.load_kw,
                        "source": forecast.source,
                        "fetched_at": forecast.fetched_at.isoformat(),
                    },
                    f,
                )

            return forecast

        except Exception:
            # Persistence fallback — reuse last successful forecast, marked stale
            if os.path.exists(fallback_file):
                with open(fallback_file, "r") as f:
                    data = json.load(f)
                return Forecast(
                    solar_kw=data["solar_kw"],
                    load_kw=data["load_kw"],
                    source=data["source"],
                    stale=True,
                    fetched_at=datetime.fromisoformat(data["fetched_at"]),
                )
            else:
                # Absolute fallback — no prior forecast cached
                return Forecast(
                    solar_kw=[0.0] * 24,
                    load_kw=load_kw,
                    source="fallback (zeros)",
                    stale=True,
                    fetched_at=now,
                )
