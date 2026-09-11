# Phase 3 — Dispatch, Digital Twin & Ledger

> **Goal:** Something executes the plan and produces believable actual telemetry before real hardware
> exists, and the always-on shadow baseline turns "we saved diesel" into a measured number.
> **Status:** Not started — can run concurrently with Phases 2 and 4
> **Owner:** Split — Aarin (Task 3.1 digital twin, Task 3.2 dispatch wiring) · Dhruvi & Kavyan (Task 3.3 baseline ledger, Task 3.4 cost/emissions query, Task 3.5 alert rules)
> **Depends on:** Phase 1 (contracts frozen)
> **Demo milestone:** A savings figure appears on `GET /api/savings`, backed by two ledgers —
> optimized and baseline — run against identical realized conditions.
> **Key design refs:** [`ARCHITECTURE.md`](../architecture/ARCHITECTURE.md) §8 · [`DATA_MODEL.md`](../architecture/DATA_MODEL.md) §3–4 · `PRD.md` USP 1

## Overview

**You do not need Phase 2's advanced features.** Phase 1's single-shot optimizer is enough to build
and test the twin, the dispatch execution path, and the ledger against; when Phase 2 lands its
improvements, this phase's code needs no change, because both talk to the optimizer only through
`OptimizerPort`.

The invariant this phase exists to protect: **the baseline controller must see the exact same
realized weather and load the real (or simulated) system saw, not a separately sampled version of
"a similar day."** If the two ledgers ever diverge in what conditions they're each responding to, a
savings number stops being a measurement and becomes an argument.

---

## Tasks

### Task 3.1 — The digital twin

**Goal:** A physics-based simulator plausible enough to develop and demo against, and honest about
being one.

**Subtasks:**
- [ ] `dispatch_simulator.execute(decision) -> ActualState` implementing `DispatchPort`
- [ ] Battery physics: SoC evolves from the decision's charge/discharge power through the site's
      round-trip efficiency, exactly as the MILP models it — the twin must not silently use a different
      efficiency number than the optimizer assumed, or "the plan and the actual disagree" stops meaning
      "forecast error" and starts meaning "the two models don't even agree on physics"
- [ ] Diesel fuel burn from the same `fuel_curve` the optimizer uses
- [ ] Solar production from the forecast's GHI **plus Gaussian noise**, so realized solar deviates
      from the forecast the optimizer planned against — this is what makes forecast error a real,
      observable thing in a demo rather than a claim in the README
- [ ] Load similarly perturbed from its forecast

**Test plan:**
- Running the same decision through the twin twice with the same random seed reproduces the same
  actual state — determinism for reproducible demos and tests
- Over many runs, realized solar/load average to the forecast (the noise is unbiased) — an
  optimizer that appears to beat its own forecast systematically would mean the noise is biased, not
  that the optimizer is unusually good

**Design refs:** `ARCHITECTURE.md` §8.

---

### Task 3.2 — Dispatch execution wiring

**Goal:** The rolling loop's hour-0 decision actually reaches the twin, and the twin's result reaches
telemetry, every tick.

**Subtasks:**
- [ ] `rolling_horizon_service` calls `DispatchPort.execute()` and persists the result via
      `TelemetryRepository.record()`, badged `SIMULATED`
- [ ] `dispatch_log` row written in the same transaction as the telemetry row — a decision without its
      recorded execution, or an execution without its decision, is a bug the transaction boundary
      prevents
- [ ] The interface leaves room for `dispatch_hardware/` (`[DESIGN]`) without any change to
      `rolling_horizon_service` — verified by writing a second fake adapter in tests and confirming the
      service code is untouched

**Test plan:**
- A full tick (Phase 2's scheduler, Phase 1's optimizer, this task's twin) produces one plan row, one
  dispatch_log row and one telemetry row, all three timestamp-consistent

**Design refs:** `ARCHITECTURE.md` §2, §8.

---

### Task 3.3 — Shadow baseline runner

**Goal:** Every tick, the greedy controller runs against the identical realized conditions, in its
own ledger.

**Subtasks:**
- [ ] `baseline_service` reads the same `telemetry` row's realized solar/load (not a re-sampled or
      re-forecast version) and produces its own decision via `baseline_service.decide()` from Phase 0
- [ ] Persist to `baseline_telemetry` / `baseline_dispatch_log`, `source: "baseline"`, same shape as
      the real tables
- [ ] The baseline's own battery SoC evolves independently and *only* from its own decisions — the two
      controllers do not share a battery, they each simulate their own, because the comparison question
      is "what would this site look like if it had run the naive rule instead," not "what does the real
      battery do"

**Test plan:**
- For a fixed realized-weather scenario, the baseline's diesel-hours are always ≥ the optimized run's
  (this should hold on average across many scenarios — a single scenario where it doesn't is worth
  investigating, not silently accepted, since it would mean either the formulation or the baseline has
  a bug)
- `baseline_telemetry` and `telemetry` share the exact same `at` timestamps for a given tick — the
  comparison query in `DATA_MODEL.md` §4 depends on this join

**Design refs:** `DATA_MODEL.md` §3–4; `PRD.md` USP 1.

---

### Task 3.4 — Cost & emissions ledger

**Goal:** Fuel litres, cost and CO₂ are derived consistently on both sides of the comparison.

**Subtasks:**
- [ ] `fuel_price` and `co2_kg_per_liter` in site config
- [ ] The `GET /api/savings` query from `DATA_MODEL.md` §4, applying the identical conversion to both
      `telemetry` and `baseline_telemetry`
- [ ] A day-boundary test — the comparison must not leak a partial day's data across midnight in a way
      that makes one side look better by an accounting artefact

**Test plan:**
- Feeding identical diesel-kWh into both sides of the query yields identical cost/CO₂/litres — this
  is the sanity check that the conversion itself introduces no asymmetry

**Design refs:** `DATA_MODEL.md` §4; `API_CONTRACT.md` §5.

---

### Task 3.5 — Alert rules

**Goal:** The six alert types from `PRD.md` §11, correctly deduped and cooled down.

**Subtasks:**
- [ ] `LOW_SOC_RESERVE`, `DIESEL_REQUIRED_SOON`, `CRITICAL_LOAD_AT_RISK`, `SOLVER_FALLBACK_ACTIVE`,
      `FORECAST_STALE`, `BASELINE_DIVERGENCE`
- [ ] One lifecycle, one inbox, dedup per `(site_id, type, subject)`, 60s cooldown after resolve
- [ ] `raised_at` from the clock of the thing that raised it (optimizer tick or telemetry timestamp),
      `received_at` server-side
- [ ] `BASELINE_DIVERGENCE` — fires if the optimized run performs worse than baseline for a tick; this
      should never fire in practice and exists to catch a modelling bug, not to describe normal
      operation, so a firing of this alert during development is worth investigating before shipping

**Test plan:**
- Each of the six fires from its own inputs and no others
- The same condition twice creates one alert, not two
- Resolving then immediately re-triggering does not re-fire inside the cooldown

**Design refs:** `PRD.md` §11; `DATA_MODEL.md` §5.

---

## Verification (end of Phase 3)

- [ ] **CP-3.1** The twin's physics match the optimizer's assumed efficiency/fuel-curve exactly
- [ ] **CP-3.2** A full tick produces a consistent plan/dispatch_log/telemetry triple
- [ ] **CP-3.3** The baseline ledger runs every tick against identical realized conditions
- [ ] **CP-3.4** `GET /api/savings` returns a real, non-zero comparison for a multi-day backtest
- [ ] **CP-3.5** All six alert types fire correctly; dedup and cooldown hold

## Open issues / follow-ups

- [ ] `dispatch_hardware/` (real Modbus/MQTT integration) stays `[DESIGN]` until a hardware partner is
      identified — do not start it speculatively
- [ ] `BASELINE_DIVERGENCE` firing in a backtest is a stop-the-line signal for Phase 5, not something
      to suppress
