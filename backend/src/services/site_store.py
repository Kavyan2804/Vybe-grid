"""In-memory site configuration storage for local development."""

from __future__ import annotations

from copy import deepcopy

from src.errors import ResourceConflictError, ResourceNotFoundError
from src.schemas.sites import Site
from src.services.site_configuration import normalize_site_configuration


class SiteAlreadyExistsError(ResourceConflictError):
    """Raised when a site ID is already present in the store."""


class SiteNotFoundError(ResourceNotFoundError):
    """Raised when a site ID is not present in the store."""


class InMemorySiteService:
    """Small typed site store that can be replaced by persistence later."""

    def __init__(self, seed_demo: bool = True) -> None:
        self._sites: dict[str, Site] = {}
        if seed_demo:
            self.create(_demo_site())

    def create(self, site: Site) -> Site:
        normalized = normalize_site_configuration(site)
        if normalized.site_id in self._sites:
            raise SiteAlreadyExistsError(f"Site '{normalized.site_id}' already exists")
        self._sites[normalized.site_id] = normalized
        return deepcopy(normalized)

    def get(self, site_id: str) -> Site:
        site = self._sites.get(site_id)
        if site is None:
            raise SiteNotFoundError(f"Site '{site_id}' was not found")
        return deepcopy(site)

    def list(self) -> list[Site]:
        return [deepcopy(site) for site in self._sites.values()]

    def update(self, site_id: str, site: Site) -> Site:
        if site_id not in self._sites:
            raise SiteNotFoundError(f"Site '{site_id}' was not found")
        normalized = normalize_site_configuration(site)
        if normalized.site_id != site_id:
            raise ValueError("site_id in the path must match site_id in the payload")
        self._sites[site_id] = normalized
        return deepcopy(normalized)

    def delete(self, site_id: str) -> None:
        if site_id not in self._sites:
            raise SiteNotFoundError(f"Site '{site_id}' was not found")
        del self._sites[site_id]


def _demo_site() -> Site:
    """Build the single local-development demo site."""

    return Site.model_validate(
        {
            "site_id": "demo-site",
            "metadata": {
                "name": "Demo Community Microgrid",
                "timezone": "UTC",
                "description": "Local development site",
            },
            "location": {"latitude": 23.2, "longitude": 69.6},
            "energy_assets": {
                "assets": [
                    {
                        "asset_id": "solar-demo",
                        "name": "Demo solar array",
                        "asset_type": "solar",
                        "capacity_kw": 100,
                    },
                    {
                        "asset_id": "battery-demo",
                        "name": "Demo battery",
                        "asset_type": "battery",
                        "capacity_kwh": 250,
                        "max_charge_kw": 50,
                        "max_discharge_kw": 50,
                    },
                ]
            },
            "load_profile": {"peak_demand_kw": 120, "average_demand_kw": 50},
        }
    )


site_service = InMemorySiteService()
