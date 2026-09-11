# REPO_STRUCTURE.md

**GridPilot — repository layout and ownership**
**Status:** Active — pre-build. This is the structure the build follows from Phase 0 onward.
**Derived from:** `PRD.md`, `docs/architecture/ARCHITECTURE.md`

---

## 1. Why this shape

Two ideas drive every directory decision here:

1. **The optimizer is a Clean Architecture core, not a script.** `domain/` and `application/` know
   nothing about Pyomo, Postgres, FastAPI or HTTP — they depend on interfaces (`ports.py`), and every
   concrete technology lives behind an adapter in `infrastructure/`. This is what makes "swap the
   digital twin for real hardware" a one-adapter change instead of a rewrite (`ARCHITECTURE.md` §2).
2. **Planned and actual are separate, always.** What the optimizer decided (forecasts, dispatch
   plans) and what really happened (telemetry, executed decisions, the baseline's shadow run) live in
   different tables, populated by different code paths, joined only by a read-only comparison. A file
   that blurs this — a plan row updated in place with an actual reading, say — is wrong regardless of
   how convenient it looks at the time.

> **The grep test:** if a file under `optimizer/domain/` or `optimizer/application/` imports
> `pyomo`, `sqlalchemy`, `fastapi`, `httpx` or `requests`, it is in the wrong layer. This is enforced
> by `infra/scripts/verify_no_layer_violation.sh`, not by review alone.

---

## 2. Top-level tree

```
gridpilot/
├── PRD.md
├── REPO_STRUCTURE.md
├── README.md
├── docker-compose.yml
├── .env.example
├── .gitignore
│
├── optimizer/                  # Python 3.11 — the Clean Architecture core
├── backend/                    # FastAPI host — scheduler, API, SSE
├── dashboard/                  # Next.js 14 · React 18 · TypeScript
├── packages/
│   └── contracts/              # JSON Schema — the only shared, frozen surface
├── tools/
│   └── scenariogen/            # authored synthetic forecasts/telemetry, never captured from a real run
├── infra/
│   ├── compose/
│   └── scripts/
└── docs/
    ├── README.md
    ├── architecture/
    ├── design/
    ├── phases/
    └── agent/
```

Seven top-level concerns. No `src/` at the root, no `services/`, no `common`/`shared` package —
those are the kind of vague names that accumulate whatever nobody wanted to name properly.

---

## 3. `optimizer/` — the Clean Architecture core

```
optimizer/
├── domain/
│   ├── entities.py         # Site, Battery, DieselGenerator, Load, Forecast, DispatchPlan, DispatchDecision
│   └── ports.py             # ForecastPort, OptimizerPort, DispatchPort, PlanRepository, TelemetryRepository
│
├── application/             # orchestration only — depends on domain, imports no concrete library
│   ├── rolling_horizon_service.py   # one tick: fetch → solve → persist → execute → record
│   ├── baseline_service.py          # runs the greedy rule in a shadow ledger, same tick, same conditions
│   └── explainability_service.py    # [STRETCH] binding-constraint → one-line rationale
│
├── infrastructure/          # the only place a concrete library is imported
│   ├── optimizer_pyomo/     # PyomoHighsOptimizerAdapter — the MILP formulation lives here
│   ├── forecast_openmeteo/  # OpenMeteoForecastAdapter + persistence-forecast fallback
│   ├── dispatch_simulator/  # SimulatorDispatchAdapter — the digital twin
│   ├── dispatch_hardware/   # [DESIGN] ModbusDispatchAdapter / MQTTDispatchAdapter
│   └── db/                  # SQLAlchemy repositories implementing PlanRepository / TelemetryRepository
│
├── sites/                   # one YAML per microgrid — the only thing that changes per deployment
│   └── example-site.yml
│
├── tests/
└── pyproject.toml
```

**Why `sites/` is not database rows from day one.** A site config is small, versionable, and needs to
be reviewable in a diff before it drives a real generator. It becomes a `sites` table row
(`DATA_MODEL.md` §1) once the backend owns it; the YAML stays as the source format for import/export
and for anyone running the optimizer standalone (a backtest, a notebook) without the backend at all.

---

## 4. `backend/` — FastAPI host

```
backend/
├── src/
│   ├── main.py
│   ├── config/                 # env, validated
│   ├── api/                    # routers — one per API_CONTRACT.md section
│   │   ├── overview.py
│   │   ├── plans.py
│   │   ├── telemetry.py
│   │   ├── forecasts.py
│   │   ├── savings.py
│   │   ├── alerts.py
│   │   └── sites.py            # [DESIGN] — multi-site
│   ├── scheduler/               # APScheduler — the hourly tick, calls into optimizer/application
│   ├── realtime/                 # SSE broadcaster — plan.updated, telemetry.updated, alert.created
│   └── alerts/                   # lifecycle, dedup, cooldown (§11 PRD)
├── tests/
└── pyproject.toml
```

The backend **imports `optimizer/application`**, never `optimizer/infrastructure` directly — it
constructs adapters and injects them through the ports the application layer declares. This is what
keeps the layer boundary real rather than aspirational.

---

## 5. `dashboard/` — Next.js dashboard

```
dashboard/
├── app/
│   ├── layout.tsx           # header: site selector, clock, alert bell
│   ├── page.tsx             # overview: current mix, plan timeline, SoC, savings tile
│   ├── plan/                # plan vs actual, forecast panel
│   ├── savings/             # cumulative diesel/cost/CO2 saved vs baseline
│   ├── alerts/
│   └── api/                 # BFF only — proxies to the backend, never touches Postgres
├── components/
│   ├── badges/              # LIVE | FORECAST | SIMULATED | BASELINE — build this first
│   ├── panels/              # shared five-state Panel (loading/empty/stale/disconnected/error)
│   └── charts/              # dispatch timeline, SoC trajectory, savings chart
└── lib/
    ├── api.ts
    └── sse.ts
```

`components/badges/` is listed first for the same reason it always is: every other component depends
on it, and it is the cheapest thing to forget on day one.

---

## 6. `packages/contracts/` — the only shared, frozen surface

```
packages/contracts/
├── events/                  # JSON Schema — forecast, dispatch_plan, dispatch_decision, telemetry, alert
├── site-config.schema.json  # the YAML site format, validated
└── README.md
```

Frozen at the end of Phase 1 (`docs/phases/PHASE_1_the_loop.md`). Additive changes only after that —
a field is added, never renamed, exactly as the discipline in the PRD's Tech Stack decisions implies.

---

## 7. `tools/scenariogen/` — authored, never captured

A synthetic-scenario generator that emits schema-valid forecasts and telemetry so the backend and
dashboard lanes can build without waiting on a real weather-API integration or a finished simulator.
**The line that keeps it legal:** scenarios are authored from files — "a cloudy afternoon that clears
by 6pm" — never captured from a real optimizer run and replayed as if it were live. Mirrors the
`devfeed` pattern from prior work on this team: it is what lets Phases 2, 3 and 4 build concurrently
against Phase 1's frozen contracts instead of waiting on each other.

---

## 8. `infra/`

```
infra/
├── compose/
│   └── docker-compose.dev.yml     # postgres+timescale (named volume) · backend · dashboard
└── scripts/
    ├── verify_no_layer_violation.sh   # greps domain/ and application/ for infra imports
    ├── verify_no_demo_scenario.sh     # nothing under optimizer/infrastructure references scenariogen
    └── preflight.sh                    # pre-demo checklist
```

---

## 9. `docs/`

```
docs/
├── README.md                                    index + dependency graph
├── architecture/
│   ├── ARCHITECTURE.md                          Clean Architecture, ports, the MILP formulation
│   ├── API_CONTRACT.md                          backend <-> dashboard contract
│   └── DATA_MODEL.md                            column-level schema, PLANNED/ACTUAL split
├── design/
│   └── FE_DESIGN.md                             tokens, wireframes, panel states
├── phases/
│   ├── README.md                                index + parallel dependency graph
│   ├── PHASE_0_foundations_and_baseline.md
│   ├── PHASE_1_the_loop.md
│   ├── PHASE_2_rolling_horizon_engine.md
│   ├── PHASE_3_dispatch_twin_and_ledger.md
│   ├── PHASE_4_dashboard_and_insights.md
│   └── PHASE_5_hardening_and_validation.md
└── agent/
    ├── memory.md                                durable decision ledger — why is it this way?
    └── mistakes.md                              dated incident log — what has already gone wrong?
```

### The two agent-context files

| File | Answers | Lifetime |
|---|---|---|
| `docs/agent/memory.md` | *Why is it this way?* Numbered, append-only decisions: what, why, what it forecloses. | Append-only. Entries are superseded, never edited. |
| `docs/agent/mistakes.md` | *What has already gone wrong?* Dated incidents: symptom, root cause, the rule that now prevents it. | Append-only, and starts empty — there is no history yet to record. |

A mistake, once understood, produces a rule; if the rule should bind future decisions, it is promoted
to a `memory.md` entry. Nothing skips a step.

---

## 10. Ownership

Four people, three lanes. The layer boundaries in §1 are what make these lanes safe to run
concurrently — `optimizer/`, `backend/` and `dashboard/` barely overlap, the same way CODEOWNERS
partitioning worked on a prior project this structure is modelled on.

```
/optimizer/                    Aarin           (ML, integration, dockerization, data)
/backend/                      Dhruvi, Kavyan  (backend & database)
/dashboard/                    Yashita         (frontend)
/packages/contracts/           Aarin drafts — Dhruvi, Kavyan and Yashita review before it freezes
                                (Phase 0 Task 0.4); additive-only after
/tools/scenariogen/            Aarin           (it's data — scenario authoring)
/infra/                        Aarin           (dockerization)
/docs/                         Aarin coordinates — each lane keeps its own phase doc's
                                checkboxes and `docs/agent/memory.md`/`mistakes.md` entries current
```

**Why `optimizer/` is one person's directory rather than split further.** Domain, application and
infrastructure inside it are separate layers for testability (§1), not separate ownership — splitting
a rolling-horizon formulation across two people mid-build is how the SoC-feedback bug class in
`docs/agent/mistakes.md` "known in advance" section happens for real. `backend/` is two people
because database schema work (migrations, DATA_MODEL.md) and API/scheduler work (routers, SSE,
alerts) genuinely parallelize once Phase 1's tables exist — see `docs/phases/PHASE_3_dispatch_twin_and_ledger.md`
for exactly where that split runs inside one phase.

See `docs/phases/README.md` for which phase each person is in at any given time.

---

## 11. Phase index

```
                      ┌──▶ 2 · Rolling Horizon Engine ────┐
0 · Foundations ──▶ 1 · The Loop ──┼──▶ 3 · Dispatch, Twin & Ledger ──┼──▶ 5 · Hardening
                      └──▶ 4 · Dashboard & Insights ──────┘
```

Phase 1 freezes `packages/contracts/`; Phases 2, 3 and 4 then build concurrently against it, each
using `tools/scenariogen` as a stand-in for whatever it doesn't yet have from another lane. Full docs
in `docs/phases/`.

| Phase | Owner | Goal | Depends on |
|---|---|---|---|
| 0 — Foundations & Baseline | Aarin | Site model, forecast ingestion, the greedy baseline controller, frozen contracts | — |
| 1 — The Loop | ALL | One forecast → one solve → one chart, end to end | 0 |
| 2 — Rolling Horizon Engine | Aarin | Repeated re-solves, SoC feedback, degradation & run-time constraints, fallback | 1 |
| 3 — Dispatch, Twin & Ledger | Aarin (twin) / Dhruvi & Kavyan (ledger, alerts) | The simulator, the shadow-baseline ledger, alerts | 1 |
| 4 — Dashboard & Insights | Yashita | Every panel badged, moving, explainable | 1 |
| 5 — Hardening & Validation | ALL, Aarin coordinates | Multi-scenario backtests, the critical-load proof, a soak run | 2, 3, 4 |

---

## 12. Tooling and pins

| | Pin |
|---|---|
| Python | 3.11, `uv` or `venv` |
| Solver | HiGHS via Pyomo 6.x |
| Node | 20 |
| PostgreSQL | 16 + TimescaleDB |
| Next.js / React | 14 / 18 |
| Docker Compose | v2 |

No substitutions mid-build without a `docs/agent/memory.md` entry recording why.
