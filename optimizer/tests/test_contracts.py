import os
import json
import pytest
import re
from jsonschema import validate, ValidationError, Draft202012Validator

CONTRACTS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'packages', 'contracts', 'events'))

def get_schema(name):
    with open(os.path.join(CONTRACTS_DIR, f"{name}.schema.json"), 'r') as f:
        return json.load(f)

def test_all_schemas_parse():
    for f in os.listdir(CONTRACTS_DIR):
        if f.endswith('.schema.json'):
            schema = get_schema(f.split('.')[0])
            Draft202012Validator.check_schema(schema)

def test_forecast_missing_field_fails():
    schema = get_schema('forecast')
    # Valid payload, missing 'source'
    payload = {
        "site_id": "s1", "issued_at": "2026-01-01T00:00:00Z",
        "horizon_start": "2026-01-01T00:00:00Z", "horizon_end": "2026-01-02T00:00:00Z",
        "stale": False, "entries": [
            {"hour": i, "solar_kw": 0, "load_kw": 0, "ghi_wm2": 0, "cloud_cover_pct": 0, "temperature_c": 20}
            for i in range(24)
        ]
    }
    with pytest.raises(ValidationError):
        validate(instance=payload, schema=schema)

def test_dispatch_decision_missing_field_fails():
    schema = get_schema('dispatch_decision')
    payload = {"hour": 0, "solar_kw": 10}
    with pytest.raises(ValidationError):
        validate(instance=payload, schema=schema)

def test_telemetry_missing_field_fails():
    schema = get_schema('telemetry')
    payload = {"site_id": "s1", "solar_kw": 5}
    with pytest.raises(ValidationError):
        validate(instance=payload, schema=schema)

def test_alert_missing_field_fails():
    schema = get_schema('alert')
    payload = {"id": "1"}
    with pytest.raises(ValidationError):
        validate(instance=payload, schema=schema)

def test_valid_forecast_passes():
    schema = get_schema('forecast')
    payload = {
        "site_id": "s1", "issued_at": "2026-01-01T00:00:00Z",
        "horizon_start": "2026-01-01T00:00:00Z", "horizon_end": "2026-01-02T00:00:00Z",
        "source": "scenariogen", "stale": False,
        "entries": [
            {"hour": i, "solar_kw": 0, "load_kw": 0, "ghi_wm2": 0, "cloud_cover_pct": 0, "temperature_c": 20}
            for i in range(24)
        ]
    }
    validate(instance=payload, schema=schema)

def test_valid_dispatch_plan_passes():
    schema = get_schema('dispatch_plan')
    decision_schema = get_schema('dispatch_decision')
    schema['properties']['decisions']['items'] = decision_schema 
    
    payload = {
        "site_id": "s1", "forecast_id": "f1", "created_at": "2026-01-01T00:00:00Z",
        "solver_status": "optimal", "solve_time_ms": 100, "fallback_used": False,
        "decisions": [
            {
                "hour": i, "solar_kw": 0, "battery_kw": 0, "diesel_kw": 0, "load_kw": 0,
                "diesel_on": False, "soc_pct": 50, "badges": ["SIMULATED"]
            } for i in range(24)
        ]
    }
    validate(instance=payload, schema=schema)


def test_api_contract_mentions_every_canonical_schema_field():
    contract_path = os.path.abspath(
        os.path.join(os.path.dirname(__file__), '..', '..', 'docs', 'architecture', 'API_CONTRACT.md')
    )
    with open(contract_path, 'r') as f:
        contract = f.read()

    aliases = {
        'ghi_wm2': 'ghi_w_m2',
        'temperature_c': 'temperature',
        'recorded_at': 'at',
        'battery_kw': 'batt_kw',
        'created_at': 'raised_at',
        'subject': 'title',
        'status': 'state',
        'decisions': 'series',
        'solve_time_ms': 'solve_ms',
        'solar_kw': 'solar_used_kw',
        'horizon_start': 'issued_at',
        'horizon_end': 'range',
        'entries': 'series',
    }
    for filename in os.listdir(CONTRACTS_DIR):
        if not filename.endswith('.schema.json'):
            continue
        schema = get_schema(filename.split('.')[0])
        for field in schema.get('properties', {}):
            assert re.search(rf'\b{re.escape(aliases.get(field, field))}\b', contract), (
                f"{filename} field '{field}' is not documented in API_CONTRACT.md"
            )
