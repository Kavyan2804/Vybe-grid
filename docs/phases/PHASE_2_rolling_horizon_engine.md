# Phase 2 — Rolling Horizon Engine

> **Goal:** The optimizer re-solves on a schedule, corrects itself from measured state rather than its
> own prior prediction, models diesel run-time and battery degradation properly, and degrades safely
> when the solver can't produce an answer in time.
> **Status:** Complete pending owner review
> **Owner:** Aarin (ML) — Dhruvi & Kavyan on call to support the Phase 1 repositories this phase calls into, no new backend code expected
> **Depends on:** Phase 1 (contracts frozen; a single solve already works)
> **Demo milestone:** The plan visibly changes between two consecutive ticks as the forecast updates,
> and killing the solver for one tick produces a logged fallback decision instead of a crash.
> **Key design refs:** [`ARCHITECTURE.md`](../architecture/ARCHITECTURE.md) §3, §4, §6, §7

## Overview

**You do not need Phase 3 or 4.** Drive this against `tools/scenariogen`'s telemetry fixtures
standing in for the digital twin, and check your work against the `dispatch_plans` table directly.
Real telemetry arrives in Phase 3 and should require no change here — that is what the `ForecastPort`
/ `TelemetryRepository` boundary in `ARCHITECTURE.md` §2 is for.

The single easiest mistake in this phase is covered in `ARCHITECTURE.md` §4 and worth repeating: the
next tick's starting SoC comes from `TelemetryRepository.latest_soc()`, **never** from the previous
plan's own predicted trajectory. Get this wrong and the loop stops correcting for forecast error,
which is the entire premise of the product.

---

## Tasks

### Task 2.1 — The rolling scheduler

**Goal:** A tick fires on a schedule and runs the full sequence in `ARCHITECTURE.md` §3.

**Subtasks:**
- [x] APScheduler job, configurable interval (default 1h), one job per active site
- [x] Each tick: fetch forecast → read latest telemetry → solve → persist plan → hand hour 0 to
      `DispatchPort` → record the result
- [x] A `--fast-forward` mode that compresses a simulated day into minutes, for backtesting and demo
      purposes, driven off `scenariogen` fixtures rather than the real clock

**Test plan:**
- Two consecutive ticks against a changing forecast produce two different plans, both persisted
- A tick's `starting_soc_kwh` always matches the most recent `telemetry` row, never the previous
  plan's `series[1].soc_kwh`

**Design refs:** `ARCHITECTURE.md` §3, §4.

---

### Task 2.2 — Diesel run-time constraints and start cost

**Goal:** Diesel behaves like a real generator, not a switch that can flip every hour.

**Subtasks:**
- [x] Minimum run-time and minimum off-time constraints (standard MILP up/down-time formulation)
- [x] Start cost applied only on a `0 → 1` transition of `diesel_on`
- [x] A regression scenario: a borderline load pattern that would otherwise start/stop diesel twice
      inside three hours must now hold it on for the full minimum run-time instead

**Test plan:**
- No plan in the test suite starts diesel for fewer consecutive hours than `min_uptime_h`
- Start cost appears in `objective_cost` exactly once per genuine start, not per hour diesel is on

**Design refs:** `ARCHITECTURE.md` §5; `PRD.md` FR-O5.

---

### Task 2.3 — Battery degradation cost, measured not assumed

**Goal:** The objective genuinely trades off diesel/curtailment against battery wear, rather than
cycling the battery for free.

**Subtasks:**
- [x] `degradation_cost_per_kwh_cycled` applied to both charge and discharge throughput in the
      objective (`ARCHITECTURE.md` §5)
- [x] A comparison test: with degradation cost set to zero, the optimizer cycles the battery more
      aggressively than with a realistic cost — if it doesn't, the term isn't wired into the objective
      correctly, whatever the rest of the plan looks like

**Test plan:**
- Sweeping `degradation_cost_per_kwh_cycled` from 0 to a realistic value strictly reduces total
  battery throughput in the resulting plan, holding everything else constant

**Design refs:** `ARCHITECTURE.md` §5; `PRD.md` FR-O4.

---

### Task 2.4 — Fallback path

**Goal:** A solver timeout or infeasibility never stops the site from getting a dispatch decision.

**Subtasks:**
- [x] Solve timeout budget (default 20s, leaving margin inside NFR-1's 30s tick budget)
- [x] On timeout or `infeasible`, raise `SOLVER_FALLBACK_ACTIVE` and call the same greedy rule
      `baseline_service` runs, for this tick's real dispatch only (`ARCHITECTURE.md` §7)
- [x] The fallback decision is persisted through the identical `dispatch_plans`/`dispatch_log` path,
      `source: "fallback"`, so it is auditable rather than a special case invisible to the ledger

**Test plan:**
- Forcing an infeasible scenario (e.g. critical load spiking past total capacity in the flexible
  portion) still produces a persisted decision and an alert, never an unhandled exception
- Critical load is unmet in **zero** fallback-path test cases, matching the MILP path exactly

**Design refs:** `ARCHITECTURE.md` §7; `PRD.md` NFR-3, USP 3.

---

### Task 2.5 — Forecast-uncertainty reserve margin `[STRETCH]`

**Goal:** Battery reserve scales with forecast confidence rather than a fixed safety margin.

**Subtasks:**
- [x] `ForecastPort` returns a P10/P50/P90 solar band when the provider supports it
- [x] `soc_min` for the current tick's near-term hours is raised proportional to the band's spread
- [x] A comparison scenario: a wide-spread (uncertain) forecast produces a materially larger held-back
      reserve than a narrow one, for the same P50 solar value

**Test plan:**
- Reserve margin is monotonic in forecast spread, holding P50 fixed

**Design refs:** `ARCHITECTURE.md` §6; `PRD.md` FR-O8.

---

### Task 2.6 — Explainability `[STRETCH]`

**Goal:** A one-line, plain-language reason per hour's decision.

**Subtasks:**
- [x] Read the solver's binding constraints / shadow prices for each hour
- [x] Map the dominant binding constraint to a short template — "held back battery to catch forecast
      solar surplus at hour N," "diesel minimum run-time in effect," etc. — filled with real numbers
      from that solve, not a static string
- [x] Attach `reason: string` to each hour in the plan's `series`

**Test plan:**
- A scenario engineered to bind on the battery-reserve constraint produces a reason mentioning
  reserve/surplus, not a generic fallback string

**Design refs:** `PRD.md` FR-O9, USP 5.

---

## Verification (end of Phase 2)

- [x] **CP-2.1** The scheduler fires on interval and produces a new, different plan each tick against
      a changing forecast
- [x] **CP-2.2** A tick's starting SoC always comes from telemetry, verified by a test that would fail
      if the previous plan's own trajectory were used instead
- [x] **CP-2.3** No plan violates diesel minimum run-time / off-time
- [x] **CP-2.4** Battery throughput responds monotonically to degradation cost
- [x] **CP-2.5** A forced solver failure produces a fallback decision and an alert, with critical load
      still fully served
- [x] `[STRETCH]` CP-2.6 Reserve margin responds to forecast spread
- [x] `[STRETCH]` CP-2.7 Explanations reference the actual binding constraint

## Open issues / follow-ups

- [ ] Warm-starting the solver from the previous plan's shifted trajectory (FR-O5) is deferred until
      NFR-1's latency is measured under the full constraint set — optimize once it's known to be needed
- [ ] `min_uptime_h` / `min_downtime_h` values are placeholders in `example-site.yml` until a real
      generator spec sheet is available
