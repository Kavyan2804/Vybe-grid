# Phase index

```
                      ┌──▶ 2 · Rolling Horizon Engine ────┐
0 · Foundations ──▶ 1 · The Loop ──┼──▶ 3 · Dispatch, Twin & Ledger ──┼──▶ 5 · Hardening
                      └──▶ 4 · Dashboard & Insights ──────┘
```

Phase 1 freezes `packages/contracts/` (`docs/architecture/API_CONTRACT.md`,
`docs/architecture/DATA_MODEL.md`). Phases 2, 3 and 4 then have no dependency on each other and can
build concurrently, each using `tools/scenariogen` as a stand-in for whatever it doesn't yet have
from another lane — exactly the mechanism that lets a solo builder or a small team make progress on
all three fronts without one blocking the others.

| Phase | Goal | Depends on | Demo milestone |
|---|---|---|---|
| [0 — Foundations & Baseline](PHASE_0_foundations_and_baseline.md) | Site model, forecast ingestion, the greedy baseline controller, frozen contracts, solver pinned | — | The greedy controller produces a 24h dispatch sequence from one day of forecast and prints total diesel-hours and cost |
| [1 — The Loop](PHASE_1_the_loop.md) | One forecast → one MILP solve → one chart, end to end | 0 | A 24h plan renders as a chart in a browser |
| [2 — Rolling Horizon Engine](PHASE_2_rolling_horizon_engine.md) | Repeated re-solves, SoC feedback from telemetry, degradation & diesel run-time constraints, fallback path | 1 | The plan visibly changes between consecutive ticks as the forecast updates |
| [3 — Dispatch, Twin & Ledger](PHASE_3_dispatch_twin_and_ledger.md) | The digital twin, the shadow-baseline ledger, alerts | 1 | A savings number appears, backed by two ledgers on identical conditions |
| [4 — Dashboard & Insights](PHASE_4_dashboard_and_insights.md) | Every panel badged, moving, explainable | 1 | Every number on every route carries a badge |
| [5 — Hardening & Validation](PHASE_5_hardening_and_validation.md) | Multi-scenario backtests, the critical-load proof, a soak run, acceptance sweep | 2, 3, 4 | Critical load unmet is 0 across every scenario, proved by a test, not by eye |

## The two agent-context files

| File | Answers |
|---|---|
| [`../agent/memory.md`](../agent/memory.md) | Why is it this way? |
| [`../agent/mistakes.md`](../agent/mistakes.md) | What has already gone wrong? |

Both are append-only and both start empty — there is no build history yet. Use them from Phase 0
onward rather than letting the same decision get re-litigated or the same mistake happen twice.
