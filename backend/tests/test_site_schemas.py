"""Tests for strongly typed site configuration schemas."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.schemas.sites import Site


def valid_site_payload() -> dict:
    return {
        "site_id": "village-alpha",
        "metadata": {"name": "Village Alpha", "timezone": "Asia/Kolkata"},
        "location": {"latitude": 23.2, "longitude": 69.6},
        "energy_assets": {
            "assets": [
                {"asset_id": "solar-01", "name": "Solar array", "asset_type": "solar",
                 "capacity_kw": 120},
                {"asset_id": "battery-01", "name": "Battery", "asset_type": "battery",
                 "capacity_kwh": 500, "max_charge_kw": 100, "max_discharge_kw": 100},
                {"asset_id": "diesel-01", "name": "Backup generator", "asset_type": "diesel",
                 "rated_power_kw": 150, "fuel_consumption_l_per_kwh": 0.28},
            ]
        },
        "load_profile": {"peak_demand_kw": 180, "average_demand_kw": 75},
    }


def test_site_accepts_nested_typed_assets() -> None:
    site = Site.model_validate(valid_site_payload())

    assert site.site_id == "village-alpha"
    assert site.energy_assets.assets[0].asset_type == "solar"
    assert site.energy_assets.assets[1].capacity_kwh == 500
    assert site.operating_constraints.reserve_percentage == 20


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("location", {"latitude": 91, "longitude": 69.6}),
        ("load_profile", {"peak_demand_kw": 50, "average_demand_kw": 75}),
        ("energy_assets", {"assets": [{
            "asset_id": "battery-01", "name": "Battery", "asset_type": "battery",
            "capacity_kwh": 500, "max_charge_kw": 100, "max_discharge_kw": 100,
            "min_soc_percentage": 90, "max_soc_percentage": 10,
        }]}),
    ],
)
def test_site_rejects_invalid_nested_configuration(field: str, value: dict) -> None:
    payload = valid_site_payload()
    payload[field] = value

    with pytest.raises(ValidationError):
        Site.model_validate(payload)


def test_site_rejects_unknown_asset_type() -> None:
    payload = valid_site_payload()
    payload["energy_assets"]["assets"][0]["asset_type"] = "hydrogen"

    with pytest.raises(ValidationError):
        Site.model_validate(payload)


def test_site_rejects_extra_fields() -> None:
    payload = valid_site_payload()
    payload["unexpected"] = True

    with pytest.raises(ValidationError):
        Site.model_validate(payload)
