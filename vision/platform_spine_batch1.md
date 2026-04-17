# Platform Spine — Batch 1

> What landed in Batch 1 of the platform spine, what is still outstanding, and the copy-paste smoke script to verify the end-to-end flow on a clean laptop.

Companion to [`vision/platform.md`](./platform.md) (the five-layer thesis) and [`vision/platform_object_model.md`](./platform_object_model.md) (the canonical contracts).

## 1. What landed

Batch 1 is the **Ops Layer spine** — the part that turns "a bucket of runners" into "a platform with a memory."

| Piece | Status | Commit / location |
|---|---|---|
| Unified artifact schema | shipped (PR #143) | `the_similarity/platform/artifacts.py` + `artifacts_schema.json` |
| SQLite run registry + CLI | shipped (PR #144) | `the_similarity/platform/registry.py`, `the_similarity/platform/__main__.py` |
| Platform REST API | shipped (PR #146) | `the_similarity/platform/api/` |
| Copies adapter | shipped — `POST /runs/copies` | `the_similarity/platform/api/routes.py::create_copies_run` |
| Worlds adapter (Node subprocess) | shipped — `POST /runs/worlds` | `the_similarity/platform/api/routes.py::create_worlds_run` |
| Sweep adapter (Node subprocess) | shipped — `POST /runs/sweep` | `the_similarity/platform/api/routes.py::create_sweep_run` |
| Compare-by-summary | shipped | `RunRegistry.compare` + `POST /compare` |
| Cross-pillar integration tests | shipped (this batch) | `the_similarity/tests/test_platform_integration.py` |
| API integration tests | shipped (this batch) | `the-similarity-api/tests/test_platform_integration.py` |
| Smoke script | shipped (this batch) | `scripts/smoke_platform_spine.sh` |
| Platform object-model docs | shipped (this batch) | `vision/platform_object_model.md` |

### Design highlights

- **stdlib sqlite3 only.** No SQLAlchemy, no migrations framework. Humans can inspect with `sqlite3 registry.db`.
- **JSON as TEXT columns.** `config`, `artifact_paths`, `summary`, `provenance` are JSON-encoded text. Readable, portable, reversible.
- **Upsert on `run_id`.** Re-registration is intentional — a runner may land a partial summary early, the eval harness re-registers later with enriched fields.
- **Path-traversal guard.** Artifact streaming (`GET /runs/{id}/artifacts/{name}`) requires the resolved path to be `is_relative_to(run_dir)`. 404 otherwise.
- **Node subprocess for worlds.** The worlds runner is TypeScript-first; the API always crosses the language boundary via a `node runner.js` subprocess and captures stderr in the 500 detail.

## 2. What is still missing (Batch 2+)

| Piece | Why deferred | Expected batch |
|---|---|---|
| Typed `ScenarioSpec` / `DatasetSpec` dataclasses | Today these are Pydantic request models only; the `config` field on `RunRecord` is a free-form dict. Works for now; typed shapes land when the UI starts driving runs. | Batch 2 |
| Dedicated `pillar` column on the registry | Pillar is inferred from `RunKind`. Works for the four kinds we have; needs a column when pillar count grows. | Batch 2 |
| Benchmark harness for customer models | Upload model outputs, score against trusted copies/worlds, return reports. This is where Eval becomes revenue. | Batch 3 |
| Platform UI (control room) | Not a generic dashboard — a control surface for datasets, worlds, sweeps, evals, comparisons. | Batch 4 |
| Async job queue | Every runner still fits in a request window (<2s); background jobs land when something actually blocks. | TBD |
| Postgres / remote registry | SQLite is enough for the foreseeable scale (thousands of runs). Postgres when we host a team instance. | TBD |

## 3. How to verify end-to-end locally

### 3.1 Smoke script (copy-paste)

```bash
bash scripts/smoke_platform_spine.sh
```

The script lives at [`scripts/smoke_platform_spine.sh`](../scripts/smoke_platform_spine.sh). It:

1. Exports `THE_SIMILARITY_REGISTRY_DB=/tmp/spine-smoke.db` so the smoke never touches `~/.the_similarity/registry.db`.
2. Removes any previous smoke DB and initializes a fresh one.
3. Registers one synthetic run per pillar (finance `eval`, `copies`, `worlds`) via `python -m the_similarity.platform register`.
4. Lists runs via `python -m the_similarity.platform list` (global and per-kind).
5. Starts `uvicorn the_similarity.platform.api:app` on `127.0.0.1:8787` in the background.
6. Hits `GET /healthz`, `GET /runs`, `GET /runs?kind=copies` via curl.
7. Kills the uvicorn process.
8. Cleans up the tmp DB on exit.

### 3.2 Expected output (abridged)

```
[smoke] registry db: /tmp/spine-smoke.db
[smoke] registered finance: 8b62e4a9fd1a40b3a0e0f5c6a1b2c3d4
[smoke] registered copies : a1b2c3d4e5f60718293a4b5c6d7e8f90
[smoke] registered worlds : c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0
[smoke] list all:
RUN_ID     KIND     SEED     CREATED_AT             SUMMARY
----------------------------------------------------------------
c0c0c0c0   worlds   1        2026-04-15T19:00:00Z   {"n_ticks":500,"runtime_ms":4821}
a1b2c3d4   copies   7        2026-04-15T18:44:00Z   {"passed":true,"fidelity_score":0.87}
8b62e4a9   eval     42       2026-04-15T18:30:00Z   {"hit_rate":0.62,"crps":0.18}
[smoke] list --kind copies → 1 row
[smoke] list --kind worlds → 1 row
[smoke] list --kind eval   → 1 row
[smoke] starting uvicorn on 127.0.0.1:8787 ...
[smoke] GET /healthz       → 200 {"status":"ok","runs":3,...}
[smoke] GET /runs          → 200 (3 runs)
[smoke] GET /runs?kind=eval → 200 (1 run)
[smoke] stopping uvicorn ...
[smoke] OK
```

### 3.3 Pytest gates

```bash
# Python-side contracts + registry + API via TestClient
python -m pytest the_similarity/tests/test_platform_integration.py -v

# HTTP-level integration (uses fastapi.testclient.TestClient)
cd the-similarity-api && python -m pytest tests/test_platform_integration.py -v

# Full suite — nothing in this batch should regress existing tests
python -m pytest the_similarity/tests/ -v
```

All three gates must pass before merging.

### 3.4 Manual API dogfood

```bash
# In one terminal: start the API (env var isolates from the real registry)
export THE_SIMILARITY_REGISTRY_DB=/tmp/dogfood.db
python -m the_similarity.platform.api --host 127.0.0.1 --port 8787

# In another terminal: hit the routes
curl -s http://127.0.0.1:8787/healthz | jq .
curl -s http://127.0.0.1:8787/runs | jq .

# POST a copies run using the bundled demo CSV
curl -s -X POST http://127.0.0.1:8787/runs/copies \
  -H 'Content-Type: application/json' \
  -d '{
        "input_path": "the_similarity/synthetic/demos/sample.csv",
        "n": 100,
        "seed": 7,
        "generator": "block_bootstrap"
      }' | jq .
```

## 4. Cross-pillar isolation rule

Pillar isolation in Batch 1 is done **at query time via `RunKind`**, not via a dedicated column:

- `registry.list(kind=RunKind.COPIES)` / `GET /runs?kind=copies` — copies only.
- `registry.list(kind=RunKind.WORLDS)` / `GET /runs?kind=worlds` — worlds only.
- `registry.list(kind=RunKind.EVAL)` / `GET /runs?kind=eval` — finance/eval only.
- `registry.list(kind=None)` / `GET /runs` — cross-pillar, newest-first.

The integration test suite asserts this isolation by registering one run per pillar and checking that the filtered list contains exactly the expected `run_id`.

## 5. Who owns what (Batch 1)

| Area | Owner module |
|---|---|
| Contracts (artifacts + schema) | `the_similarity/platform/artifacts.py`, `artifacts_schema.json` |
| Registry (SQLite) | `the_similarity/platform/registry.py` |
| CLI | `the_similarity/platform/__main__.py` |
| API (FastAPI) | `the_similarity/platform/api/` (`main.py`, `routes.py`, `models.py`) |
| Copies adapter | `the_similarity/platform/api/routes.py` + `the_similarity/synthetic/cli.py` |
| Worlds adapter | `the_similarity/platform/api/routes.py` + `the-similarity-fractal/src/sim/headless/runner.js` |
| Sweep adapter | `the_similarity/platform/api/routes.py` + `the-similarity-fractal/src/eval/run-example-sweep.js` |
| Tests | `the_similarity/tests/test_platform_*.py`, `the-similarity-api/tests/test_platform_integration.py` |
| Docs | `vision/platform_object_model.md`, this file, and `obsidian_thesim/concepts/` |

## 6. Links

- Five-layer thesis: [`vision/platform.md`](./platform.md)
- Canonical contract shapes: [`vision/platform_object_model.md`](./platform_object_model.md)
- MVP spec we built against: [`vision/synthetic_copies_worlds_eval_mvp.md`](./synthetic_copies_worlds_eval_mvp.md)
- REST API design note: [`obsidian_thesim/concepts/platform_rest_api.md`](../obsidian_thesim/concepts/platform_rest_api.md)
