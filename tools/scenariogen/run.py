import argparse
import json
import os
import time
from datetime import datetime, timedelta, timezone

import jsonschema
import yaml


CONTRACTS_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "packages", "contracts", "events")
)


def load_schema(name):
    schema_path = os.path.join(CONTRACTS_DIR, f"{name}.schema.json")
    with open(schema_path, "r") as f:
        return json.load(f)


def validate_payload(payload, schema_name):
    schema = load_schema(schema_name)
    jsonschema.validate(instance=payload, schema=schema)


def _scenario_name(scenario):
    return str(scenario.get("name", "")).replace("-", "_")


def _hour_values(name, hour):
    solar = 5.0
    load = 2.0
    ghi = 800.0
    cloud_cover = 0.0

    if name == "clear_day":
        if hour < 6 or hour > 18:
            solar = 0.0
            ghi = 0.0
        elif hour in (6, 18):
            solar = 1.5
            ghi = 250.0
        elif hour in (7, 17):
            solar = 4.0
            ghi = 600.0
        else:
            solar = 8.0
            ghi = 950.0
    elif name == "cloudy_afternoon" and 12 <= hour <= 18:
        solar = 1.0
        ghi = 180.0
        cloud_cover = 80.0
    elif name == "storm_day":
        solar = 0.5
        ghi = 90.0
        cloud_cover = 100.0
    elif name == "load_spike" and 14 <= hour <= 17:
        load = 8.0

    return solar, load, ghi, cloud_cover


def generate_forecast(scenario):
    now = datetime.now(timezone.utc)
    name = _scenario_name(scenario)
    entries = []

    for hour in range(24):
        solar, load, ghi, cloud_cover = _hour_values(name, hour)
        entries.append(
            {
                "hour": hour,
                "solar_kw": solar,
                "load_kw": load,
                "ghi_wm2": ghi,
                "cloud_cover_pct": cloud_cover,
                "temperature_c": 25.0,
            }
        )

    forecast = {
        "site_id": "site-scenario",
        "issued_at": now.isoformat(),
        "horizon_start": now.isoformat(),
        "horizon_end": (now + timedelta(hours=24)).isoformat(),
        "source": "scenariogen",
        "stale": False,
        "entries": entries,
    }

    validate_payload(forecast, "forecast")
    return forecast


def generate_telemetry(scenario):
    now = datetime.now(timezone.utc)
    name = _scenario_name(scenario)
    solar, load, _, _ = _hour_values(name, now.hour)
    telemetry = {
        "site_id": "site-scenario",
        "recorded_at": now.isoformat(),
        "solar_kw": solar,
        "battery_kw": 0.0,
        "diesel_kw": 0.0,
        "load_kw": load,
        "soc_pct": 80.0,
        "diesel_on": False,
        "source": "simulator",
    }

    validate_payload(telemetry, "telemetry")
    return telemetry


def write_payloads(scenario, outdir):
    os.makedirs(outdir, exist_ok=True)
    forecast = generate_forecast(scenario)
    telemetry = generate_telemetry(scenario)
    name = _scenario_name(scenario)

    out_forecast = os.path.join(outdir, f"forecast_{name}.json")
    out_telemetry = os.path.join(outdir, f"telemetry_{name}.json")

    with open(out_forecast, "w") as f:
        json.dump(forecast, f, indent=2)
    with open(out_telemetry, "w") as f:
        json.dump(telemetry, f, indent=2)

    return forecast, telemetry


def emit_payloads(scenario):
    forecast = generate_forecast(scenario)
    telemetry = generate_telemetry(scenario)
    print(json.dumps({"forecast": forecast, "telemetry": telemetry}, indent=2))


def load_scenario(path):
    with open(path, "r") as f:
        return yaml.safe_load(f)


def validate_scenario(scenario):
    generate_forecast(scenario)
    generate_telemetry(scenario)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("scenario_file", help="Path to scenario YAML")
    parser.add_argument("--outdir", default=".", help="Output directory")
    parser.add_argument("--dry-run", action="store_true", help="Validate and print without files")
    parser.add_argument("--validate", action="store_true", help="Validate generated event payloads")
    parser.add_argument("--loop", action="store_true", help="Continuously emit generated payloads")
    parser.add_argument("--iterations", type=int, default=0, help="Loop iterations; 0 runs forever")
    parser.add_argument("--interval-seconds", type=float, default=5.0, help="Delay between loop emits")
    args = parser.parse_args()

    scenario = load_scenario(args.scenario_file)
    name = _scenario_name(scenario)

    if args.loop:
        iteration = 0
        while args.iterations == 0 or iteration < args.iterations:
            emit_payloads(scenario)
            iteration += 1
            if args.iterations == 0 or iteration < args.iterations:
                time.sleep(args.interval_seconds)
        return

    if args.validate:
        validate_scenario(scenario)

    if args.dry_run:
        emit_payloads(scenario)
        return

    write_payloads(scenario, args.outdir)
    print(f"Generated and validated payloads for {name}")


if __name__ == "__main__":
    main()
