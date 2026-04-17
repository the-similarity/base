# The Platform — Synthetic Environment Layer for World Models

**Status:** Thesis locked 2026-04-15 (post-MVP).
**Supersedes:** surface-level framings in `synthetic_data_platform.md` and `synthetic_copies_worlds_eval_mvp.md` when the two conflict.

## What we are building

**The Synthetic Environment Layer for World Models.**

Not a copies tool, a sim demo, a 3D app, or a one-off generator. Those are surfaces. The platform is the system underneath.

## External one-liner

> We're building the infrastructure layer for synthetic data and synthetic worlds.

Longer: *"We're building the platform where synthetic datasets and synthetic worlds are generated, evaluated, and operationalized for world-model training and testing."*

## Platform shape (five layers)

### 1. Data Layer
- Synthetic copies
- Provenance
- Privacy audits
- Fidelity and utility scorecards

### 2. World Layer
- Headless worlds
- Scenario configs
- Controllable knobs
- Seeded reproducibility
- Telemetry streams

### 3. Eval Layer *(the lock-in layer)*
- Sweeps
- Controllability tests
- Regime coverage
- Model / agent benchmark harnesses
- Failure analysis

### 4. Ops Layer
- Artifact storage
- Run tracking
- Dataset / world registries
- Benchmark history
- Team / customer workspace management

### 5. Experience Layer
- CLI for power users
- API for integrations
- 3D / browser renderer for exploration
- Reports / dashboard for non-technical users

## The core thesis

- **Copies** are one platform primitive.
- **Worlds** are another platform primitive.
- **Eval is the lock-in layer.**
- The moat is not *"we can generate."* The moat is: **we can generate, control, evaluate, and audit synthetic environments end-to-end.**

## Where the current MVP sits on the platform

- **Data Layer** — block-bootstrap + regime-aware copies, provenance, fidelity/privacy/utility scorecards. ✅ shipped.
- **World Layer** — `small_village` headless runner, knobs, JSONL telemetry. ✅ shipped.
- **Eval Layer** — sweep runner, regime coverage, controllability with permutation p-values. ✅ shipped for worlds; copies scorecards landed in Data Layer.
- **Ops Layer** — ✅ partial — unified artifact model (`platform/contracts.py`), run registry (SQLite, `platform/registry.py`), finance/copies/worlds adapters (`platform/adapters/`). Landed in Batch 1 (2026-04-17, PRs #147--#151). Remaining: benchmark history, team/customer workspace management.
- **Experience Layer** — CLI ✅, renderer ✅ (localhost), API ✅ partial — 15 REST endpoints under `/platform/*` (`the-similarity-api/app/platform_routes.py`, PR #150, 2026-04-17), dashboard ❌.

## Build-next priority order

Ranked by platform leverage, not by feature visibility.

### 1. Unified artifact model
One schema for dataset runs, world runs, sweeps, scorecards, provenance. The Python `Scorecard` + `Provenance` dataclasses and the TS world scorecard already mirror each other — formalize the union into a single cross-language artifact schema.

### 2. Run registry
Every copies/worlds/eval run gets: `run_id`, `kind`, `config`, `seed`, `artifact_paths`, `summary`, `created_at`. SQLite or DuckDB is enough at this stage; Postgres later. Runs become findable, comparable, and promotable.

### 3. API
Thin REST/gRPC surface over the registry and the runners:
- `POST /runs` — create run
- `GET /runs/:id/artifacts/:name` — fetch artifact
- `POST /compare` — compare two runs (delta fidelity, regime coverage delta, controllability drift)
- `POST /sweeps` — launch a sweep

### 4. Benchmark harness for customer models
Upload model outputs or plug in an agent. Run against trusted copies and worlds. Return reports. This is where Eval becomes revenue.

### 5. Platform UI
Not a generic dashboard. A **control room** for datasets, worlds, sweeps, evaluations, comparisons. The 3D renderer is one panel inside it, not the frame.

## The one user workflow

Every surface must roll up to this:

1. Create copies or worlds.
2. Run evaluation.
3. Compare results.
4. Promote trusted artifacts.
5. Use them for training / testing (including agent teams).

If a feature doesn't live on this line, defer it.

## The trap to avoid

Don't let the platform become a bucket of tools. Copies, worlds, sweeps, scorecards — if they live as independent CLIs with no shared registry and no comparison surface, we ship a portfolio, not a platform.

Every new primitive must come with its registry entry. Every new scorecard must speak the unified artifact schema. Every new world scenario must be sweepable through the same eval harness. **The registry is the platform's memory; without it, runs are ephemeral and the moat is imaginary.**

## Messaging discipline

| Audience | Lead with |
|---|---|
| Eng / research / infra | headless runner, telemetry, sweeps, scorecards, determinism, the registry |
| Customers / investors / press | the rendered worlds, the control-room UI, the benchmark harness, end-to-end workflow |

Same platform. Two doors. Don't mix them in one conversation.

## The sentence to memorize

> *Copies are analytical. Headless worlds are evaluable. Rendered worlds are explorable. Eval is the lock-in. The registry is the memory.*
