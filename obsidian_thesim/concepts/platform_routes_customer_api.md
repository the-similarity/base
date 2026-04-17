# Platform routes on the customer-facing API

The [[Platform REST API]] at `the_similarity/platform/api/` was built as a
standalone FastAPI for runner execution (POST /runs/copies, POST /runs/worlds,
etc.). This note covers the **read/write registry surface** exposed on the
customer-facing FastAPI at `the-similarity-api/app/` under the `/platform/*`
prefix.

Why a second surface?
---------------------
The standalone platform API is operator-focused — it executes subprocesses and
writes artifacts. The customer-facing API already serves dashboards, auth,
alerts, terrain, and warehouse data; mounting the platform **registry** there
lets the Next.js UI hit one host for both analogue search and run listings.

The two surfaces **share the same SQLite registry** (pointed at by
`THE_SIMILARITY_REGISTRY_DB`, default `~/.the_similarity/registry.db`), so a
run created via the standalone API's `POST /runs/copies` is immediately
visible via the customer API's `GET /platform/runs`.

File map
--------
- `the-similarity-api/app/platform_routes.py` — router module (all endpoints).
- `the-similarity-api/app/settings.py` — `resolve_registry_db()` helper.
- `the-similarity-api/app/main.py` — `app.include_router(platform_router)` mount.
- `the-similarity-api/tests/test_platform_routes.py` — 21 tests.

Endpoints (all prefixed `/platform`)
------------------------------------
| Method | Path | Purpose |
|--------|------|---------|
| GET  | `/healthz` | Independent liveness (DB reachable) |
| GET  | `/runs` | List runs (filters: `kind`, `pillar`, `status`, `limit`, `offset`) |
| POST | `/runs` | Register a new run record (409 on duplicate) |
| GET  | `/runs/{run_id}` | Fetch a single run (404 on miss) |
| GET  | `/runs/{run_id}/artifacts` | List artifact metadata rows |
| POST | `/runs/{run_id}/artifacts` | Register an artifact row (409 on dup `(run_id, name)`) |
| GET  | `/runs/{run_id}/artifacts/{name}` | Single artifact metadata (not bytes) |
| GET  | `/runs/{run_id}/scorecards` | List scorecard summaries |
| POST | `/runs/{run_id}/scorecards` | Register a scorecard summary |
| GET  | `/scenarios` / `/{id}` | List / fetch scenario specs |
| POST | `/scenarios` | Register a scenario (409 on dup id) |
| GET  | `/datasets` / `/{id}` | List / fetch dataset specs |
| POST | `/datasets` | Register a dataset (409 on dup id) |

Companion tables
----------------
Agent 1's upcoming `platform/contracts.py` adds `RunRecord`, `ArtifactRecord`,
`ScorecardSummary`, `ScenarioSpec`, `DatasetSpec`. Until Agent 2 extends
`RunRegistry` with matching register/list methods, this router maintains
auxiliary SQLite tables in the **same DB file**:

- `artifacts` — PK `(run_id, name)`, columns: path, content_type, size_bytes,
  sha256, created_at.
- `scorecards` — PK `(run_id, name)`, columns: passed, overall_score,
  metrics_json, created_at.
- `scenarios` — PK `scenario_id`, columns: name, description, pillar,
  parameters_json, created_at.
- `datasets` — PK `dataset_id`, columns: name, description, path, schema_json,
  version, created_at.

Schema creation is idempotent via `_ensure_ext_schema()` on every
`get_registry()` dependency call. Once Agent 2's registry extension lands the
inline SQL migrates to `registry.list_artifacts()` / `register_artifact()` etc.
— the **wire contract does not change**.

Design decisions (frozen)
-------------------------
1. **Thin router, no business logic.** Every handler is validate -> registry
   call -> shape. Runner execution stays on the standalone platform API.
2. **POST treats duplicate IDs as 409**, unlike `RunRegistry.register()` which
   upserts. The registry's upsert path supports partial-then-enriched
   workflows; the customer API's POST is a creation verb.
3. **`pillar` and `status` stored inside `provenance`** for backward-compat.
   Existing `RunArtifact` rows predate these fields; the router fills them
   with sensible defaults (`status="complete"`, `pillar=None`) on read.
4. **DatasetSpec uses `schema` on the wire, `columns` in Python.** The
   `schema` JSON key collides with Pydantic v1's deprecated `.schema()`
   method and triggers v2 alias warnings on generic container attributes.
   Translation happens at the router boundary via `_dataset_from_wire` /
   `_dataset_to_wire`.
5. **No auth on `/platform/*` today.** The existing `get_current_user`
   dependency is available; we hold off until the orchestrator decides
   whether the registry surface is public-read or auth-gated.

Testing
-------
`the-similarity-api/tests/test_platform_routes.py` — 21 tests via
`fastapi.testclient.TestClient` with per-test tmp-path SQLite files and the
`get_registry` dependency overridden. Covers:
- health on empty DB.
- empty list responses (not 404) when the parent exists with no children.
- 404s for missing runs / artifacts / scenarios / datasets.
- 409s for duplicate POST on every resource.
- list filter composition (kind + pillar + status + pagination).
- env-var registry path resolution through `resolve_registry_db`.

Run:
```
cd the-similarity-api && python -m pytest tests/ -v
```

Cross-links
-----------
- [[Platform REST API]] — the standalone operator API (runner execution).
- [[RunArtifact]] — canonical on-disk contract.
- [[Run registry]] — SQLite store both surfaces share.
- [[Platform thesis]] — eval-lock-in strategy; registry is the lock.
- `the-similarity-api/app/platform_routes.py` — router implementation.
