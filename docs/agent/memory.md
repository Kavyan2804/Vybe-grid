# memory.md — durable decision ledger

*Why is it this way?*

**Append-only. Entries are superseded, never edited.** Numbered. Whoever makes the call writes the
entry.

**Entry format:**

```
## NNN — <one-line decision>
**Date:** YYYY-MM-DD · **By:** <who> · **Status:** Active | Superseded by NNN

**Decision.** What was decided, in the imperative.
**Reason.** Why, including the alternative that was rejected.
**Forecloses.** What this makes impossible or expensive later.
```

Escalation: if a rule needs to bind every future decision of its kind, it belongs here rather than in
a phase doc's prose. If it should never be violated, promote it further into a project-wide law file
if this project grows one — nothing skips a step.

---

## 001 — Documentation and repo structure modelled on a prior project's discipline
**Date:** 2026-09-11 · **By:** project owner · **Status:** Active

**Decision.** GridPilot's `PRD.md`, `REPO_STRUCTURE.md`, phase docs, `API_CONTRACT.md`,
`DATA_MODEL.md` and `FE_DESIGN.md` follow the structure, tagging discipline
(`[BUILD]/[STRETCH]/[DESIGN]/[EXCLUDED]`), and provenance-badge pattern used on a prior retail
intelligence project, adapted to this domain rather than copied verbatim.

**Reason.** That structure earned its shape under real pressure — a hackathon where every claim had
to survive a judge asking "is this actually real?" The same discipline applies here for a different
reason: a rolling-horizon optimizer's value proposition is a *saved* number (diesel, cost, emissions),
and a saved number is only trustworthy if it's clear what's measured, what's forecast, and what's
simulated. The badge system (`LIVE | FORECAST | SIMULATED | BASELINE`) and the always-on shadow
baseline (PRD USP 1) exist for that reason.

**Forecloses.** Nothing yet — this is the first entry. It sets the expectation that decisions from
here on get written down here rather than re-argued the next time they come up, and that phase docs
stay prospective (unchecked boxes, no fabricated history) until work actually happens.

---

<!-- Next entry starts at 002. Do not renumber or edit an existing entry — supersede it instead. -->
