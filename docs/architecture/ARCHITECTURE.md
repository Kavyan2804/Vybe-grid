# ARCHITECTURE.md

**GridPilot — system architecture**
**Status:** Active — pre-build. Authoritative for how `optimizer/` and `backend/` are layered.
**Implements:** `PRD.md` §4, §8

---

## 1. Why Clean Architecture here

The optimizer is the one component whose correctness the entire product depends on, and it is also
the component most likely to have its concrete technology swapped: the solver might change (HiGHS
today, something else if a horizon grows), the forecast provider might change (Open-Meteo today, a
paid provider at Live-site tier), and the dispatch target *will* change (a simulator today, a real
inverter/genset controller at Live-site tier). None of those swaps should touch the MILP formulation
or the rolling-horizon logic.

**Dependency rule: arrows point inward. Domain depends on nothing.**

```
        ┌─────────────────────────────────────────────────────┐
        │  infrastructure/            interfaces/               │
        │  (adapters — the only place a library is imported)     │
        │                                                        │
        │   ┌───────────────────────────────────────────────┐   │
        │   │  application/  (use-case orchestration)         │   │
        │   │                                                  │   │
        │   │   ┌─────────────────────────────────────────┐   │   │
        │   │   │  domain/   (entities + ports)             │   │   │
        │   │   │  no pyomo · no sqlalchemy · no fastapi    │   │   │
        │   │   └─────────────────────────────────────────┘   │   │
        │   └───────────────────────────────────────────────┘   │
        └─────────────────────────────────────────────────────┘
```

`domain/` defines *what* the system needs (a `Site`, a `DispatchPlan`, a `ForecastPort` interface).
`application/` defines *when and in what order* those things happen (one rolling-horizon tick).
`infrastructure/` supplies *how*, per concrete technology, behind the interfaces `domain/` declared.

This buys one thing that matters more than the diagram: **the MILP formulation and the rolling-horizon
loop can be unit-tested with zero database, zero solver license, and zero network access**, by
injecting fake adapters that implement the same ports. A test that asserts "critical load is never
dropped" (NFR-3) should not need Postgres running to prove it.

---

## 2. Ports — the seam every adapter implements

| Port | Method | Implemented by (Simulated tier) | Implemented by (Live-site tier, `[DESIGN]`) |
|---|---|---|---|
| `ForecastPort` | `get_latest(site_id) -> Forecast` | `OpenMeteoForecastAdapter` | same, or a paid provider |
| `OptimizerPort` | `solve(state, forecast, site_config) -> DispatchPlan` | `PyomoHighsOptimizerAdapter` | same |
| `DispatchPort` | `execute(decision) -> ActualState` | `SimulatorDispatchAdapter` | `ModbusDispatchAdapter` / `MQTTDispatchAdapter` |
| `PlanRepository` | `save(plan)`, `latest(site_id)` | Postgres via SQLAlchemy | unchanged |
| `TelemetryRepository` | `record(actual)`, `latest_soc(site_id)` | Postgres via SQLAlchemy | unchanged |

**The one adapter that changes between tiers is `DispatchPort`.** Everything else — the formulation,
the rolling loop, the persistence shape — is identical whether the thing executing hour 0 is a
physics simulator or a real generator controller. That is the entire point of the boundary.

---

## 3. The rolling-horizon tick, end to end

```
 every tick (default: hourly, driven by backend/src/scheduler)
 ┌──────────────────────────────────────────────────────────────────────┐
 │ 1. ForecastPort.get_latest(site)        → solar + load forecast, 24h │
 │ 2. TelemetryRepository.latest_soc(site) → actual starting state,      │
 │                                             never the previous plan's │
 │                                             own predicted SoC (§4)    │
 │ 3. OptimizerPort.solve(state, forecast,                               │
 │                          site_config)   → 24h DispatchPlan (MILP)     │
 │ 4. PlanRepository.save(plan)             → badged FORECAST            │
 │ 5. DispatchPort.execute(plan.hour[0])    → simulator or real hardware │
 │ 6. TelemetryRepository.record(actual)    → badged LIVE | SIMULATED    │
 │ 7. BaselineService repeats 1–6 in a shadow ledger, greedy rule only,  │
 │    against the SAME realized weather/load — this is what makes a     │
 │    savings number measured rather than claimed (PRD USP 1)           │
 │ 8. Hours 1–23 of the plan are discarded — they existed only so hour  │
 │    0 could be chosen with reserve capacity in mind, and next tick's  │
 │    fresher forecast supersedes them entirely                          │
 └──────────────────────────────────────────────────────────────────────┘
```

## 4. Why the starting SoC must come from telemetry, never from the plan

The single easiest mistake to make in this loop is convenient rather than correct: reusing the
previous plan's own predicted `soc[1]` as this tick's starting state, instead of reading what the
digital twin (or real hardware) actually reports. If the plan feeds itself, forecast error never
gets corrected — a persistent optimistic solar bias would compound silently for days, and the entire
premise of *re-planning on fresh information* stops being true while the dashboard still looks
correct. `TelemetryRepository.latest_soc()` is the only legal source of a tick's starting state, and
this is worth a regression test, not just a comment.

---

## 5. The MILP formulation

Decision variables, for each hour `t` in the horizon `t = 0 … H-1` (`H = 24`, `Δt = 1h`):

| Variable | Domain | Meaning |
|---|---|---|
| `diesel_on[t]` | binary | generator running this hour |
| `diesel_kw[t]` | continuous, `[0, diesel_max_kw]` | generator output |
| `batt_charge_kw[t]`, `batt_discharge_kw[t]` | continuous ≥ 0 | battery power, kept mutually exclusive |
| `soc[t]` | continuous, `[soc_min, soc_max]` | battery state of charge |
| `solar_used[t]` | continuous, `[0, solar_forecast[t]]` | solar dispatched (rest is curtailed) |
| `unmet_flex[t]` | continuous ≥ 0 | curtailable non-critical load left unserved, penalized |

**Critical load has no corresponding slack variable at all.** It is not "penalized heavily" — it is
structurally absent from anything the solver could choose to leave unserved. This is FR-O3 and it is
the single most important modelling decision in the product: a penalty, however large, is still a
choice the solver could make under an extreme enough scenario; an omitted variable is not.

**Constraints, per hour:**

```
diesel_min_kw · diesel_on[t]  ≤  diesel_kw[t]  ≤  diesel_max_kw · diesel_on[t]

soc[t+1] = soc[t] + batt_charge_kw[t]·η_charge·Δt − (batt_discharge_kw[t] / η_discharge)·Δt

solar_used[t] + batt_discharge_kw[t] + diesel_kw[t]
    = critical_load[t] + flexible_load[t] − unmet_flex[t]

diesel minimum run-time / minimum off-time — standard MILP up/down-time constraints (FR-O5)
```

**Objective — minimize, summed over the horizon:**

```
Σ [ diesel_kw[t] · fuel_curve(diesel_kw[t]) · fuel_price
    + Δ(diesel_on[t]) · start_cost
    + (batt_charge_kw[t] + batt_discharge_kw[t]) · degradation_cost_per_kwh
    + unmet_flex[t] · flex_penalty ]
```

`fuel_curve` is a linear interpolation between the generator's fuel-per-kWh at minimum load and at
maximum load — diesel gensets are markedly less efficient near their minimum, which is part of why
"is it worth starting at all this hour" is a real optimization question and not just a threshold.

`degradation_cost_per_kwh` turns battery cycling from a capacity constraint into an economic term:
every kWh thrown at the battery costs something in wear, so the optimizer only cycles it when the
diesel/curtailment it avoids is worth more — this is FR-O4, and it is easy to skip in a first pass
and get numbers that look right for the wrong reason (unlimited free cycling).

## 6. Forecast-uncertainty reserve margin `[STRETCH]`

`ForecastPort.get_latest()` can return a P10/P50/P90 solar band rather than a single series. When it
does, `soc_min` for the *current* tick is raised above the site's hard minimum by an amount
proportional to `(P90 − P10)` for the next few hours — a wide spread (an uncertain, possibly cloudy
afternoon) earns a bigger held-back reserve than a confident forecast does. This is deliberately not
a fixed safety margin picked by hand; it is what makes "forecasts are never perfect" (problem
statement) a modelled quantity instead of a caveat in the README.

## 7. Fallback path — what happens when the solver fails

If `OptimizerPort.solve()` times out, returns infeasible, or the forecast is stale beyond a
configured threshold, `rolling_horizon_service` does **not** retry silently or skip the tick. It:

1. Raises a `SOLVER_FALLBACK_ACTIVE` alert (`PRD.md` §11), immediately, before falling back.
2. Calls the same greedy rule the baseline comparator runs, for **this tick's real dispatch only**.
3. Persists the resulting decision exactly as any other, badged the same way, with `source:
   "fallback"` recorded so it is auditable afterwards.

Critical load is still guaranteed here because the greedy rule also treats it as non-curtailable —
the guarantee does not depend on the MILP succeeding, only on both paths sharing that one property.

## 8. Digital twin vs real hardware — the boundary that must not move

`dispatch_simulator/` and (eventually) `dispatch_hardware/` implement the identical `DispatchPort`
interface and the identical `ActualState` shape. The simulator adds Gaussian noise to solar
production and load relative to their forecasts specifically so that forecast error is a real,
measurable thing during development and backtesting rather than a claim tested only in prose. No
component upstream of `DispatchPort` may special-case which implementation is active — if the
dashboard needs to know, it reads the `SIMULATED`/`LIVE` badge on the telemetry row, never a
site-config flag reinterpreted in the frontend.
