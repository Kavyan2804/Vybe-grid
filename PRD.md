# PRD.md

**GridPilot — Rolling-Horizon Microgrid Energy Mix Optimizer**
**Document type:** Product Requirements Document
**Status:** v1 — pre-build draft. Every requirement carries a status tag; nothing is unmarked.
**Owner:** (assign)
**Related:** `REPO_STRUCTURE.md` · `docs/architecture/ARCHITECTURE.md` · `docs/architecture/API_CONTRACT.md` ·
`docs/architecture/DATA_MODEL.md` · `docs/design/FE_DESIGN.md` · `docs/phases/*`

---

## 0. How to read this document

Four tags, same discipline throughout. Every requirement, module and table row carries exactly one.

| Tag | Meaning |
|---|---|
| **[BUILD]** | Built for the MVP / first demo. Appears in `docs/phases/*` with a checkpoint. |
| **[STRETCH]** | Built only after every [BUILD] item works end to end. May not exist on demo day. |
| **[DESIGN]** | Specified here, not being built now. Stated as future scope, with the reason it isn't built yet. |
| **[EXCLUDED]** | Deliberately out of the product. Reason given. |

Nothing tagged [DESIGN] or [EXCLUDED] is claimed in the present tense anywhere else in this repo.

---

## 1. Problem

Off-grid and rural microgrids run on a mix of solar, battery storage and diesel generation, almost
always dispatched by a **greedy rule**: use solar first, then battery, then diesel when both run out.
That rule has no memory of the future — on a day with a cloudy afternoon it fully charges the battery
by late morning, curtails the rest of the day's solar, and then runs diesel for hours it didn't need
to, because nothing held battery capacity back to catch the midday surplus.

**GridPilot** replaces the greedy rule with a **rolling-horizon optimizer**: at every step it takes the
latest weather forecast and the battery's current charge, solves for the best 24-hour dispatch plan,
executes only the next hour's decision, and re-solves an hour later with better information. Same
hardware, same weather, less diesel burned — and the claim is measured, not asserted (§2, USP 1).

## 2. Product thesis & USPs

**Plan ahead, act on the freshest information, and prove the saving rather than claim it.** Six ideas
follow from that, each tagged by how committed it is for the MVP.

1. **Always-on shadow baseline — [BUILD].** Every rolling-horizon tick also runs the naive
   solar-then-battery-then-diesel controller against the *identical* realized weather and load, in a
   separate ledger. Savings are a **measured delta between two controllers on the same day**, never a
   claimed percentage. This is the demo's centrepiece, playing the same role the reference project's
   "control slot" plays for its shelf detector: without it, a number that looks like a saving could
   just be a favorable scenario.
2. **Config-driven, hardware-agnostic site model — [BUILD].** A microgrid is one YAML file — battery
   capacity, diesel fuel curve, load shape. Adding a new site costs zero code. The optimizer talks to
   a `DispatchPort` interface, not to a specific inverter or generator controller, so swapping the
   digital twin for real hardware later is one adapter, not a rewrite (§ Architecture).
3. **Graceful degradation, never a blackout — [BUILD].** Critical load is a *hard* constraint inside
   the MILP — it has no slack variable, so the solver cannot choose to drop it (§10, NFR-3). If the
   solver times out, is infeasible under an extreme scenario, or the forecast feed is stale, the
   system falls back to the safe greedy rule for that tick only, and says so loudly (an alert, not a
   silent substitution).
4. **Forecast-uncertainty-aware reserve margin — [STRETCH].** Instead of trusting a single point
   forecast, hold back battery capacity proportional to the spread between a pessimistic and
   optimistic solar forecast (P10/P90). Turns "forecasts are never perfect" from a caveat in the
   problem statement into a modelled quantity instead of a fixed safety margin picked by hand.
5. **Explainable dispatch — [STRETCH].** Each hour's decision ships with a one-line, plain-language
   reason, generated from the solver's own binding constraints and shadow prices — *"held 18% SoC back
   to catch tomorrow's forecasted midday surplus"* — not a templated guess. Operators who are asked to
   trust a black-box optimizer over their own judgment need this more than a nicer chart.
6. **Edge-deployable, cloud-optional — [DESIGN → BUILD path].** The whole loop, forecast fetch aside,
   runs on one low-power box at the site. The only outbound requirement is a periodic weather-API
   call; a fleet dashboard for an NGO managing many sites is an optional upstream sync, never a
   dependency for the site to keep dispatching (matches the target users — Tier-2/3 connectivity,
   §6).

## 3. The provenance contract — every number says where it came from

Borrowed directly from the discipline that makes a demo defensible: **a number without a badge is a
bug.** Four badges, and a value can carry more than one.

| Badge | Means | Produced by |
|---|---|---|
| `LIVE` | Measured from real site telemetry, right now | a real inverter/BMS/genset controller, once connected |
| `FORECAST` | Model-projected, not yet realized | the weather/solar/load forecast, or an unexecuted hour of a dispatch plan |
| `SIMULATED` | Produced by the digital-twin simulator standing in for real hardware | `dispatch_simulator` adapter (§ Architecture) |
| `BASELINE` | Produced by the greedy comparison controller, for benchmarking only | the shadow-baseline ledger — never the operative plan |

A dispatch plan's hour 0, once executed, is badged `LIVE` or `SIMULATED` (whichever adapter is
wired in); hours 1–23 stay `FORECAST` until their own tick arrives and supersedes them. A savings
number is always `LIVE|SIMULATED` + `BASELINE` together — one badge alone would be a different claim.

## 4. Tech stack

| Layer | Choice | Why |
|---|---|---|
| Optimization core | **Python 3.11, Pyomo 6.x + HiGHS** | mature MILP modelling; HiGHS is fast, free and has no license risk, unlike Gurobi/CPLEX; faster than CBC on horizons this size |
| Backend API | **FastAPI (Python)** | same language as the optimizer — no serialization boundary around the solver's internal state; async-native for SSE |
| Rolling scheduler | **APScheduler** (in-process) | an hourly tick is a cron-like job; no broker needed at single-site scale |
| Database | **PostgreSQL 16 + TimescaleDB** | forecasts, plans and telemetry are all time series; hypertables keep rolling-window queries cheap |
| ORM / migrations | **SQLAlchemy 2.x + Alembic** | |
| Weather / solar forecast | **Open-Meteo** (primary), **NASA POWER** (historical backfill / backtesting) | free, key-less, hourly GHI + cloud cover; NASA POWER supplies the historical series backtests need |
| Digital twin / simulator | Python module, `dispatch_simulator/` | stands in for real hardware before a site has telemetry; also drives backtests |
| Realtime transport | **Server-Sent Events** (native) | one-way push of plan/telemetry/alert updates; no broker, no WebSocket library |
| Frontend | **Next.js 14, React 18, TypeScript** | dashboard, App Router |
| Charts | **Recharts** | dispatch timeline, SoC trajectory, cost & emissions |
| Containerization | **Docker Compose** | one-command bring-up on an edge box at a rural site |
| Contracts | **JSON Schema**, `packages/contracts/` | forecast / dispatch-plan / telemetry / alert event shapes, shared and frozen after Phase 1 |

**Rejected alternatives, and why:**

| Decision | Rejected | Reason |
|---|---|---|
| Solver | Gurobi / CPLEX | Commercial license cost and risk for an open, demoable project; HiGHS is within a few percent on horizons this size |
| Backend language | Node/NestJS | Would add a language boundary between backend and optimizer for no benefit — there's no CV/ML runtime split here to justify it |
| Realtime transport | WebSockets | Only one-way push is needed (plan/telemetry/alert updates); SSE is simpler and needs no library |
| Weather provider | Solcast / NREL NSRDB | Better accuracy but paid and keyed; Open-Meteo is free and sufficient for the Simulated tier, revisit for Live-site tier |
| Load forecasting | An ML load forecaster | No real smart-meter data exists yet to train one; a synthetic day-profile is honest and sufficient for MVP (§9) |

## 5. Goals and non-goals

**Goals** — plan the solar/battery/diesel mix ahead of time instead of reacting to the present moment;
re-solve continuously as forecasts improve; guarantee critical loads are never dropped; make the
diesel/emissions/cost saving a measured, defensible number; run on a site with poor or intermittent
connectivity.

**Non-goals** — grid-tied tariff optimization or utility billing integration **[EXCLUDED]**, this is an
off-grid product; EV-charging co-optimization **[DESIGN]**, a natural extension once the core loop is
proven; predictive maintenance of the diesel engine itself **[EXCLUDED]**, out of scope for a dispatch
optimizer; carbon-credit certification reporting **[DESIGN]**, needs a real metering standard behind
it; automatic hardware failover beyond sending dispatch signals **[EXCLUDED]**.

## 6. Users

| User | Needs | Surface | Status |
|---|---|---|---|
| Microgrid operator / site technician | Today's plan, why it's making each call, an alert before diesel is needed | Dashboard | [BUILD] |
| Rural electrification agency / NGO | Proof of diesel and cost saved, per site and across a portfolio | Dashboard, fleet view | [BUILD] site-level, [DESIGN] fleet |
| Off-grid community (indirect) | Reliable power, lower fuel cost passed through | — | outcome, not a UI |
| Hardware integrator | A dispatch port to wire a real inverter/genset controller into | `DispatchPort` adapter | [DESIGN] |

## 7. Problem-statement coverage

| What the brief asks for | Module | Status |
|---|---|---|
| Plan ahead using a weather forecast, not just react | Optimization Core | **[BUILD]** |
| Model diesel on/off + minimum-load behaviour | Optimization Core | **[BUILD]** |
| Account for battery efficiency losses and degradation cost | Optimization Core | **[BUILD]** |
| Link each hour's decision to the next via battery SoC | Optimization Core | **[BUILD]** |
| Re-solve on a rolling basis as new forecasts arrive | Rolling Horizon Engine | **[BUILD]** |
| Guarantee critical loads are never dropped | Optimization Core (hard constraint) | **[BUILD]**, proved in Phase 5 |
| Revise the plan as forecasts improve | Rolling Horizon Engine | **[BUILD]** |
| Quantify diesel/emissions/cost reduction vs the naive approach | Baseline Comparator | **[BUILD]** |
| Weather/forecast API integration | Forecast Ingestion | **[BUILD]** |
| Web dashboard | Dashboard | **[BUILD]** |
| Battery/storage modelling library | Optimization Core, config-driven | **[BUILD]** |
| Real hardware integration (inverter/BMS/genset control) | Dispatch Port — hardware adapter | **[DESIGN]** |
| Multi-site fleet monitoring | Fleet View | **[DESIGN]** |
| ML-based load forecasting from real meter data | Forecast Ingestion | **[DESIGN]**, needs real telemetry first |

## 8. Modules

### 8.1 Optimization Core — `optimizer/domain` + `optimizer/application`
The MILP formulation and the rolling-horizon orchestration. Pure Python, no I/O — see
`docs/architecture/ARCHITECTURE.md` for the exact decision variables and constraints. **[BUILD]**

### 8.2 Forecast Ingestion — `optimizer/infrastructure/forecast_openmeteo`
Fetches solar irradiance, cloud cover and a synthetic load profile; falls back to a persistence
forecast (assume tomorrow behaves like the last known good forecast) if the API is unreachable, and
badges that fallback so it is never mistaken for a fresh read. **[BUILD]**; ML load forecasting from
real meter data is **[DESIGN]**.

### 8.3 Baseline Comparator — `optimizer/application/baseline_service`
Runs the literal greedy rule from the problem statement against identical realized conditions every
tick, in a shadow ledger. This is what makes USP 1 true. **[BUILD]**

### 8.4 Dispatch & Digital Twin — `optimizer/infrastructure/dispatch_simulator`
Executes the plan's hour 0 and produces the next tick's starting state. Before real hardware exists,
a physics-based simulator (battery efficiency losses, diesel fuel curve, solar production from
forecasted irradiance plus noise) plays that role, badged `SIMULATED`. **[BUILD]**; a Modbus/MQTT
adapter to real inverter/genset controllers is **[DESIGN]**.

### 8.5 Telemetry & Ledger — `backend` + Postgres
Persists the PLANNED domain (forecasts, dispatch plans) and the ACTUAL domain (telemetry, executed
decisions, baseline shadow run) separately; savings are a read-only comparison computed after both
persist (`docs/architecture/DATA_MODEL.md` §0). **[BUILD]**

### 8.6 Alerts — `backend`
One lifecycle (`created → acknowledged → resolved`), dedup per `(type, site, subject)`, cooldown
after resolve. See §11. **[BUILD]**

### 8.7 Dashboard — `dashboard`
Plan timeline, SoC trajectory with reserve band, savings-vs-baseline tile, alerts, forecast panel.
See `docs/design/FE_DESIGN.md`. **[BUILD]**; explainability panel and fleet view are **[STRETCH]**/**[DESIGN]**.

## 9. Capability tiers

| | Simulated | Live-site | Fleet |
|---|---|---|---|
| Gate | weather API + a site config file | a hardware integration for that site's inverter/BMS/genset | 2+ sites reporting to one backend |
| Rolling optimizer, baseline comparator, dashboard | ✓ | ✓ | ✓ |
| Real telemetry, real dispatch commands | — | ✓ | ✓ |
| Cross-site aggregation, portfolio savings | — | — | ✓ |
| Status | **[BUILD]** | **[DESIGN]** | **[DESIGN]** |

**The MVP runs at Simulated tier.** Every claim about diesel/cost/emissions saved is a claim about
the digital twin's physics model, not about a real generator — say this plainly whenever the number
is shown outside this repo. Live-site tier is gated on a real hardware integration and a validation
checkpoint against it, the same way the reference project gated its CV model on real footage before
trusting it (§ Architecture, "domain gap" risk in §15).

## 10. Functional requirements

### 10.1 Optimizer

| | Requirement | Status |
|---|---|---|
| FR-O1 | Formulate and solve a 24h rolling MILP from the current SoC and the latest forecast | **[BUILD]** |
| FR-O2 | Diesel binary on/off with a minimum-load constraint when on | **[BUILD]** |
| FR-O3 | Critical load has **no slack variable** — it cannot be dropped by construction, not by penalty | **[BUILD]** |
| FR-O4 | Battery round-trip efficiency losses and a degradation cost term in the objective | **[BUILD]** |
| FR-O5 | Diesel minimum run-time and minimum off-time constraints | **[BUILD]** |
| FR-O6 | Fall back to the greedy baseline for one tick on solver timeout or infeasibility, logged as an alert | **[BUILD]** |
| FR-O7 | Warm-start each solve from the previous plan's shifted trajectory | **[STRETCH]** |
| FR-O8 | Forecast-uncertainty-aware reserve margin from a P10/P90 solar band | **[STRETCH]** |
| FR-O9 | Per-hour natural-language explanation from binding constraints / shadow prices | **[STRETCH]** |

### 10.2 Backend

| | Requirement | Status |
|---|---|---|
| FR-B1 | Fetch and persist the forecast on a schedule, badged `FORECAST` | **[BUILD]** |
| FR-B2 | Trigger one rolling-horizon tick per configured interval | **[BUILD]** |
| FR-B3 | PLANNED and ACTUAL domains persist in separate tables; comparison reads both, after both persist, never writes | **[BUILD]** |
| FR-B4 | Run the shadow baseline every tick against identical realized conditions | **[BUILD]** |
| FR-B5 | One alert lifecycle, dedup, cooldown, shared by every alert type | **[BUILD]** |
| FR-B6 | Push plan/telemetry/alert updates over SSE | **[BUILD]** |
| FR-B7 | Serve the REST API in `docs/architecture/API_CONTRACT.md` | **[BUILD]** |
| FR-B8 | Import/version a site config without a code change | **[BUILD]** |
| FR-B9 | Route requests across multiple sites | **[DESIGN]** |

### 10.3 Dashboard

| | Requirement | Status |
|---|---|---|
| FR-D1 | Every number carries a badge from §3; a value with unknown provenance renders `—`, never a bare number | **[BUILD]** |
| FR-D2 | 24-hour dispatch plan timeline (solar / battery / diesel / load) | **[BUILD]** |
| FR-D3 | SoC trajectory chart with the reserve-margin band | **[BUILD]** |
| FR-D4 | Savings-vs-baseline tile — fuel litres, cost, CO₂, diesel-hours, badged `BASELINE` | **[BUILD]** |
| FR-D5 | Alert centre — acknowledge, resolve | **[BUILD]** |
| FR-D6 | Explainability panel, one line per hour | **[STRETCH]** |
| FR-D7 | Forecast panel with an uncertainty band | **[STRETCH]** |
| FR-D8 | Fleet view across sites | **[DESIGN]** |

## 11. Alert rules

| Type | Inputs | Rule | Badges |
|---|---|---|---|
| `CRITICAL_LOAD_AT_RISK` | optimizer | the solver's fallback path was invoked because the primary solve could not guarantee critical load | `SIMULATED`/`LIVE` |
| `LOW_SOC_RESERVE` | telemetry | SoC below the reserve margin the current plan assumed | `SIMULATED`/`LIVE` |
| `DIESEL_REQUIRED_SOON` | plan | plan calls for diesel start within the next 2 hours | `FORECAST` |
| `SOLVER_FALLBACK_ACTIVE` | optimizer | this tick's decision came from the greedy fallback, not the MILP | `SIMULATED`/`LIVE` |
| `FORECAST_STALE` | forecast ingestion | latest forecast is older than 2x its expected refresh interval | `FORECAST` |
| `BASELINE_DIVERGENCE` | comparator | the optimized plan performed *worse* than baseline for a tick — should never fire; exists to catch a modelling bug, not to report normal operation | `SIMULATED`/`LIVE` + `BASELINE` |

## 12. Data model

Summarized here; column-level schema in `docs/architecture/DATA_MODEL.md`. The core invariant: **the
optimizer's plan (PLANNED) and what actually happened (ACTUAL) are separate tables, and the savings
number is a read-only join computed after both persist** — the same discipline as separating
observation from accounting in any system where a claim needs to be checkable, not just asserted.

## 13. Non-functional requirements

| | Requirement | Status |
|---|---|---|
| NFR-1 | A rolling solve completes well inside the tick interval — target < 30s for a 24h/1h-step MILP on commodity hardware, measured | **[BUILD]** |
| NFR-2 | The loop runs offline between ticks; only the forecast fetch needs connectivity | **[BUILD]** |
| NFR-3 | Unmet critical load is exactly 0 across every backtested scenario, including fallback paths | **[BUILD]** — the one number that must never fail, proved in Phase 5 |
| NFR-4 | Dashboard reflects a new tick within 2s on LAN | **[BUILD]** |
| NFR-5 | Every plan is reproducible from its stored inputs (forecast + starting SoC + site config version) | **[BUILD]** |
| NFR-6 | No API key required for the MVP forecast provider; nothing secret is committed | **[BUILD]** |

## 14. Decisions

Recorded here as recommendations awaiting a ruling — see `docs/agent/memory.md` for the format that
makes a ruling durable once made.

| Decision | Recommendation | Rejected alternative |
|---|---|---|
| MILP solver | Pyomo + HiGHS | PuLP+CBC (slower at this horizon); Gurobi/CPLEX (license cost/risk) |
| Backend language | Python (FastAPI) | Node/NestJS — an unnecessary language boundary around the solver |
| Tick length / horizon | 1-hour ticks, 24-hour horizon | 15-minute ticks — finer than the forecast providers or typical genset dispatch practice support well |
| Weather provider | Open-Meteo | Solcast/NREL NSRDB — better accuracy, paid and keyed; revisit for Live-site tier |
| Load forecasting | Synthetic day-profile for MVP | An ML forecaster — no real meter data yet to train one |
| Realtime transport | SSE | WebSockets — only one-way push is needed |

## 15. Risks

| Item | Severity | Position |
|---|---|---|
| Solver runtime exceeds the tick budget as constraints (min run-time, uncertainty bands) are added | Medium | Mitigate with warm-starts, HiGHS, and a MIP-gap tolerance; measured in Phase 5 |
| Weather API outage | Medium | Fall back to a persistence forecast (assume tomorrow ≈ last known good), badged so it is never mistaken for fresh data |
| Domain gap between the digital twin and real hardware | High, if claimed at Live-site tier | Every savings number at MVP is a Simulated-tier claim; Live-site tier is gated on a real validation checkpoint before it is sold as proven — same discipline the reference project applied to a CV model trained on someone else's data |
| Infeasibility under an extreme scenario (diesel down for maintenance, no sun) | Critical | The optimizer must degrade to "serve what you can, protect critical load" via the fallback path, never crash or fail silently — proved in Phase 5 |
| Overclaiming savings from a favorable synthetic scenario | Medium | The always-on shadow baseline (USP 1) makes every saving a measured delta on identical conditions, not a cherry-picked comparison |

## 16. Roadmap

1. **Phase 0 — Foundations & Baseline.** Site model, forecast ingestion, the greedy baseline
   controller, frozen contracts, solver pinned.
2. **Phase 1 — The Loop.** One forecast → one MILP solve → one chart, end to end.
3. **Phase 2 — Rolling Horizon Engine.** Repeated re-solves, SoC feedback, degradation and diesel
   run-time constraints, fallback path.
4. **Phase 3 — Dispatch, Digital Twin & Ledger.** The simulator, the shadow baseline ledger, alerts.
5. **Phase 4 — Dashboard & Insights.** Every panel, badged, moving, explainable.
6. **Phase 5 — Hardening & Validation.** Multi-scenario backtests, the critical-load proof, a soak
   run, acceptance sweep.
7. **Post-MVP.** Real hardware dispatch adapter (Modbus/MQTT), Live-site tier validation, fleet
   dashboard, ML load forecaster trained on real meter data, carbon-credit reporting.
