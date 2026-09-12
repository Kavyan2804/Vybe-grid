# memory.md — durable decision ledger

*Why is it this way?*

**Append-only. Entries are superseded, never edited.** Numbered. Whoever makes the call writes the
entry.

**Entry format:**

```
## NNN — <one-line decision>
**Date:** YYYY-MM-DD · **By:** <who> · **Status:** Active | Superseded by NNN

**Decision.** What was decided, in the imperative.
**Reason.** Why, including the alternative that was rejected.
**Forecloses.** What this makes impossible or expensive later.
```

Escalation: if a rule needs to bind every future decision of its kind, it belongs here rather than in
a phase doc's prose. If it should never be violated, promote it further into a project-wide law file
if this project grows one — nothing skips a step.

---

## 001 — Documentation and repo structure modelled on a prior project's discipline
**Date:** 2026-09-11 · **By:** project owner · **Status:** Active

**Decision.** GridPilot's `PRD.md`, `REPO_STRUCTURE.md`, phase docs, `API_CONTRACT.md`,
`DATA_MODEL.md` and `FE_DESIGN.md` follow the structure, tagging discipline
(`[BUILD]/[STRETCH]/[DESIGN]/[EXCLUDED]`), and provenance-badge pattern used on a prior retail
intelligence project, adapted to this domain rather than copied verbatim.

**Reason.** That structure earned its shape under real pressure — a hackathon where every claim had
to survive a judge asking "is this actually real?" The same discipline applies here for a different
reason: a rolling-horizon optimizer's value proposition is a *saved* number (diesel, cost, emissions),
and a saved number is only trustworthy if it's clear what's measured, what's forecast, and what's
simulated. The badge system (`LIVE | FORECAST | SIMULATED | BASELINE`) and the always-on shadow
baseline (PRD USP 1) exist for that reason.

**Forecloses.** Nothing yet — this is the first entry. It sets the expectation that decisions from
here on get written down here rather than re-argued the next time they come up, and that phase docs
stay prospective (unchecked boxes, no fabricated history) until work actually happens.

---

<!-- Next entry starts at 002. Do not renumber or edit an existing entry — supersede it instead. -->

## 002 — Record the Phase 0 Pyomo/HiGHS smoke-test latency baseline
**Date:** 2026-09-12 · **By:** Copilot · **Status:** Active

**Decision.** Use the Pyomo/HiGHS smoke test as the initial solver-latency baseline: the two-variable
LP solved to objective `10.0` in `275.778 ms`, and the 24-variable toy problem solved to objective
`276.0` in `8.206 ms` on the development machine.

**Reason.** Phase 0 requires a real, recorded number before the full rolling-horizon formulation is
built; the two tests establish correctness and a first-order latency floor.

**Forecloses.** These values are machine-specific sanity measurements, not the Phase 5 production
latency budget or a claim about the eventual full constraint set.

---

## 003 — Phase 2 Rolling Horizon Engine: Up/down time formulation and fallback design
**Date:** 2026-09-12 · **By:** Aarin · **Status:** Active

**Decision.**
1. Implement diesel up/down-time via binary transition tracking (`diesel_start[t]`, `diesel_stop[t]`), where start cost is applied exclusively on genuine `0 -> 1` transitions.
2. The starting SoC for every tick in `RollingHorizonService` is strictly sourced from `TelemetryRepository.latest_soc()`, never re-using the previous plan's predicted trajectory.
3. Fallback path treats critical load as structurally non-curtailable by executing the greedy baseline controller and raising `SOLVER_FALLBACK_ACTIVE`.

**Reason.** Conforms to Clean Architecture layer rules and PRD NFR-3 / USP 1, guaranteeing that real forecast correction happens across rolling ticks and critical load is never dropped even when the solver fails or times out.

**Forecloses.** Starting SoC cannot be queried from `DispatchPlan` tables.

---

## 004 — Unify alert enums, Postgres alert store, and identical-conditions baseline
**Date:** 2026-09-13 · **By:** Copilot · **Status:** Active

**Decision.**
1. Align DB `alert_type` with `packages/contracts/events/alert.schema.json` (and Phase 3 rules).
2. Tick path writes alerts only to Postgres; `/api/alerts*` reads that same store (in-memory remains a test override).
3. Shadow baseline decides against twin-realized solar/load and writes `baseline_dispatch_log` alongside `baseline_telemetry`.
4. Rolling-horizon solves receive prior diesel on/off continuity from telemetry/service state.

**Reason.** Savings and alerts were split across stores/enums and the baseline was comparing forecast inputs, which would make USP-1 numbers and the alert inbox dishonest.

**Forecloses.** Reintroducing divergent alert type names without a migration; sourcing baseline conditions from forecast instead of realized twin/hardware telemetry.

<!-- Next entry starts at 005. Do not renumber or edit an existing entry — supersede it instead. -->
