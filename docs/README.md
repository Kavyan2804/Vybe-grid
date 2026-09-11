# docs/

Source of truth for GridPilot, beyond the two root files (`PRD.md`, `REPO_STRUCTURE.md`).

```
architecture/
  ARCHITECTURE.md       Clean Architecture layering, ports, the MILP formulation
  API_CONTRACT.md        backend <-> dashboard contract — freezes end of Phase 1
  DATA_MODEL.md          column-level schema, PLANNED/ACTUAL split — freezes with API_CONTRACT.md
design/
  FE_DESIGN.md            tokens, wireframes, panel states
phases/
  README.md               phase index + parallel dependency graph
  PHASE_0_foundations_and_baseline.md
  PHASE_1_the_loop.md
  PHASE_2_rolling_horizon_engine.md
  PHASE_3_dispatch_twin_and_ledger.md
  PHASE_4_dashboard_and_insights.md
  PHASE_5_hardening_and_validation.md
agent/
  memory.md                decision ledger — why is it this way?
  mistakes.md               dated incident log — what has already gone wrong?
```

## Reading order for someone new to the project

1. [`../PRD.md`](../PRD.md) — what this is, the USPs, the tech stack, what's built vs designed
2. [`../REPO_STRUCTURE.md`](../REPO_STRUCTURE.md) — how the code is laid out and why
3. [`architecture/ARCHITECTURE.md`](architecture/ARCHITECTURE.md) — the layering and the optimization
   formulation
4. [`phases/README.md`](phases/README.md) — build order, starting with Phase 0

## The two agent-context files

| File | Answers | Lifetime |
|---|---|---|
| [`agent/memory.md`](agent/memory.md) | Why is it this way? | Append-only; entries superseded, never edited |
| [`agent/mistakes.md`](agent/mistakes.md) | What has already gone wrong? | Append-only, starts empty |

Both start with only the entries that are true today — a seeded decision for `memory.md`, and a set
of known-in-advance failure modes for `mistakes.md` that haven't happened yet but are worth designing
against from Phase 0.
