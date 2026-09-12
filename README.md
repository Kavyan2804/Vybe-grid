# GridPilot

**Rolling-horizon dispatch optimizer for off-grid microgrids** — plans the solar/battery/diesel mix
24 hours ahead from a weather forecast, executes only the next hour, and re-solves every hour as
forecasts improve. Built to replace the "use solar first, then battery, then diesel" greedy
controller most sites run today, and to prove the saving rather than claim it.

**Status: working, not just designed.** The full loop runs end to end against a real PostgreSQL
database — a real forecast is fetched, a real mixed-integer program is solved (HiGHS reports
`optimal`), the decision is executed against the digital twin, and the result is served live to a
dashboard over Server-Sent Events. `docs/phases/*` describes the build plan; this file describes
what's actually running today.

---

## Quickstart

### Docker Compose (everything at once)

```bash
cp .env.example .env          # defaults already point at the compose services
docker compose up --build
```

- Dashboard: [http://localhost:3000](http://localhost:3000)
- Backend API + docs: [http://localhost:8000/docs](http://localhost:8000/docs)
- Postgres/TimescaleDB: `localhost:5432` (user/db `gridpilot`)

The backend runs its own scheduler on boot — it ticks the rolling-horizon loop automatically every
`TICK_INTERVAL_MINUTES` (default 60). To see a change without waiting an hour, either hit
`POST /api/tick?site_id=Dharavi Microgrid` directly or use the **"Run tick now"** button in the
dashboard header.

### Running the pieces by hand (dev loop)

```bash
# 1. Database only
docker compose up db -d

# 2. Backend
cd backend
uv venv .venv && .venv/Scripts/activate   # or source .venv/bin/activate on Linux/macOS
uv pip install -e ".[dev]"
alembic upgrade head
uvicorn src.main:app --reload --port 8000

# 3. Dashboard
cd dashboard
npm install
npm run dev
```

`optimizer/` is a separate installable package (`optimizer/pyproject.toml`) that both the backend
(`backend/src/services/optimizer_bridge.py`) and its own test suite depend on directly — there's no
service boundary between them, only a directory-ownership one (see **Architecture** below).

---

## Repository layout

```
Vybe-grid/
├── optimizer/          Clean Architecture core — domain, application, infrastructure (Python)
│   ├── domain/          entities + ports; zero external imports
│   ├── application/     rolling_horizon_service.py, baseline_service.py (the shadow controller)
│   ├── infrastructure/  Pyomo+HiGHS adapter, Open-Meteo adapter, digital-twin dispatch adapter
│   ├── sites/           one YAML per microgrid — the only thing that changes per deployment
│   └── tests/
├── backend/             FastAPI — API, scheduler, realtime, and the Postgres bridge
│   └── src/
│       ├── api/          overview, plans, telemetry, forecasts, savings, alerts, sites, tick
│       ├── db/            SQLAlchemy models, async repositories, Alembic migrations
│       ├── services/      optimizer_bridge.py (the sync↔async bridge), savings/comparison/alerts
│       ├── realtime/      SSE broadcaster
│       └── scheduler/     APScheduler wrapper
├── dashboard/            Next.js 14 / React 18 / TypeScript — the operator-facing UI
├── packages/contracts/   JSON Schema — forecast / plan / telemetry / alert shapes, frozen
├── infra/                Compose overrides, verification scripts
├── tools/scenariogen/    Authored (never captured) forecast/telemetry fixtures for dev without a
│                         live API key or a finished digital twin
└── docs/
    ├── architecture/      ARCHITECTURE.md, API_CONTRACT.md, DATA_MODEL.md
    ├── design/            FE_DESIGN.md
    ├── phases/             the six-phase build plan
    └── agent/              memory.md (decisions) / mistakes.md (incidents)
```

---

## How it works — the rolling-horizon loop

```
 every tick (default: hourly)
 ┌────────────────────────────────────────────────────────────────────────┐
 │ 1. Fetch the latest forecast (Open-Meteo)                                │
 │ 2. Read the battery's MEASURED charge from telemetry — never from the    │
 │    previous plan's own prediction (this is the one rule that keeps the   │
 │    loop honest: skip it and forecast error never gets corrected)         │
 │ 3. Solve the 24-hour mixed-integer program (below) from that state       │
 │ 4. Persist the plan; execute ONLY hour 0 against the site (digital twin  │
 │    today, real hardware later — same interface, one adapter swapped)     │
 │ 5. Record what actually happened as telemetry                            │
 │ 6. Run the literal greedy rule too, in a shadow ledger, against the      │
 │    IDENTICAL realized weather/load — this is what turns "we saved        │
 │    diesel" into a measured delta instead of a claim                      │
 │ 7. Discard hours 1–23 of the plan; they only existed so hour 0 could be  │
 │    chosen with reserve capacity in mind — next tick's fresher forecast   │
 │    replaces them entirely                                                │
 └────────────────────────────────────────────────────────────────────────┘
```

---

## Architecture

The optimizer is a small Clean Architecture core so its one job — deciding the dispatch — never
depends on which solver, which weather API, or which hardware is behind it.

```
        infrastructure/  (Pyomo+HiGHS · Open-Meteo · digital twin · PostgreSQL)
        ┌───────────────────────────────────────────────────┐
        │  application/  (rolling-horizon service, baseline  │
        │                 shadow service)                     │
        │   ┌─────────────────────────────────────────────┐  │
        │   │  domain/  (Site, Battery, Diesel, Forecast,  │  │
        │   │            DispatchPlan — zero external      │  │
        │   │            imports)                          │  │
        │   └─────────────────────────────────────────────┘  │
        └───────────────────────────────────────────────────┘
              ▲                                    ▲
        backend/ (FastAPI, scheduler, SSE)   dashboard/ (Next.js)
```

Both `backend/` and `dashboard/` talk to `infrastructure/` only, through the same ports `domain/`
declares — this is what let a digital twin stand in for real hardware everywhere in this repo
without either backend or dashboard code knowing the difference. Full detail in
[`docs/architecture/ARCHITECTURE.md`](docs/architecture/ARCHITECTURE.md).

---

## The optimization model

This is the exact mixed-integer program `optimizer/infrastructure/optimizer_pyomo/adapter.py`
solves every tick — not a simplified textbook version. Solved with **HiGHS** via **Pyomo**.

### Sets and indices

```math
t \in \mathcal{T} = \{0, 1, \dots, H-1\} \quad \text{hourly decision steps, } H = 24
```
```math
s \in \mathcal{S} = \{0, 1, \dots, H\} \quad \text{state-of-charge time points (hour boundaries)}
```

### Parameters

| Symbol | Meaning |
|---|---|
| $C$ | battery capacity (kWh) |
| $E_{\min}, E_{\max}$ | usable SoC bounds, $= C \cdot \text{soc\_min\_pct},\ C \cdot \text{soc\_max\_pct}$ |
| $P^{ch}_{\max}, P^{dis}_{\max}$ | max battery charge / discharge power (kW) |
| $\eta$ | one-way (charge or discharge) efficiency, $\eta = \sqrt{\eta_{rt}}$ from the site's round-trip efficiency |
| $P^{d}_{\min}, P^{d}_{\max}$ | diesel minimum and rated load (kW) — the min-load constraint a real generator can't ignore |
| $T^{up}_{\min}, T^{dn}_{\min}$ | minimum consecutive hours the generator must stay on / off once it transitions |
| $c_{start}$ | diesel start cost |
| $c_{deg}$ | battery degradation cost per kWh cycled (charge + discharge) |
| $p_{fuel}$ | fuel price per litre |
| $L^{crit}_t, L^{flex}_t$ | forecast critical / flexible load (kW) at hour $t$ |
| $G_t$ | forecast solar generation (kW) at hour $t$ |
| $G^{p10}_t, G^{p90}_t$ | optional 10th/90th-percentile solar forecast band |
| $E_0$ | **measured** starting SoC, read from telemetry — never from a previous plan |

### Decision variables

```math
x_t \in \{0,1\} \quad \text{diesel on/off}
```
```math
u_t, v_t \in \{0,1\} \quad \text{diesel start / stop indicators}
```
```math
P^{d}_t \in [0, P^{d}_{\max}], \qquad P^{ch}_t \in [0, P^{ch}_{\max}], \qquad P^{dis}_t \in [0, P^{dis}_{\max}]
```
```math
b_t \in \{0,1\} \quad \text{battery charging-mode indicator (mutual exclusion with discharge)}
```
```math
E_s \in [E_{\min}(s),\, E_{\max}] \quad \forall s \in \mathcal{S} \qquad G^{used}_t \in [0, G_t] \qquad U_t \geq 0
```

### Objective — minimize total cost over the horizon

```math
\min \sum_{t \in \mathcal{T}} \Big[\, p_{fuel}\big(m \cdot P^{d}_t + k \cdot x_t\big) \;+\; c_{start} \cdot u_t \;+\; c_{deg}\big(P^{ch}_t + P^{dis}_t\big) \;+\; \pi \cdot U_t \,\Big]
```

where the fuel term is a **linear interpolation of the generator's fuel curve** between its
minimum- and maximum-load operating points (a real diesel genset is markedly less efficient near
its floor — this is why "should diesel run at all this hour" is a genuine optimization question):

```math
m = \frac{P^{d}_{\max} f_{\max} - P^{d}_{\min} f_{\min}}{P^{d}_{\max} - P^{d}_{\min}}, \qquad
k = P^{d}_{\min} f_{\min} - m \cdot P^{d}_{\min}
```

$f_{\min}, f_{\max}$ are litres-per-hour at minimum and maximum load. $\pi$ is a flexible-load
curtailment penalty set high enough that the solver only sheds flexible load when every other
option is genuinely exhausted: $\pi = \max(10,\ 100\, f_{\min}\, p_{fuel})$.

### Constraints

**Initial condition** — the loop's one non-negotiable rule:
```math
E_0 = E_0^{\,measured}
```

**Forecast-uncertainty reserve** *(stretch feature)* — the SoC floor tightens near-term when the
solar forecast is uncertain, instead of using one fixed safety margin:
```math
E_s \geq E_{\min}(s) \qquad \forall s \in \mathcal{S}
```
```math
E_{\min}(s) = \begin{cases} \min\!\big(E_{\max}-\varepsilon,\; E_{\min} + r\big) & s < 12 \\ E_{\min} & \text{otherwise} \end{cases}
\quad\text{where}\quad
r = \min\!\Big(0.3\,(E_{\max}-E_{\min}),\ \tfrac{1}{2}\overline{\Delta G}\Big),\quad
\overline{\Delta G} = \tfrac{1}{12}\sum_{t=0}^{11}\max(0,\, G^{p90}_t - G^{p10}_t)
```

**Diesel minimum-load commitment** — the whole reason diesel is part binary, part continuous:
```math
P^{d}_{\min}\, x_t \;\leq\; P^{d}_t \;\leq\; P^{d}_{\max}\, x_t \qquad \forall t \in \mathcal{T}
```

**Start/stop transition logic**, with $x_{-1}$ = the generator's actual state carried in from the
previous tick:
```math
u_t \geq x_t - x_{t-1}, \qquad v_t \geq x_{t-1} - x_t \qquad \forall t \in \mathcal{T}
```

**Minimum up-time / down-time** — once started, the generator can't be stopped for damage-prevention
reasons before $T^{up}_{\min}$ hours; once stopped, it can't restart before $T^{dn}_{\min}$ hours:
```math
x_\tau \geq u_t \quad \forall\, \tau \in [t,\, t+T^{up}_{\min}), \qquad
1 - x_\tau \geq v_t \quad \forall\, \tau \in [t,\, t+T^{dn}_{\min})
```

**Battery charge/discharge mutual exclusion** (a battery cannot charge and discharge in the same
hour):
```math
P^{ch}_t \leq P^{ch}_{\max}\, b_t, \qquad P^{dis}_t \leq P^{dis}_{\max}\,(1-b_t) \qquad \forall t \in \mathcal{T}
```

**Solar dispatch limit** and **curtailable-load limit**:
```math
G^{used}_t \leq G_t, \qquad U_t \leq L^{flex}_t \qquad \forall t \in \mathcal{T}
```

**Battery state-of-charge dynamics**, with the one-way efficiency $\eta$ applied on both legs:
```math
E_{t+1} = E_t + \eta\, P^{ch}_t - \frac{P^{dis}_t}{\eta} \qquad \forall t \in \mathcal{T}
```

**Energy balance.** This is the load-bearing line in the entire model: notice **$L^{crit}_t$ has no
slack term.** Only $U_t$ — bounded above by $L^{flex}_t$ — can ever absorb a shortfall. Critical
load cannot be dropped by construction, not by a large penalty coefficient that a sufficiently
extreme scenario could still override:
```math
G^{used}_t + P^{dis}_t + P^{d}_t \;=\; L^{crit}_t + L^{flex}_t - U_t + P^{ch}_t \qquad \forall t \in \mathcal{T}
```

### The baseline (shadow) controller — for contrast

The permanent comparison arm (`optimizer/application/baseline_service.py`) is deliberately **not**
an optimization — it's the literal greedy rule, so the saving reported by the dashboard is measured
against something that actually exists at most sites today, not a strawman. Per hour, given
available solar $G$, total load $L = L^{crit}+L^{flex}$, and current energy $E$:

```math
G^{used} = \min(G, L), \qquad \text{surplus} = G - G^{used}
```
```math
\text{if surplus} > 0:\quad P^{ch} = \min\!\Big(\text{surplus},\ P^{ch}_{\max},\ \frac{E_{\max}-E}{\eta}\Big)
```
```math
\text{else:}\quad \text{shortfall} = L - G^{used}, \qquad P^{dis} = \min\!\Big(\text{shortfall},\ P^{dis}_{\max},\ (E-E_{\min})\,\eta\Big)
```

Diesel starts **only** once solar and battery are both exhausted — no lookahead, no reserve held
back for later, exactly the rule the problem statement describes and exactly what GridPilot's
24-hour lookahead is measured against.

---

## Provenance — every number says where it came from

| Badge | Means |
|---|---|
| `LIVE` | Measured from real site telemetry, right now |
| `FORECAST` | Model-projected — a weather forecast, or a plan hour not yet executed |
| `SIMULATED` | Produced by the digital-twin simulator standing in for real hardware |
| `BASELINE` | The greedy shadow controller's output — for comparison only, never the operative plan |

A savings figure always carries `SIMULATED|LIVE` **and** `BASELINE` together — one badge alone would
be a different claim.

---

## Docs index

| Document | Answers |
|---|---|
| [`PRD.md`](PRD.md) | What is this, who is it for, what's built vs. designed vs. excluded |
| [`REPO_STRUCTURE.md`](REPO_STRUCTURE.md) | How the repo is laid out and why |
| [`docs/architecture/ARCHITECTURE.md`](docs/architecture/ARCHITECTURE.md) | The Clean Architecture layering and the ports |
| [`docs/architecture/API_CONTRACT.md`](docs/architecture/API_CONTRACT.md) | Backend ↔ dashboard contract |
| [`docs/architecture/DATA_MODEL.md`](docs/architecture/DATA_MODEL.md) | Column-level schema |
| [`docs/design/FE_DESIGN.md`](docs/design/FE_DESIGN.md) | Dashboard tokens, wireframes, panel states |
| [`docs/phases/README.md`](docs/phases/README.md) | Build order and the parallel dependency graph |
| [`docs/agent/memory.md`](docs/agent/memory.md) | Durable decision log — why is it this way? |
| [`docs/agent/mistakes.md`](docs/agent/mistakes.md) | Dated incident log — what has already gone wrong? |

---

## Team — Vybe

| Person | Owns |
|---|---|
| **Aarin** | ML & integration, dockerization, data — the optimization core end to end, the forecast pipeline, the container setup tying every service together |
| **Dhruvi** | Backend & database — schema, migrations, and the API surface the optimizer and dashboard both depend on |
| **Kavyan** | Backend & database — the ledger, alert rules, and the savings comparison query |
| **Yashita** | Frontend — the dashboard that makes every number legible, badged, and moving in real time |
