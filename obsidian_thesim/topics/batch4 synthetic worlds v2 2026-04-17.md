# Batch 4: Synthetic Worlds v2 — Decision Record

**Date:** 2026-04-17
**Batch:** 4 (5 parallel agents)
**Status:** Shipping

## What was decided

Ship four capabilities as a coordinated batch of 5 parallel agents:

| Agent | Scope | Key artifact |
|-------|-------|-------------|
| 1 | [[worlds_scenario_dsl|Scenario DSL]] with presets + schema + loader | `the-similarity-fractal/src/sim/scenarios/` |
| 2 | [[worlds_eval_harness|Eval harness]] for external policies + greedy example | `the-similarity-fractal/src/eval/` |
| 3 | [[worlds_telemetry_export|Telemetry export]] (CSV, diff, enriched metrics) + comparison CLI | `the-similarity-fractal/src/sim/headless/` |
| 4 | Python worlds adapter + scenario sync + API endpoints | `the_similarity/platform/adapters/worlds.py` |
| 5 | Tests, demos, docs (this agent) | `the_similarity/tests/test_worlds_v2_integration.py` |

## Alternatives considered

1. **Sequential delivery** — ship each piece in order, one PR at a time. Rejected
   because each piece is independent and the batch can be parallelized without
   conflict. Sequential delivery would take 5x longer for no benefit.

2. **Monolithic PR** — one agent does everything. Rejected because the scope is
   too large for a single agent session and parallel agents reduce wall-clock
   time from hours to ~30 minutes.

3. **Skip eval harness** — ship scenarios + telemetry + adapter without the
   harness, add eval later. Rejected because the harness is the "so what" —
   without it, worlds are telemetry dumps with no structured quality signal.

## Why this shape

- **Scenario presets** make the platform usable without reading source code.
  A new user runs `--preset stress_test` and gets a meaningful simulation.

- **Eval harness** turns worlds from "generate data" into "evaluate policies."
  This is the pivot from data generation to world models — the harness is the
  hook that makes external agent policies (RL, LLM, hybrid) pluggable.

- **Telemetry export** makes worlds interoperable with standard data tools
  (pandas, Excel, R). JSONL is the internal format; CSV is the exchange format.

- **Platform integration** (adapter + API) means worlds runs appear alongside
  finance and copies runs in the registry, CLI, and eventual UI. One registry
  for all pillars.

## Risks and mitigations

| Risk | Mitigation |
|------|-----------|
| Parallel agents edit shared files | Agent 5 (docs) avoids `_MOC.md`, `.gitignore`, `CHANGELOG.md`, `pyproject.toml` |
| Eval harness is too thin | Ship greedy policy as proof of concept; document limitations honestly |
| Scenario presets don't cover interesting regimes | Presets are hand-authored; automated scenario discovery is on the roadmap |
| JSONL format may change | Format is flat and unversioned; v3 can add a `version` field to rows |

## Related

- `vision/synthetic_worlds_v2.md` — full vision doc
- `vision/synthetic_worlds_eval.md` — v1 eval design note
- [[worlds_scenario_dsl]], [[worlds_eval_harness]], [[worlds_telemetry_export]]
