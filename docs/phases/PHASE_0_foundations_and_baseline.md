# Phase 0 — Foundations & Baseline

> **Goal:** The site model exists as a versioned config, a real weather forecast can be fetched, the
> literal greedy controller from the problem statement runs and produces a number, and every shared
> data shape is frozen before anything downstream depends on it.
> **Status:** Not started
> **Depends on:** —
> **Demo milestone:** Given one day of forecast and a site config, the greedy controller produces a
> 24-hour dispatch decision sequence and prints total diesel-hours, fuel litres and cost.
> **Key design refs:** [`PRD.md`](../../PRD.md) §4, §8.1–8.3 · [`ARCHITECTURE.md`](../architecture/ARCHITECTURE.md)

## Overview

Nothing here is optional groundwork — it is the thing everything else is measured against. The
baseline controller built in this phase (Task 0.3) is not a throwaway; it runs for the life of the
product as the permanent comparison arm behind every savings number (`PRD.md` USP 1). Get its
behaviour right here, because Phase 3 depends on it being an honest, literal implementation of "solar
first, then battery, then diesel," not a strawman tuned to lose.

---

## Tasks

### Task 0.1 — Site & device model

**Goal:** A microgrid site is fully described by one reviewable file.

**Subtasks:**
- [ ] Define `Site`, `Battery`, `DieselGenerator`, `Load` entities in `optimizer/domain/entities.py`
- [ ] `Battery`: `capacity_kwh`, `max_charge_kw`, `max_discharge_kw`, `round_trip_efficiency`,
      `degradation_cost_per_kwh_cycled`, `soc_min_pct`, `soc_max_pct`
- [ ] `DieselGenerator`: `min_load_kw`, `max_load_kw`, `fuel_curve` (litres/kWh at min and max load,
      linearly interpolated), `start_cost`, `min_uptime_h`, `min_downtime_h`
- [ ] `Load`: `critical_kw` profile and `flexible_kw` profile, both as an hourly shape
- [ ] `site-config.schema.json` in `packages/contracts/` validating the YAML shape
- [ ] One example site, `optimizer/sites/example-site.yml`, with plausible rural-microgrid numbers

**Test plan:**
- A malformed site YAML fails schema validation with a message naming the field
- Loading `example-site.yml` produces a `Site` entity with every field populated, no silent defaults

**Design refs:** `ARCHITECTURE.md` §1; `PRD.md` §8.1.

---

### Task 0.2 — Forecast ingestion

**Goal:** Real solar and load forecasts can be fetched for a site, with an honest fallback when they
can't.

**Subtasks:**
- [ ] `ForecastPort` interface in `optimizer/domain/ports.py`
- [ ] `OpenMeteoForecastAdapter` — hourly GHI, cloud cover, temperature for the next 24h
- [ ] A synthetic load-profile generator (weekday/weekend day-shape + noise) standing in for a real
      smart-meter feed — badged `FORECAST` with `source: "synthetic"`, never presented as measured
- [ ] Persistence-fallback: if the live fetch fails, reuse the last successful forecast, `stale: true`
- [ ] NASA POWER client for historical solar data, used only for backtesting (Phase 5), never live

**Test plan:**
- A live fetch produces a 24-entry hourly series with no gaps
- Killing network access mid-fetch falls back to the last forecast and marks it `stale: true`, never
  silently reused as fresh

**Design refs:** `PRD.md` §8.2, §15 (weather API outage).

---

### Task 0.3 — The baseline greedy controller

**Goal:** The literal "solar first, then battery, then diesel" rule, implemented exactly as described
in the problem statement — no lookahead, no forecast, decides one hour at a time from the current
state alone.

**Subtasks:**
- [ ] `baseline_service.decide(state, current_hour_load) -> DispatchDecision` — no `Forecast` argument
      at all, by construction, so it cannot accidentally gain foresight
- [ ] Rule: serve load from solar first; any solar surplus charges the battery up to its limits; any
      shortfall discharges the battery down to `soc_min`; only if both are exhausted does diesel start,
      at the load required (respecting `min_load_kw`)
- [ ] Diesel, once started, keeps running until load can be served by solar+battery again (a literal
      reading of "when both run out," not an optimized on/off schedule)
- [ ] Unit tests reproducing the exact motivating example from the problem statement: a cloudy
      afternoon after a battery fully charged by late morning should show diesel running the evening
      peak under this controller

**Test plan:**
- Given a synthetic "sunny morning, cloudy afternoon" day, the controller's battery is full by noon
  and diesel runs the evening peak — this is the failure mode the whole product exists to fix, and it
  must be reproducible on demand, not just asserted in prose
- The controller never reads a `Forecast` object — enforced by the function signature, not a comment

**Design refs:** `PRD.md` §1 ("why the naive approach fails"), §8.3.

---

### Task 0.4 — Contracts freeze

**Goal:** Every shape another phase will build against exists and validates, before anyone builds
against it.

**Subtasks:**
- [ ] `packages/contracts/events/*.schema.json` — `forecast`, `dispatch_plan`, `dispatch_decision`,
      `telemetry`, `alert`
- [ ] `packages/contracts/site-config.schema.json` (from Task 0.1)
- [ ] A schema-consistency test: every field `API_CONTRACT.md` documents exists in a schema, and vice
      versa
- [ ] Announce the freeze — additive changes only from here on (`REPO_STRUCTURE.md` §6)

**Test plan:**
- Every schema parses as valid JSON Schema
- A forecast/telemetry/plan object missing a required field fails validation

**Design refs:** `docs/architecture/API_CONTRACT.md`; `docs/architecture/DATA_MODEL.md`.

---

### Task 0.5 — Solver pin & smoke test

**Goal:** Know the solver works, and how fast, before building a formulation on top of it.

**Subtasks:**
- [ ] Pyomo 6.x + HiGHS installed and pinned in `optimizer/pyproject.toml`
- [ ] A trivial LP (2 variables, 1 constraint) solved end to end through `PyomoHighsOptimizerAdapter`'s
      scaffolding
- [ ] Measure and record solve latency for a toy 24-variable problem, as a sanity floor for NFR-1

**Test plan:**
- The trivial LP returns the known-correct optimum
- Solve latency is recorded in `docs/agent/memory.md` as the first real number this project has

**Design refs:** `PRD.md` §4 (tech stack), §14 (solver decision).

---

### Task 0.6 — `tools/scenariogen/` — unblock the other lanes

**Goal:** Schema-valid forecasts and telemetry on demand, so Phases 2–4 don't wait on each other.

**Subtasks:**
- [ ] `tools/scenariogen/run.py` reads a scenario file (e.g. "cloudy afternoon", "storm day", "load
      spike") and emits schema-valid forecast/telemetry fixtures
- [ ] Every emitted object validates against the canonical schema before being written
- [ ] A README stating the line: scenarios are **authored**, never captured from a real optimizer run
      and replayed as if live

**Test plan:**
- Every bundled scenario validates against its schema
- `verify_no_demo_scenario.sh` fails if anything under `optimizer/infrastructure` references
  `scenariogen`

**Design refs:** `REPO_STRUCTURE.md` §7.

---

## Verification (end of Phase 0)

- [ ] **CP-0.1** `example-site.yml` loads into a valid `Site` entity; the schema rejects a malformed one
- [ ] **CP-0.2** A live forecast fetch succeeds; a simulated outage falls back and marks `stale: true`
- [ ] **CP-0.3** The baseline controller reproduces the "cloudy afternoon → evening diesel" failure mode from a synthetic day
- [ ] **CP-0.4** Every contract schema is valid and cross-checked against `API_CONTRACT.md`
- [ ] **CP-0.5** The solver smoke test passes and its latency is recorded
- [ ] **CP-0.6** Every bundled `scenariogen` scenario validates

## Open issues / follow-ups

- [ ] Real per-site fuel price and emission-factor sourcing is a config value for now — a live pricing
      feed is `[DESIGN]`
- [ ] The synthetic load profile is a placeholder for a real smart-meter feed; do not tune it to match
      a specific demo number — that would defeat Phase 5's honesty requirement
