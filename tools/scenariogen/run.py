import sys
import argparse
import yaml
import json
import os
import jsonschema
from datetime import datetime, timedelta, timezone

CONTRACTS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'packages', 'contracts', 'events'))

def load_schema(name):
    schema_path = os.path.join(CONTRACTS_DIR, f"{name}.schema.json")
    with open(schema_path, 'r') as f:
        return json.load(f)

def validate_payload(payload, schema_name):
    schema = load_schema(schema_name)
    jsonschema.validate(instance=payload, schema=schema)

def generate_forecast(scenario):
    now = datetime.now(timezone.utc)
    entries = []
    
    for h in range(24):
        solar = 5.0
        load = 2.0
        ghi = 800.0
        cc = 0.0
        
        name = scenario.get("name", "")
        if "cloudy_afternoon" in name and 12 <= h <= 18:
            solar = 1.0
            cc = 80.0
        elif "storm_day" in name:
            solar = 0.5
            cc = 100.0
        elif "load_spike" in name and 14 <= h <= 17:
            load = 8.0
            
        entries.append({
            "hour": h,
            "solar_kw": solar,
            "load_kw": load,
            "ghi_wm2": ghi,
            "cloud_cover_pct": cc,
            "temperature_c": 25.0
        })

    forecast = {
        "site_id": "site-scenario",
        "issued_at": now.isoformat(),
        "horizon_start": now.isoformat(),
        "horizon_end": (now + timedelta(hours=24)).isoformat(),
        "source": "scenariogen",
        "stale": False,
        "entries": entries
    }
    
    validate_payload(forecast, "forecast")
    return forecast

def generate_telemetry(scenario):
    now = datetime.now(timezone.utc)
    telemetry = {
        "site_id": "site-scenario",
        "recorded_at": now.isoformat(),
        "solar_kw": 5.0,
        "battery_kw": 1.0,
        "diesel_kw": 0.0,
        "load_kw": 2.0,
        "soc_pct": 80.0,
        "diesel_on": False,
        "source": "simulator"
    }
    
    validate_payload(telemetry, "telemetry")
    return telemetry

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("scenario_file", help="Path to scenario YAML")
    parser.add_argument("--outdir", default=".", help="Output directory")
    args = parser.parse_args()

    with open(args.scenario_file, 'r') as f:
        scenario = yaml.safe_load(f)
        
    forecast = generate_forecast(scenario)
    telemetry = generate_telemetry(scenario)
    
    out_f = os.path.join(args.outdir, f"forecast_{scenario['name']}.json")
    out_t = os.path.join(args.outdir, f"telemetry_{scenario['name']}.json")
    
    with open(out_f, 'w') as f:
        json.dump(forecast, f, indent=2)
    with open(out_t, 'w') as f:
        json.dump(telemetry, f, indent=2)
        
    print(f"Generated and validated payloads for {scenario['name']}")

if __name__ == "__main__":
    main()
