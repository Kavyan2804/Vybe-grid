"""Tests for site configuration normalization."""

from __future__ import annotations

import pytest

from src.schemas.sites import Site
from src.services.site_configuration import (
    SiteConfigurationNormalizationError,
    normalize_site_configuration,
)
from tests.test_site_schemas import valid_site_payload


def normalized_input() -> Site:
    return Site.model_validate(valid_site_payload())


def test_normalize_site_configuration_sets_stable_defaults() -> None:
    site = normalized_input()
    site.metadata.timezone = "UTC"
    site.location.latitude = 23.123456789
    site.energy_assets.assets[0].asset_id = " Solar Roof 01 "
    site.energy_assets.assets[0].name = "  Community   Solar  Array "

    normalized = normalize_site_configuration(site)

    assert normalized.site_id == "village-alpha"
    assert normalized.metadata.description == ""
    assert normalized.metadata.operator == ""
    assert normalized.metadata.timezone == "UTC"
    assert normalized.location.latitude == 23.123457
    assert normalized.location.elevation_m == 0.0
    assert normalized.energy_assets.assets[0].asset_id == "solar-roof-01"
    assert normalized.energy_assets.assets[0].name == "Community Solar Array"


@pytest.mark.parametrize(
    "mutate",
    [
        lambda s: setattr(s.energy_assets.assets[1], "asset_id", " Solar 01 "),
        lambda s: setattr(s.energy_assets.assets[0], "asset_id", "!!!"),
        lambda s: setattr(s.energy_assets.assets[1], "capacity_kwh", -1),
        lambda s: (
            setattr(s.energy_assets.assets[1], "min_soc_percentage", 80),
            setattr(s.energy_assets.assets[1], "max_soc_percentage", 20),
        ),
        lambda s: setattr(s.energy_assets.assets[1], "initial_soc_percentage", 95),
        lambda s: setattr(s.energy_assets.assets[2], "min_output_kw", 200),
        lambda s: setattr(s.load_profile, "critical_demand_kw", -1),
        lambda s: setattr(s.metadata, "timezone", "Not/A_Timezone"),
    ],
)
def test_invalid_configuration_is_rejected_with_clear_error(mutate) -> None:
    site = normalized_input()
    mutate(site)

    with pytest.raises(SiteConfigurationNormalizationError) as exc_info:
        normalize_site_configuration(site)

    assert exc_info.value.errors
