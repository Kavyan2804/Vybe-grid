import json
from unittest.mock import Mock, patch

import pytest

from optimizer.domain.entities import load_site_from_yaml
from optimizer.infrastructure.forecast_openmeteo.nasa_power import NasaPowerHistoricalAdapter


def test_malformed_site_names_field(tmp_path):
    malformed = tmp_path / "malformed.yml"
    malformed.write_text("name: incomplete-site\n")
    with pytest.raises(ValueError, match="latitude"):
        load_site_from_yaml(str(malformed))


def test_nasa_power_historical_adapter_parses_ordered_values():
    site = load_site_from_yaml("optimizer/sites/example-site.yml")
    response = Mock()
    response.json.return_value = {
        "properties": {
            "parameter": {
                "ALLSKY_SFC_SW_DWN": {"2026091201": 1.5, "2026091200": 0.0}
            }
        }
    }
    response.raise_for_status.return_value = None
    with patch("httpx.get", return_value=response) as get:
        values = NasaPowerHistoricalAdapter().fetch_hourly_irradiance(
            site, "2026-09-12", "2026-09-12"
        )
    assert values == [0.0, 1.5]
    get.assert_called_once()


def test_nasa_power_rejects_invalid_date_range():
    site = load_site_from_yaml("optimizer/sites/example-site.yml")
    with pytest.raises(ValueError, match="on or before"):
        NasaPowerHistoricalAdapter().fetch_hourly_irradiance(
            site, "2026-09-13", "2026-09-12"
        )
