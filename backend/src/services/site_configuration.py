"""Normalization and business validation for site configurations."""

from __future__ import annotations

import re
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from src.errors import ConfigurationValidationError
from src.schemas.sites import BatteryAsset, DieselGenerator, Site

_COMMON_TIMEZONES = {
    "Asia/Kolkata",
    "Asia/Colombo",
    "Asia/Dhaka",
    "Asia/Kathmandu",
    "Asia/Singapore",
    "Asia/Tokyo",
    "Australia/Sydney",
    "Europe/Berlin",
    "Europe/London",
    "Pacific/Auckland",
    "America/Chicago",
    "America/Los_Angeles",
    "America/New_York",
}


class SiteConfigurationNormalizationError(ConfigurationValidationError):
    """Raised when a site cannot be converted to the internal format."""

    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__(
            "Site configuration normalization failed: " + "; ".join(errors),
            [{"message": error} for error in errors],
        )


def _normalize_identifier(value: str) -> str:
    """Convert an identifier to a stable lowercase hyphen-separated value."""

    normalized = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
    return normalized


def _normalize_name(value: str) -> str:
    """Trim and collapse whitespace without changing the display casing."""

    return " ".join(value.split())


def normalize_site_configuration(site: Site) -> Site:
    """Validate and normalize a validated site into the backend's internal format.

    The returned model is independent from the input and has stable identifiers,
    canonical timezone data, rounded coordinates, and explicit optional defaults.
    """

    errors: list[str] = []
    assets: list[dict[str, Any]] = []
    normalized_ids: set[str] = set()

    for index, asset in enumerate(site.energy_assets.assets):
        asset_data = asset.model_dump()
        asset_id = _normalize_identifier(asset.asset_id)
        if not asset_id:
            errors.append(f"energy_assets.assets[{index}].asset_id must contain letters or digits")
        elif asset_id in normalized_ids:
            errors.append(f"energy_assets.assets[{index}].asset_id '{asset_id}' is not unique")
        normalized_ids.add(asset_id)

        asset_data["asset_id"] = asset_id
        asset_data["name"] = _normalize_name(asset.name)
        if not asset_data["name"]:
            errors.append(f"energy_assets.assets[{index}].name cannot be blank")

        if hasattr(asset, "capacity_kwh") and asset.capacity_kwh < 0:
            errors.append(f"energy_assets.assets[{index}].capacity_kwh must be non-negative")
        if hasattr(asset, "capacity_kw") and asset.capacity_kw < 0:
            errors.append(f"energy_assets.assets[{index}].capacity_kw must be non-negative")
        if isinstance(asset, BatteryAsset):
            if asset.min_soc_percentage >= asset.max_soc_percentage:
                errors.append(
                    f"energy_assets.assets[{index}].min_soc_percentage must be lower than "
                    "max_soc_percentage"
                )
            if not asset.min_soc_percentage <= asset.initial_soc_percentage <= asset.max_soc_percentage:
                errors.append(
                    f"energy_assets.assets[{index}].initial_soc_percentage must be within "
                    "the allowed SOC range"
                )
        if isinstance(asset, DieselGenerator):
            if asset.min_output_kw < 0 or asset.rated_power_kw < 0:
                errors.append(
                    f"energy_assets.assets[{index}] diesel minimum and maximum power must be "
                    "non-negative"
                )
            if asset.min_output_kw > asset.rated_power_kw:
                errors.append(
                    f"energy_assets.assets[{index}].min_output_kw cannot exceed rated_power_kw"
                )
        assets.append(asset_data)

    load = site.load_profile
    for field in ("peak_demand_kw", "average_demand_kw", "critical_demand_kw"):
        if getattr(load, field) < 0:
            errors.append(f"load_profile.{field} must be non-negative")

    try:
        timezone = "UTC" if site.metadata.timezone.upper() == "UTC" else ZoneInfo(
            site.metadata.timezone
        ).key
    except (ZoneInfoNotFoundError, ValueError):
        if site.metadata.timezone in _COMMON_TIMEZONES:
            timezone = site.metadata.timezone
        else:
            errors.append(
                f"metadata.timezone '{site.metadata.timezone}' is not a valid IANA timezone"
            )
            timezone = site.metadata.timezone

    if errors:
        raise SiteConfigurationNormalizationError(errors)

    data = site.model_dump()
    data["site_id"] = _normalize_identifier(site.site_id)
    data["metadata"]["name"] = _normalize_name(site.metadata.name)
    data["metadata"]["timezone"] = timezone
    data["metadata"]["description"] = _normalize_name(site.metadata.description or "")
    data["metadata"]["operator"] = _normalize_name(site.metadata.operator or "")
    data["location"]["latitude"] = round(site.location.latitude, 6)
    data["location"]["longitude"] = round(site.location.longitude, 6)
    data["location"]["elevation_m"] = site.location.elevation_m or 0.0
    data["energy_assets"]["assets"] = assets
    return Site.model_validate(data)
