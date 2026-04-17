# Platform thesis 2026-04-15

Decision record: reframe from feature-set to platform. Locked after the [[synthetic launch 2026-04-15|synthetic MVP]] shipped.

## What changed

Before: "we're building Synthetic Copies + Synthetic Worlds + an eval scaffold." Three features.

After: **"we're building the Synthetic Environment Layer for World Models."** One platform with primitives.

## Why

A bucket of tools competes on feature parity and gets out-built. A platform competes on the **loop it closes** — generate → evaluate → compare → promote → use — and the registry/eval layer that no competitor can drop into an existing customer stack in a weekend.

## The five layers

1. **Data Layer** — copies, provenance, privacy, fidelity, utility.
2. **World Layer** — headless runners, scenarios, knobs, seeds, telemetry.
3. **Eval Layer** — sweeps, coverage, controllability, benchmark harnesses. *Lock-in.*
4. **Ops Layer** — artifact storage, run registry, dataset/world registries, benchmark history, workspaces. *Platform memory.*
5. **Experience Layer** — CLI, API, 3D renderer, dashboard. *Surfaces.*

## Where the MVP sits

Data ✅ · World ✅ · Eval (partial — worlds side is live, customer-model harness is not) · Ops ✅ partial (unified artifact model, run registry, adapters — [[batch1 platform spine 2026-04-17|Batch 1]]) · Experience (CLI ✅, renderer ✅, API ✅ partial — `/platform/*` endpoints, dashboard ❌).

## Build order

1. [[../../vision/platform.md|Unified artifact model]] — one schema across Python + TS.
2. Run registry — SQLite/DuckDB with `run_id`, `kind`, `config`, `seed`, `artifact_paths`, `summary`, `created_at`.
3. API — `POST /runs`, `GET /runs/:id/artifacts/:name`, `POST /compare`, `POST /sweeps`.
4. Benchmark harness — customer model in, report out.
5. Platform UI — control room, not dashboard. Renderer as one panel.

Every new primitive must ship with its registry entry. Every new scorecard must speak the unified schema. No exceptions.

## The sentence

> Copies are analytical. Headless worlds are evaluable. Rendered worlds are explorable. Eval is the lock-in. The registry is the memory.

See [[../../vision/platform.md|vision/platform.md]] for the full thesis document.
