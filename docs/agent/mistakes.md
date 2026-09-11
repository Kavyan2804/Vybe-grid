# mistakes.md — dated incident log

*What has already gone wrong?*

**Append-only.** Whoever hits it writes it. No blame, no narrative — symptom, root cause, rule.

An entry here is a cheap way to stop the second occurrence. The expensive alternative is
rediscovering the same failure during a demo or, worse, at a real site.

**Entry format:**

```
## YYYY-MM-DD — <one-line symptom>
**Symptom.** What was observed, including what looked fine and wasn't.
**Root cause.** The actual mechanism.
**Rule.** What now prevents it, and where that rule lives.
```

Escalation: if the rule needs to bind future decisions, promote it to `memory.md`.

---

## Known in advance — failure modes to design against from day one

These have not happened on this project yet. They are recorded here because each is a well-known
failure mode in this exact class of system, and the rule that prevents each is cheaper to build in
from Phase 0 than to retrofit after a plan reaches a real generator.

### A rolling loop that trusts its own prior prediction stops correcting for forecast error
**Risk.** If the next tick's starting SoC is read from the previous plan's own trajectory instead of
measured telemetry, a persistent forecast bias compounds silently — the dashboard keeps looking
correct while the plan drifts further from reality every hour.
**Rule.** `TelemetryRepository.latest_soc()` is the only legal source of a tick's starting state.
`ARCHITECTURE.md` §4.

### A penalty is not a guarantee
**Risk.** Modelling critical load as "heavily penalized if unmet" rather than structurally
unable-to-be-unmet means an extreme enough scenario can still make the solver choose to drop it,
because a large penalty is still a choice with a price.
**Rule.** Critical load has no slack variable in the formulation at all — not a large coefficient, an
absent one. `ARCHITECTURE.md` §5, `PRD.md` FR-O3.

### A savings number without an identical-conditions comparison is an estimate wearing a measurement's clothes
**Risk.** Comparing an optimized run's performance on one day against a baseline's historical average
on other days looks like a saving but measures weather variance, not controller quality.
**Rule.** The baseline runs every tick against the exact same realized weather and load the real (or
simulated) system saw. `DATA_MODEL.md` §0, `PRD.md` USP 1.

---

*No incidents yet from actual build work. This file grows from here.*
