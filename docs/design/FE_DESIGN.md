# FE_DESIGN.md

**GridPilot — dashboard design specification**
**Status:** Draft — freezes with the rest of Phase 1's contracts.
**Authoritative for:** `dashboard/`.

---

## 0. What this screen is for

A site technician glances at it a few times a day; an NGO evaluating the site's impact studies it for
longer. Both want the same two things: **what is the site doing right now, and how much is that
saving versus the old way of doing it.**

1. **Every number carries a badge** — `LIVE | FORECAST | SIMULATED | BASELINE` (`PRD.md` §3). No
   exceptions.
2. **The plan and the actual are always shown together, never one standing in for the other.** A
   forecasted hour and an executed hour must be visually distinguishable at a glance.
3. **The saving is the headline, and it is always paired with what it's measured against** — never a
   percentage alone.

---

## 1. Tokens

Defined once as CSS custom properties; components never hard-code a color.

```css
:root {
  --bg: #F5F7F6;
  --surface: #FFFFFF;
  --border: #E3E8E6;

  --text: #111827;
  --text-muted: #4B5563;

  --brand: #0B6E4F;        /* interactive elements only, never a state */

  --ok: #036B4E;
  --warn: #92400E;
  --danger: #B91C1C;
  --info: #1D4ED8;

  /* provenance badges — each measured ≥4.5:1 on --surface */
  --live:      #036B4E;
  --forecast:  #1D4ED8;
  --simulated: #6D28D9;
  --baseline:  #92400E;

  --radius: 16px;
  --radius-control: 10px;
  --mono: "JetBrains Mono", ui-monospace, monospace;
  --sans: "Inter", ui-sans-serif, system-ui, sans-serif;
}
```

`--mono` for every number that changes — SoC%, kW, litres, currency. `--brand` is interactive-only,
never a badge or a state, for the same reason it was ruled that way in prior projects: a `LIVE` badge
sitting next to a primary button in the same green would stop reading as provenance.

---

## 2. Badges

```tsx
<Badge kind="LIVE" />
<BadgeGroup kinds={['SIMULATED', 'BASELINE']} />
```

| Kind | Reads | Means |
|---|---|---|
| `LIVE` | LIVE | measured from real site telemetry, right now |
| `FORECAST` | FORECAST | model-projected — a weather forecast, or an unexecuted plan hour |
| `SIMULATED` | SIMULATED | produced by the digital-twin simulator, standing in for real hardware |
| `BASELINE` | BASELINE | the greedy comparison controller's shadow run — never the operative plan |

10px uppercase text on a 12%-opacity tint of its own color, never a bare dot. A value the dashboard
cannot determine provenance for renders `—`, not an unbadged number.

---

## 3. Overview — `/`

```
┌ Current mix ─────────┐┌ Battery SoC ─────────┐┌ Today's savings vs baseline ─────┐
│ ● Solar   4.1 kW      ││                       ││  Diesel   3.5 h saved            │
│ ● Battery charging    ││    62%    SIMULATED   ││  Fuel     6.2 L saved            │
│ ● Diesel  OFF         ││   [reserve band]      ││  Cost     ₹1,240 saved           │
│                SIMULATED ││                       ││  CO2      16.4 kg avoided        │
└──────────────────────┘└──────────────────────┘│           SIMULATED  BASELINE    │
                                                   └───────────────────────────────────┘
┌ 24h dispatch plan ──────────────────────────────────────────────────────────────────┐
│  stacked area: solar used · battery discharge · diesel · load line · critical floor  │
│  hour 0 shaded solid (executed) — hours 1-23 hatched (forecast, not yet real)         │
│                                                                          FORECAST     │
└───────────────────────────────────────────────────────────────────────────────────────┘
┌ Alerts ───────────────────────────────────────────────────────────────────────────────┐
│  ⚠ Diesel start planned within 2 hours                                    FORECAST     │
└───────────────────────────────────────────────────────────────────────────────────────┘
```

- **The plan chart's hour-0/hour-1+ visual distinction is not decorative.** It is the single most
  important thing this screen has to communicate honestly: a plan is not a promise past the hour that
  has actually run.
- **Savings tile always shows both halves** — the absolute numbers, not a bare percentage — same
  reasoning as a conversion tile that shows the raw count alongside the ratio: "how much" invites
  trust that "21%" alone does not.
- **Reserve band** on the SoC gauge only renders once the uncertainty-aware margin (`[STRETCH]`) is
  built; until then the gauge shows SoC alone, honestly, rather than a fabricated band.

## 4. Plan vs Actual — `/plan`

One chart, two series on the same axis: the plan as it stood at the last tick, and what was actually
measured for the hours that have since executed. The gap between them **is the forecast error**, and
it should be visible rather than smoothed away — a chart that hides the gap is hiding the reason the
rolling loop exists at all.

Below it, when the explainability service (`[STRETCH]`) is built: one line per hour, in plain
language, sourced from the solver's binding constraints — never a templated restatement of the
numbers already on screen.

## 5. Savings — `/savings`

A date-range picker over the `GET /api/savings` query. Two bars per day — optimized vs baseline — for
diesel-hours, fuel, cost and CO₂, each pair badged `SIMULATED|LIVE` + `BASELINE`. A cumulative total
across the selected range sits above the chart, in the same units an NGO would put in a grant report.

## 6. Alerts — `/alerts`

Card per alert: type, plain-language title, both timestamps (`raised_at` from the optimizer/telemetry
clock, `received_at` from the server), provenance line with its badge, acknowledge/resolve buttons.
When the two timestamps differ by more than a few seconds — the loop was interrupted and this alert
is being reported late — the gap is highlighted rather than hidden, the same way a buffered event's
delay is shown rather than smoothed over in any system that has to survive a connectivity gap.

## 7. Panel states

Every panel implements all five, via one shared `Panel` component:

| State | Trigger | Render |
|---|---|---|
| Loading | first fetch pending | skeleton at real dimensions, never a spinner that reflows on load |
| Empty | request ok, nothing to show | `—` plus a one-liner, e.g. "No plan yet for this site" |
| Stale | no SSE update for > 15s | value dims, a `stale 23s` chip appears, **the last value stays on screen** |
| Disconnected | `EventSource` closed | header strip: "Reconnecting…"; panels hold their last value |
| Error | 4xx/5xx | inline, with a `Retry` button; one broken panel must not blank the dashboard |

Stale and Disconnected are not failure states to hide — a site with intermittent connectivity
(`PRD.md` §2, USP 6) will show these often, and they should read as "the loop is fine, the link to
this browser isn't" rather than as a crash.

## 8. Realtime

`lib/sse.ts` — native `EventSource`, one connection per site, opened once and shared by context.
Reconnect with backoff 1s → 2s → 5s → 10s. On reconnect, refetch `/api/overview` once to resync, then
resume streaming. No component fetches on receipt of an SSE event that doesn't carry its own payload.

## 9. Component inventory

| Path | Contents |
|---|---|
| `components/badges/` | `Badge`, `BadgeGroup` — build first |
| `components/panels/` | `Panel` (all five states), `MetricTile`, `SavingsTile` |
| `components/charts/` | `PlanTimelineChart`, `SocChart`, `SavingsChart` |
| `components/alerts/` | `AlertCard`, `AlertList` |
| `lib/` | `api.ts`, `sse.ts`, `money.ts` |

## 10. Accessibility

Body text ≥14px, metric values ≥28px. Contrast ≥4.5:1 for text on surfaces. Never color alone — every
badge is text, every alert has a glyph and a word.
