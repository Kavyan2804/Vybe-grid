# Simulator Contract

The Phase 3 simulator returns `ActualState` for one UTC, ISO-8601 timestamped interval. The initial
interval is one hour; power values are average `kW` over that interval and fuel, cost, and emissions
are interval totals.

Required fields: `site_id`, `recorded_at`, `solar_kw`, `battery_kw`, `diesel_kw`, `load_kw`,
`load_served_kw`, `unmet_load_kw`, `soc_pct`, `diesel_on`, and `source`. `simulation_run_id` is
optional and links a plan, simulation run, ledger records, and comparisons.

`ActualState.to_telemetry()` emits only the frozen telemetry schema. The ledger consumes the typed
result for fuel litres, cost, and emissions. Source names are `solar`, `battery`, `diesel`, and
`load`; telemetry provenance is `source: "simulator"` with the `SIMULATED` badge.

The simulator does not access a database. `ExecutionRepository` is the integration boundary: its
database implementation must write the hour-0 dispatch log and telemetry record in one transaction.
