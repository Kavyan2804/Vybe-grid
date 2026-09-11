# Phase 4 — Dashboard & Insights

> **Goal:** Every number the system produces is on screen, badged, and moving; the plan, the actual,
> and the saving are all one glance apart.
> **Status:** Not started — can run concurrently with Phases 2 and 3
> **Owner:** Yashita (frontend)
> **Depends on:** Phase 1 (contracts frozen; shell, badges and `Panel` exist)
> **Demo milestone:** Every panel on every route carries a badge, and the savings tile updates live as
> new ticks land.
> **Key design refs:** [`FE_DESIGN.md`](../design/FE_DESIGN.md) · [`API_CONTRACT.md`](../architecture/API_CONTRACT.md)

## Overview

**You do not need Phases 2 or 3.** Bring up the backend, seed a site, and drive it with
`tools/scenariogen --loop`. Everything rendered here is defined exactly in `API_CONTRACT.md`; if a
shape is missing there, that's a contracts change to raise, not a local guess.

Two ideas carried over deliberately: **provenance is the feature** — a value on screen without a
badge is a bug, not a cosmetic gap — and **the plan/actual distinction must survive contact with a
chart**, because it is the one thing on this dashboard that keeps the rolling-horizon claim honest
rather than decorative.

---

## Tasks

### Task 4.0 — Theme foundation

**Subtasks:**
- [ ] Tokens from `FE_DESIGN.md` §1 in `globals.css`; no hex outside that file
- [ ] The four badge colors, each measured ≥4.5:1 on `--surface`
- [ ] A contrast-verification script in the build

**Checkpoint:** Palette decided and machine-checked.

---

### Task 4.1 — Overview panels

**Subtasks:**
- [ ] Current-mix tile (solar/battery/diesel this hour)
- [ ] SoC gauge with the reserve-margin band (renders empty, honestly, until Phase 2's `[STRETCH]`
      uncertainty band exists)
- [ ] Savings-vs-baseline tile — both absolute numbers, badged `SIMULATED|LIVE` + `BASELINE`
- [ ] 24h plan timeline chart, hour-0 solid / hours-1+ hatched, per `FE_DESIGN.md` §3
- [ ] Alerts strip
- [ ] All five panel states via the shared `Panel`

**Test plan:**
- Every tile shows at least one badge; none renders an unbadged number
- With SSE disconnected, tiles dim and show a `stale` chip while keeping their last value

**Checkpoint:** Every overview tile badged and fed by `plan.updated` / `telemetry.updated`.

---

### Task 4.2 — Plan vs Actual page

**Subtasks:**
- [ ] Two-series chart: the plan as it stood at the last tick vs the measured actual for hours that
      have since executed
- [ ] The gap between them rendered visibly, not smoothed — this is the forecast error, and hiding it
      would hide the reason the rolling loop exists
- [ ] Forecast panel: solar irradiance next 24h, with a P10/P90 band when Phase 2's `[STRETCH]`
      uncertainty forecast exists, absent otherwise
- [ ] `[STRETCH]` Explainability line per hour, sourced from the plan's `reason` field when present

**Test plan:**
- The plan/actual gap is visually distinguishable at 1280×720
- A missing `solar_p10_kw`/`solar_p90_kw` renders no band, not a fabricated one

**Checkpoint:** Plan vs actual renders correctly against a multi-hour backtest fixture.

---

### Task 4.3 — Savings page

**Subtasks:**
- [ ] Date-range picker over `GET /api/savings`
- [ ] Paired bars (optimized vs baseline) for diesel-hours, fuel, cost, CO₂
- [ ] Cumulative total across the selected range, in units suitable for a grant/impact report

**Test plan:**
- Selecting a range with no data renders the panel's empty state, never a zero bar chart

**Checkpoint:** Savings page renders a real multi-day comparison correctly.

---

### Task 4.4 — Alert centre

**Subtasks:**
- [ ] `AlertCard` — type, plain-language title, both timestamps, provenance line, acknowledge/resolve
- [ ] The `raised_at`/`received_at` gap highlighted when it exceeds a few seconds, with a tooltip
      explaining why (a fallback tick, a connectivity gap)
- [ ] Filter tabs — Open / Acknowledged / Resolved, default Open
- [ ] Toast on `alert.created`

**Test plan:**
- A reconciled alert (e.g. `CRITICAL_LOAD_AT_RISK` carrying a fallback provenance) shows the right
  badge combination
- Resolving removes it from Open without a page reload

**Checkpoint:** Toast arrives; card shows provenance and both timestamps; resolve works.

---

### Task 4.5 — Realtime plumbing

**Subtasks:**
- [ ] `lib/sse.ts` — native `EventSource`, one connection per site, shared by context
- [ ] Reconnect with backoff 1s → 2s → 5s → 10s
- [ ] `plan.updated` / `telemetry.updated` replace their object wholesale, no field-level merging
- [ ] On reconnect, refetch `/api/overview` once to resync, then resume streaming

**Test plan:**
- Stopping the backend shows "Reconnecting…"; restarting resyncs without a page reload
- No duplicate connections after five reconnect cycles

**Checkpoint:** Backend restart recovers without a page reload.

---

### Task 4.6 — Fleet view `[DESIGN]`

Not built for the MVP. Specified here so it is stated as future scope rather than implied:

- A card per site, each showing today's savings and current status
- Aggregated portfolio diesel/cost/CO₂ saved across all sites
- Gated on 2+ live or simulated sites reporting to one backend (`PRD.md` §9)

---

## Verification (end of Phase 4)

- [ ] **CP-4.0** Palette decided, recorded, and contrast-checked
- [ ] **CP-4.1** Every overview tile badged and updating from SSE
- [ ] **CP-4.2** Plan vs actual renders the forecast-error gap correctly
- [ ] **CP-4.3** Savings page renders a real comparison
- [ ] **CP-4.4** Toast arrives; card shows provenance and both timestamps; resolve works
- [ ] **CP-4.5** Backend restart recovers without a page reload
- [ ] Layout holds at 1280×720
- [ ] Every panel and every alert card on every route carries a badge — walked all routes

## Open issues / follow-ups

- [ ] Fleet view stays `[DESIGN]` until Phase 3's ledger has run against at least two distinct site
      configs long enough to have something to aggregate
- [ ] Explainability panel (Task 4.2) has no content until Phase 2 Task 2.6 lands — build the slot,
      not a placeholder string
