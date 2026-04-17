# Batch 1 — Platform Spine (2026-04-17)

Decision record for the first batch of the 6-batch platform buildout.
Shipped 2026-04-16 to 2026-04-17 as 9 PRs (#147--#155).

Links: [[platform thesis 2026-04-15]], [[../../vision/platform_spine_batch1.md|vision/platform_spine_batch1.md]], [[../../vision/platform_object_model.md|vision/platform_object_model.md]]

## What shipped

Batch 1 delivered the **Ops Layer** and **Experience Layer (API)** of the
[[platform thesis 2026-04-15|five-layer platform]]:

- Unified artifact model ([[platform_contracts|contracts.py]])
- Run registry with full CRUD ([[platform_registry|registry.py]])
- REST API — 15 endpoints under `/platform/*` ([[platform_routes_customer_api|platform_routes.py]])
- Three adapters (finance, copies, worlds) ([[platform_adapters|adapters/]])
- CI correctness infrastructure (`ci_local.sh`, `main-health.yml`)
- Codebase hygiene (unused imports, dependency declarations, formatting)

## PR ledger (merge order)

| PR | Title | Scope |
|----|-------|-------|
| #152 | ruff F401 unused imports | Cleanup — 11 errors across 6 files |
| #153 | Promote sklearn/fastapi/uvicorn/httpx/pyarrow to main deps | Cleanup — pyproject.toml |
| #154 | main-health workflow + ci_local.sh + CLAUDE.md CI section | Cleanup — CI infra |
| #155 | ruff format on 25 synthetic+platform files | Cleanup — formatting |
| #147 | Platform contracts | Feature — RunRecord, ArtifactRecord, ScorecardSummary, Provenance, ScenarioSpec, DatasetSpec, enums, JSON schema, 27 tests |
| #148 | Registry extension | Feature — artifacts/scorecards/scenarios/datasets tables, CRUD, cascade delete, derive_run_id, migration, 22 new tests |
| #150 | Platform REST API | Feature — 15 endpoints, Pydantic v2 models, mounted in FastAPI, 21 tests |
| #151 | Platform adapters | Feature — finance/copies/worlds adapters, --register flags, 8 tests |
| #149 | Vision docs + integration tests + smoke script | Feature — vision docs, obsidian notes, 11+14 integration tests, smoke script |

## Why this order

Cleanup PRs landed first to unblock CI — without #152/#153, the test suite
was broken on clean installs even though agents reported green locally (see
[[ci correctness gap 2026-04-17]]). Feature PRs then landed in dependency
order: contracts (#147) before registry (#148) before API (#150) before
adapters (#151). Docs (#149) landed last because it depends on all feature
code being merged.

## What broke

1. **CI correctness gap** — agents reported "683 tests pass" but CI failed
   because `pyproject.toml` was missing runtime deps that were present in
   polluted local envs. See [[ci correctness gap 2026-04-17]].

2. **Cascade merge conflicts** — 5 parallel agents all touched
   `platform/__init__.py`, `artifacts.py`, `artifacts_schema.json`. Each
   merge to main created new conflicts for the remaining PRs. See
   [[cascade merge conflicts 2026-04-17]].

3. **Poetry extras bug** — deps listed in `[tool.poetry.extras]` get
   stripped from PEP 517 core metadata by poetry-core, so `pip install -e .`
   skips them even when they also appear in main deps. Fix: removed the
   redundant `api` extra.

## What we learned

- Local green means nothing without `scripts/ci_local.sh` (throwaway venv).
- Parallel agents must not touch shared files; merge in strict dependency
  order or consolidate into one branch when conflicts cascade.
- Poetry extras interact badly with PEP 517 — keep runtime deps in main
  `[tool.poetry.dependencies]` only.
- The cleanup-first strategy (PRs #152--#155) was correct: it stabilized CI
  before any feature code landed, preventing a compounding mess.

## Platform status after Batch 1

- **Ops Layer** — was "not yet", now **partial**: unified artifact model,
  run registry (SQLite), finance/copies/worlds adapters.
- **Experience Layer API** — was "not yet", now **partial**: 15 REST
  endpoints under `/platform/*`.
- Remaining batches: API clients, benchmark harness, platform UI, customer
  workspace management, dashboard.
