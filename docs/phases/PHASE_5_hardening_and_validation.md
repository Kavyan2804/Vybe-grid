# Phase 5 — Hardening & Validation

> **Goal:** Prove the thing works under stress, not just on a calm day, and prove the one claim that
> must never be false: critical load is never dropped.
> **Status:** Not started
> **Depends on:** Phases 2, 3 and 4
> **Demo milestone:** A multi-scenario backtest report showing diesel/cost/CO₂ saved vs baseline
> across a clear day, a cloudy afternoon, a storm day and a load spike — with zero unmet critical load
> in every one of them.
> **Key design refs:** [`PRD.md`](../../PRD.md) §13, §15

## Overview

No new features in this phase. If a `[STRETCH]` item destabilizes anything checked in Phase 5, it is
reverted, not debugged under time pressure.

**Task 5.2 is the one that matters most.** Everything else in this phase supports the demo; this task
supports the product's central promise, and it needs to be a test the build fails loudly if it
regresses, not a thing someone remembers to check by eye.

---

## Tasks

### Task 5.1 — Multi-scenario backtest

**Subtasks:**
- [ ] Run every `tools/scenariogen` scenario (`clear-day`, `cloudy-afternoon`, `storm-day`,
      `load-spike`) through both the optimizer and the baseline, back to back, over a multi-day window
- [ ] Record diesel-hours, fuel, cost, CO₂ for both, and the delta, per scenario
- [ ] The `cloudy-afternoon` scenario is the one from the problem statement's own motivating example —
      confirm the optimized run visibly holds battery reserve through the morning and the baseline
      visibly doesn't

**Test plan:**
- The optimized run's diesel-hours are strictly less than the baseline's on every scenario except one
  engineered to make no difference possible (e.g. a day with so much sun neither controller ever
  needs diesel) — a scenario where baseline wins should not exist; if one appears, it's a formulation
  bug, not a data point to report around

**Checkpoint:** A written backtest report exists with a number and a method beside each claim.

---

### Task 5.2 — The critical-load proof

**Subtasks:**
- [ ] An automated test sweeping every backtest scenario, the fallback path, and at least one
      deliberately infeasible-for-flexible-load scenario, asserting `unmet_critical_kwh == 0` in every
      single hour of every single run
- [ ] The same assertion run against the fallback (greedy) path specifically, not only the MILP path —
      the guarantee has to hold regardless of which path produced the hour's decision
- [ ] A scenario engineered so that the *only* way to serve critical load is running diesel below its
      rated efficiency band — confirm the optimizer still does it rather than reporting infeasible

**Test plan:**
- Zero unmet critical load across every scenario in the suite, including the fallback and the
  deliberately extreme cases — this is a hard pass/fail, not a percentage

**Checkpoint:** **The one number that must never fail.** Recorded, not asserted from memory.

---

### Task 5.3 — Solver performance budget under rolling cadence

**Subtasks:**
- [ ] Measure solve latency for the full constraint set (min run-time, degradation, reserve margin if
      built) across every backtest scenario
- [ ] Confirm it stays well inside the tick interval (NFR-1) with margin for the fallback path's own
      decision time
- [ ] If it doesn't, warm-starting (deferred in Phase 2) becomes a Phase 5 task, not a demo-day
      surprise

**Test plan:**
- 95th-percentile solve time recorded across the backtest suite, with the solver/hardware it was
  measured on stated beside the number

**Checkpoint:** Solve latency measured and recorded, with margin against NFR-1's budget.

---

### Task 5.4 — Multi-day soak run

**Subtasks:**
- [ ] Run the full rolling loop continuously for several simulated days, crossing multiple midnight
      boundaries
- [ ] Confirm no state corruption at a day boundary — SoC continuity, no duplicate or missing plan
      rows, `dispatch_plans (site_id, tick_at)` uniqueness holds throughout
- [ ] Confirm the savings query (`DATA_MODEL.md` §4) produces sane, non-negative-in-the-wrong-direction
      numbers across the whole run

**Test plan:**
- N consecutive simulated days with no unplanned intervention; savings totals reconcile to the sum of
  their daily figures

**Checkpoint:** A multi-day soak completes with no state corruption.

---

### Task 5.5 — Acceptance sweep

**Subtasks:**
- [ ] Walk every `[BUILD]` requirement in `PRD.md` §10 and tick it in this document, by observation
- [ ] Any red item becomes the priority; `[STRETCH]` work stops until it's green
- [ ] Confirm every capability on any external-facing summary (deck, README) is marked
      built/stretch/designed and nothing appears as built that isn't

**Test plan:**
- Every `[BUILD]` row ticked by someone watching it work, not by assumption

**Checkpoint:** All `[BUILD]` requirements green.

---

## Verification (end of Phase 5)

- [ ] **CP-5.1** Backtest report exists, optimized beats baseline on every scenario where it's possible to
- [ ] **CP-5.2** Zero unmet critical load across every scenario, every path, proved by a test
- [ ] **CP-5.3** Solve latency measured and inside budget
- [ ] **CP-5.4** Multi-day soak completes with no state corruption
- [ ] **CP-5.5** Every `[BUILD]` requirement in `PRD.md` verified green

## Open issues / follow-ups

- [ ] Live-site tier validation against real hardware is out of scope for this phase — it is its own
      checkpoint, gated on a hardware integration existing at all (`PRD.md` §9)
- [ ] `BASELINE_DIVERGENCE` firing anywhere in the backtest suite blocks this phase's sign-off until
      explained
