# Phase 1 — The Loop

> **Goal:** One forecast, one MILP solve, one chart on screen. Prove the pipe end to end with the
> thinnest possible slice before adding the rolling mechanism.
> **Status:** Not started
> **Owner:** ALL — Aarin (MILP v1, scenariogen, infra) · Dhruvi & Kavyan (DB, migrations, triggered-solve API) · Yashita (dashboard shell, badges, first chart)
> **Depends on:** Phase 0
> **Demo milestone:** A 24-hour dispatch plan, solved from a real forecast and a real site config,
> renders as a chart in a browser.
> **Key design refs:** [`ARCHITECTURE.md`](../architecture/ARCHITECTURE.md) §5 · [`API_CONTRACT.md`](../architecture/API_CONTRACT.md) · [`DATA_MODEL.md`](../architecture/DATA_MODEL.md)

## Overview

This phase does two things and the order matters. **First, it finishes freezing the contracts** —
`API_CONTRACT.md` and `DATA_MODEL.md` — so Phases 2, 3 and 4 can start the moment this merges without
waiting on each other. **Second, it proves the pipe** with a single, non-rolling solve: garbage
numbers are fine here, a single feasible plan reaching a browser is not.

---

## Tasks

### Task 1.1 — MILP formulation v1

**Goal:** The formulation in `ARCHITECTURE.md` §5, solvable once, for one 24h horizon.

**Subtasks:**
- [ ] `PyomoHighsOptimizerAdapter.solve(state, forecast, site_config) -> DispatchPlan`
- [ ] Energy balance, battery SoC dynamics, diesel min-load linking constraint
- [ ] **Critical load has no slack variable** — implemented as its absence from the balance equation's
      right-hand slack, not as a heavily-weighted penalty (FR-O3, non-negotiable)
- [ ] Objective: fuel cost (from the fuel curve) + battery degradation cost + flexible-load penalty
- [ ] Diesel minimum run-time / off-time and start cost — **deferred to Phase 2**; v1 may start/stop
      diesel freely, this is scoped explicitly, not an oversight

**Test plan:**
- A day with abundant solar produces a plan with zero diesel hours
- A day with no solar and a depleted battery produces a plan that starts diesel and never drops
  critical load
- An artificial scenario with critical load exceeding total available generation is infeasible for
  the *flexible* load only — critical load still cannot appear as unserved in the model at all

**Design refs:** `ARCHITECTURE.md` §5.

---

### Task 1.2 — Database & migrations

**Goal:** Postgres + TimescaleDB, every `[BUILD]` table from `DATA_MODEL.md` §1–3, one command.

**Subtasks:**
- [ ] `docker-compose.dev.yml` brings up Postgres 16 + TimescaleDB on a named volume
- [ ] SQLAlchemy models + Alembic migration for `sites`, `site_config_history`, `forecasts`,
      `dispatch_plans`, `telemetry`, `dispatch_log`, `alerts`
- [ ] `baseline_telemetry` / `baseline_dispatch_log` tables (populated starting Phase 3, schema now)
- [ ] Unique index on `(site_id, tick_at)` for `dispatch_plans`; partial unique index on open alerts

**Test plan:**
- `alembic upgrade head` on an empty database creates every table
- `compose down && compose up` preserves data (named volume)

**Design refs:** `DATA_MODEL.md`.

---

### Task 1.3 — Backend: one triggered solve, one read endpoint

**Goal:** A solve can be triggered and its result read back over HTTP.

**Subtasks:**
- [ ] FastAPI skeleton, `backend/src/main.py`
- [ ] An internal trigger (CLI command or a protected endpoint) that runs one
      `rolling_horizon_service` tick manually — the rolling *scheduler* itself is Phase 2
- [ ] `GET /api/plans/latest?site_id=` per `API_CONTRACT.md` §2
- [ ] `GET /api/overview?site_id=` serving only the fields this phase can honestly compute — no
      `today.cost_saved_vs_baseline` yet, since there is no baseline ledger until Phase 3; that field
      is simply absent from the response rather than zero-filled

**Test plan:**
- Triggering a solve for `example-site.yml` inserts one `dispatch_plans` row
- `GET /api/plans/latest` returns it, validating against the Zod/JSON-Schema shape in
  `packages/contracts`
- `GET /api/overview` omits fields it cannot yet compute rather than returning zeros for them

**Design refs:** `API_CONTRACT.md` §1, §2; a value with unknown provenance must never render as an
unbadged number or a fabricated zero (`PRD.md` §3).

---

### Task 1.4 — Minimal dashboard: one chart

**Goal:** The plan from Task 1.3 renders as a chart in a browser.

**Subtasks:**
- [ ] Next.js app shell, `dashboard/`
- [ ] `components/badges/` — `Badge`, `BadgeGroup`, all four kinds — build this before anything else
      in the frontend, per `FE_DESIGN.md` §2
- [ ] `components/charts/PlanTimelineChart` bound to `GET /api/plans/latest`
- [ ] The hour-0 vs hour-1+ visual distinction from `FE_DESIGN.md` §3, even though at this phase no
      hour has actually executed yet (that distinction becomes meaningful in Phase 2)

**Test plan:**
- The plan chart renders real data from the backend, each series badged correctly
- Every rendered value carries a badge — asserted by a test, not by eye

**Design refs:** `FE_DESIGN.md` §1–3.

---

### Task 1.5 — `tools/scenariogen` scenarios for the other lanes

**Goal:** Backend and dashboard work in Phases 3 and 4 doesn't have to wait on the real forecast
integration or the digital twin being finished.

**Subtasks:**
- [ ] Scenarios: `clear-day`, `cloudy-afternoon` (the motivating example), `storm-day`, `load-spike`
- [ ] Each validated against the canonical schema before being committed
- [ ] `--loop` mode for driving the dashboard continuously during frontend development

**Test plan:**
- `--dry-run --validate` on every scenario emits only schema-valid events

**Design refs:** `PHASE_0` Task 0.6; `REPO_STRUCTURE.md` §7.

---

## Verification (end of Phase 1)

- [ ] **CP-1.1** Contracts frozen — `API_CONTRACT.md` and `DATA_MODEL.md` match the schemas exactly
- [ ] **CP-1.2** Clean database → migration → every table from §1–3 of `DATA_MODEL.md` exists
- [ ] **CP-1.3** A triggered solve produces a plan row, readable over the API
- [ ] **CP-1.4** The plan renders as a chart in a browser, every value badged
- [ ] **CP-1.5** Every bundled scenario validates

## Open issues / follow-ups

- [ ] The rolling scheduler itself, SoC feedback from telemetry, and diesel run-time constraints are
      explicitly Phase 2 — do not pull them forward
- [ ] After this phase, contracts are additive-only; a rename needs a `docs/agent/memory.md` entry
