# GridPilot

**Rolling-horizon dispatch optimizer for off-grid microgrids** — plans the solar/battery/diesel mix
24 hours ahead from a weather forecast, executes only the next hour, and re-solves every hour as
forecasts improve. Built to replace the "use solar first, then battery, then diesel" greedy
controller most sites run today, and to prove the saving rather than claim it.

## Start here

| Document | Answers |
|---|---|
| [`PRD.md`](PRD.md) | What is this, who is it for, what's built vs designed vs excluded, tech stack |
| [`REPO_STRUCTURE.md`](REPO_STRUCTURE.md) | How the repo is laid out and why |
| [`docs/architecture/ARCHITECTURE.md`](docs/architecture/ARCHITECTURE.md) | The Clean Architecture layering, the ports, the MILP formulation |
| [`docs/architecture/API_CONTRACT.md`](docs/architecture/API_CONTRACT.md) | Backend ↔ dashboard contract |
| [`docs/architecture/DATA_MODEL.md`](docs/architecture/DATA_MODEL.md) | Column-level schema |
| [`docs/design/FE_DESIGN.md`](docs/design/FE_DESIGN.md) | Dashboard tokens, wireframes, panel states |
| [`docs/phases/README.md`](docs/phases/README.md) | Build order and the parallel dependency graph |

## The idea in one sentence

A forward-looking controller holds some battery capacity back in the morning specifically so it can
capture the midday solar surplus, and uses that reserve to cover the evening peak instead of running
diesel for it — same hardware, same weather, less fuel burned — and GridPilot measures that saving by
running the naive controller in a shadow ledger against the exact same conditions, every hour, so the
number on the dashboard is a comparison, not a claim.

## Status

Pre-build. See `docs/phases/PHASE_0_foundations_and_baseline.md` for the first thing to do.
