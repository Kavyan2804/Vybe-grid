# DATA_MODEL.md

**GridPilot — column-level schema**
**Status:** Draft — freezes with `API_CONTRACT.md` at the end of Phase 1.
**Implements:** `PRD.md` §12, `REPO_STRUCTURE.md` §1

---

## 0. The one rule this schema exists to enforce

**What the optimizer decided (PLANNED) and what actually happened (ACTUAL) are separate tables, and
a savings figure is a read-only comparison computed after both persist.**

```
PLANNED                                    ACTUAL
what the optimizer decided                 what really happened
────────────────────────                   ─────────────────────
forecasts                                  telemetry
dispatch_plans (24h, produced per tick)     dispatch_log (executed hour-0 decisions)
                                            baseline_telemetry (shadow greedy run)
                                            baseline_dispatch_log
        │                                          │
        └──────────────────── savings query ───────┘
                    READ-ONLY, after both persist
```

A plan row is never edited once written — a tick that revises the outlook writes a *new* plan row,
superseding the old one by `tick_at`, the same way a corrected ledger entry is a compensating
movement rather than an edit in any system where a claim needs to stay auditable after the fact.

---

## 1. Sites & configuration

### `sites`
| Column | Type | Notes |
|---|---|---|
| `id` | `text` PK | `site-001` |
| `name` | `text` | |
| `timezone` | `text` | IANA name, e.g. `Asia/Kolkata` |
| `config_version` | `int` | bumped on every config change |
| `config` | `jsonb` | battery, diesel, load-shape parameters — see `site-config.schema.json` |
| `created_at` | `timestamptz` | |

### `site_config_history`
| Column | Type | Notes |
|---|---|---|
| `id` | `bigserial` PK | |
| `site_id` | `text` FK → `sites` | |
| `version` | `int` | |
| `config` | `jsonb` | full snapshot at that version |
| `changed_at` | `timestamptz` | |

Every `dispatch_plans` and `telemetry` row names the `config_version` in force when it was produced,
so a savings comparison spanning a config change is at least detectable.

---

## 2. PLANNED domain

### `forecasts`
| Column | Type | Notes |
|---|---|---|
| `id` | `bigserial` PK | |
| `site_id` | `text` FK | |
| `issued_at` | `timestamptz` | when the forecast was fetched |
| `horizon_hours` | `int` | 24 |
| `source` | `text` | `openmeteo \| persistence_fallback` |
| `stale` | `boolean` | true when reused past its expected refresh interval |
| `series` | `jsonb` | array of `{hour, ghi_w_m2, cloud_cover_pct, load_forecast_kw, solar_p10_kw?, solar_p50_kw, solar_p90_kw?}` |

### `dispatch_plans`
| Column | Type | Notes |
|---|---|---|
| `id` | `bigserial` PK | |
| `site_id` | `text` FK | |
| `tick_at` | `timestamptz` | when this solve ran |
| `forecast_id` | `bigint` FK → `forecasts` | the exact forecast this plan was solved against |
| `config_version` | `int` | |
| `starting_soc_kwh` | `real` | read from `telemetry`, never from a previous plan (`ARCHITECTURE.md` §4) |
| `series` | `jsonb` | 24 hourly decisions — see `API_CONTRACT.md` §2 |
| `objective_cost` | `real` | |
| `solver_status` | `text` | `optimal \| feasible \| infeasible \| timeout` |
| `solve_ms` | `int` | |
| `source` | `text` | `milp \| fallback` — see `ARCHITECTURE.md` §7 |

`(site_id, tick_at)` is the natural key; a rolling loop that fires the same tick twice is a bug this
index catches rather than silently duplicating a plan.

```sql
CREATE UNIQUE INDEX dispatch_plans_tick_uniq ON dispatch_plans (site_id, tick_at);
```

---

## 3. ACTUAL domain

### `telemetry`
| Column | Type | Notes |
|---|---|---|
| `id` | `bigserial` PK | |
| `site_id` | `text` FK | |
| `at` | `timestamptz` | |
| `soc_kwh` | `real` | |
| `diesel_on` | `boolean` | |
| `diesel_kw` | `real` | |
| `batt_kw` | `real` | signed — positive charging, negative discharging |
| `solar_kw` | `real` | |
| `load_kw` | `real` | |
| `source` | `text` | `simulator \| hardware \| fallback` |
| `config_version` | `int` | |

`TelemetryRepository.latest_soc(site_id)` is `SELECT soc_kwh FROM telemetry WHERE site_id = $1 ORDER
BY at DESC LIMIT 1` — the only legal source of a tick's starting state.

### `dispatch_log`
| Column | Type | Notes |
|---|---|---|
| `id` | `bigserial` PK | |
| `plan_id` | `bigint` FK → `dispatch_plans` | |
| `hour_index` | `int` | always `0` today — a plan's hour 0 is the only hour ever executed |
| `executed_at` | `timestamptz` | |
| `decision` | `jsonb` | the exact decision sent to `DispatchPort.execute()` |

### `baseline_telemetry` / `baseline_dispatch_log`

Same shape as `telemetry` / `dispatch_log`, `source` fixed to `'baseline'`. Populated every tick by
`baseline_service` against the identical realized weather/load the real (or simulated) run saw —
this identity is what makes a savings figure a measured delta rather than an independent estimate
(`PRD.md` USP 1).

---

## 4. Savings — a query, not a table

```sql
SELECT
  date_trunc('day', t.at) AS day,
  sum(t.diesel_kw)          AS optimized_diesel_kwh,
  sum(b.diesel_kw)          AS baseline_diesel_kwh,
  sum(t.diesel_kw > 0::int) AS optimized_diesel_hours,
  sum(b.diesel_kw > 0::int) AS baseline_diesel_hours
FROM telemetry t
JOIN baseline_telemetry b
  ON b.site_id = t.site_id AND b.at = t.at
WHERE t.site_id = $1 AND t.at BETWEEN $2 AND $3
GROUP BY 1;
```

Fuel litres, cost and CO₂ are derived from `diesel_kwh` via the site's fuel curve and an emission
factor in `config`, applied identically to both sides — the comparison is only meaningful if both
runs are converted to cost/emissions the same way.

---

## 5. Alerts

### `alerts`
| Column | Type | Notes |
|---|---|---|
| `id` | `text` PK | |
| `site_id` | `text` FK | |
| `type` | `alert_type` | the six in `PRD.md` §11 |
| `subject` | `text` NULL | e.g. a counter or slot equivalent, if applicable |
| `state` | `alert_state` | `created → acknowledged → resolved` |
| `title` | `text` | |
| `raised_at` | `timestamptz` | the clock of the thing that raised it (optimizer/telemetry), not the server |
| `received_at` | `timestamptz` | server clock |
| `resolved_at` | `timestamptz` NULL | starts the cooldown |
| `provenance` | `jsonb` | which inputs produced it, with badges |

```sql
CREATE UNIQUE INDEX alerts_open_uniq ON alerts (site_id, type, subject)
  WHERE state <> 'resolved';
```

One lifecycle, one inbox — a new alert type is a `type` value, never a second table.

---

## 6. Deliberately absent

| Absent | Why |
|---|---|
| A stored "savings" column | It would drift from `telemetry`/`baseline_telemetry` the first time either is corrected; §4's query is always the truth |
| `users` / auth tables | No auth in the MVP — single-operator deployment (`API_CONTRACT.md` §9) |
| Grid tariff / billing tables | Off-grid product, `[EXCLUDED]` per `PRD.md` §5 |
| A `dispatch_plans` edit path | Plans are append-only; a revised outlook is a new row at a new `tick_at`, never an update |
