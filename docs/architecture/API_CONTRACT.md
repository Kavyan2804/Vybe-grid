# API_CONTRACT.md

**GridPilot — backend ↔ dashboard contract**
**Status:** Draft — freezes at the end of Phase 1 (`docs/phases/PHASE_1_the_loop.md`). Additive
changes only after that; a field is added, never renamed.
**Canonical form:** `packages/contracts/` JSON Schemas. This document explains them.

---

## 0. Rules

1. Additive changes only after Phase 1.
2. **Every value the dashboard renders carries one or more badges** from `PRD.md` §3
   (`LIVE | FORECAST | SIMULATED | BASELINE`). A response field without provenance is a bug.
3. Timestamps are ISO-8601 with offset.
4. Energy is kW / kWh as floats; money is a decimal amount plus an explicit currency code — never a
   bare number with an assumed currency.

---

## 1. `GET /api/overview?site_id=`

Everything the landing page needs in one call.

```jsonc
{
  "server_time": "2026-01-14T09:02:11+05:30",
  "site": { "id": "site-001", "name": "Example Village Microgrid" },
  "current": {
    "soc_pct": { "value": 62.4, "badges": ["SIMULATED"] },
    "diesel_on": { "value": false, "badges": ["SIMULATED"] },
    "solar_kw": { "value": 4.1, "badges": ["SIMULATED"] },
    "load_kw": { "value": 3.2, "badges": ["SIMULATED"] }
  },
  "today": {
    "diesel_hours": { "value": 1.5, "badges": ["SIMULATED"] },
    "cost_saved_vs_baseline": { "value": 340.0, "currency": "INR", "badges": ["SIMULATED", "BASELINE"] },
    "fuel_liters_saved_vs_baseline": { "value": 6.2, "badges": ["SIMULATED", "BASELINE"] }
  },
  "unread_alerts": 1
}
```

## 2. `GET /api/plans/latest?site_id=`

The most recent 24-hour dispatch plan.

```jsonc
{
  "plan_id": "plan_000482",
  "forecast_id": "forecast_000482",
  "site_id": "site-001",
  "tick_at": "2026-01-14T09:00:00+05:30",
  "starting_soc_kwh": 12.4,
  "series": [
    {
      "hour": 0,
      "diesel_on": false, "diesel_kw": 0,
      "batt_charge_kw": 1.2, "batt_discharge_kw": 0,
      "soc_kwh": 13.1,
      "solar_used_kw": 3.8, "solar_curtailed_kw": 0.0,
      "unmet_flex_kw": 0.0,
      "executed": true,
      "badges": ["SIMULATED"]
    },
    {
      "hour": 1,
      "diesel_on": false, "diesel_kw": 0,
      "batt_charge_kw": 0.9, "batt_discharge_kw": 0,
      "soc_kwh": 13.7,
      "solar_used_kw": 3.1, "solar_curtailed_kw": 0.0,
      "unmet_flex_kw": 0.0,
      "executed": false,
      "badges": ["FORECAST"]
    }
  ],
  "objective_cost": 812.4,
  "solver_status": "optimal",
  "solve_ms": 4210,
  "fallback_used": false
}
```

`series[0].executed` is `true` only for the hour that has actually run; every later hour is a plan,
not a promise, and is superseded at the next tick. `explanation` (`[STRETCH]`, FR-O9) adds a
`reason: string` per hour when the explainability service is built.

## 3. `GET /api/telemetry?site_id=&range=`

Historical actual state — the ACTUAL domain, never the plan.

```jsonc
{
  "site_id": "site-001",
  "points": [
    { "at": "2026-01-14T09:00:00+05:30", "soc_kwh": 13.1, "diesel_on": false,
      "diesel_kw": 0, "batt_kw": 1.2, "solar_kw": 3.8, "load_kw": 2.6,
      "source": "simulator", "badges": ["SIMULATED"] }
  ]
}
```

`source` ∈ `simulator | hardware | fallback`. `fallback` marks a tick where `SOLVER_FALLBACK_ACTIVE`
fired and the greedy rule produced this row instead of the MILP.

## 4. `GET /api/forecasts/latest?site_id=`

```jsonc
{
  "site_id": "site-001",
  "issued_at": "2026-01-14T08:45:00+05:30",
  "horizon_start": "2026-01-14T09:00:00+05:30",
  "horizon_end": "2026-01-15T09:00:00+05:30",
  "horizon_hours": 24,
  "source": "openmeteo",
  "stale": false,
  "series": [
    { "hour": 0, "ghi_w_m2": 210, "cloud_cover_pct": 40, "load_forecast_kw": 2.9,
      "solar_p10_kw": 0.6, "solar_p50_kw": 1.1, "solar_p90_kw": 1.5 }
  ],
  "badges": ["FORECAST"]
}
```

`solar_p10_kw` / `solar_p90_kw` are present only when the uncertainty-aware reserve margin
(`[STRETCH]`, FR-O8) is built; until then the series carries `solar_p50_kw` alone and the dashboard's
forecast-uncertainty band renders empty rather than fabricated.

`source: "persistence_fallback"` with `stale: true` marks a forecast reused because the live API was
unreachable — badged `FORECAST` still, since it is model output, but never conflated with a fresh
read (`PRD.md` §15 risk: weather API outage).

## 5. `GET /api/savings?site_id=&range=`

The comparison — computed read-only, after both the real (or simulated) ledger and the baseline
shadow ledger persist for the range requested.

```jsonc
{
  "site_id": "site-001",
  "range": { "from": "2026-01-14T00:00:00+05:30", "to": "2026-01-15T00:00:00+05:30" },
  "optimized":  { "diesel_hours": 1.5, "fuel_liters": 3.1, "cost": 620.0, "co2_kg": 8.2 },
  "baseline":   { "diesel_hours": 5.0, "fuel_liters": 9.3, "cost": 1860.0, "co2_kg": 24.6 },
  "saved":      { "diesel_hours": 3.5, "fuel_liters": 6.2, "cost": 1240.0, "co2_kg": 16.4 },
  "badges": ["SIMULATED", "BASELINE"]
}
```

**This is USP 1 made concrete.** Both `optimized` and `baseline` are measured over the identical
weather and load realization for the range; `saved` is their difference, never an independently
modelled estimate.

## 6. Alerts

### `GET /api/alerts?site_id=&state=open|acknowledged|resolved`

```jsonc
{
  "unread": 1,
  "alerts": [
    {
      "id": "alr_...",
      "type": "DIESEL_REQUIRED_SOON",
      "site_id": "site-001",
      "state": "created",
      "title": "Diesel start planned within 2 hours",
      "raised_at": "2026-01-14T09:00:00+05:30",
      "received_at": "2026-01-14T09:00:04+05:30",
      "payload": {},
      "acknowledged_at": null,
      "resolved_at": null,
      "cooldown_until": null,
      "badges": ["FORECAST"]
    }
  ]
}
```

`type` ∈ the six in `PRD.md` §11. Lifecycle `created → acknowledged → resolved`, shared by every
type.

### `POST /api/alerts/:id/acknowledge` · `POST /api/alerts/:id/resolve`

```jsonc
{ "id": "alr_...", "state": "acknowledged" }
```

## 7. Site configuration

### `GET /api/sites` · `POST /api/sites/import` (multipart YAML)

```jsonc
// 201
{ "site_id": "site-001", "config_version": 3 }
```

Config changes are versioned, never overwritten in place — a plan or telemetry row always names the
`config_version` it was produced under, so a savings comparison across a config change is at least
detectable rather than silently misleading.

## 8. Realtime — SSE, and only SSE

### `GET /api/events/stream?site_id=`

```
event: plan.updated
data: { ...the plan object from §2... }

event: telemetry.updated
data: { ...the latest point from §3... }

event: alert.created
data: { ...the alert object from §6... }

: keep-alive
```

No WebSocket library, no broker — one direction, one connection, matching `PRD.md` §4's transport
decision.

## 9. Errors

```jsonc
{ "error": "machine_readable_code", "message": "human sentence", "detail": {} }
```

`400` validation · `404` unknown site/plan/alert · `409` illegal alert-lifecycle transition ·
`422` schema rejection · `500` unexpected.

No authentication in the MVP — single-operator, LAN or single-tenant deployment. Multi-site / fleet
access control is `[DESIGN]` alongside the fleet view itself (`PRD.md` §9).
