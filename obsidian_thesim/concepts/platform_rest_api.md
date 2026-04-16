# Platform REST API

FastAPI surface over the Ops Layer — third priority of the [[Platform thesis]]
after the unified [[RunArtifact]] contract and the [[Run registry]] (SQLite).

Lives at `the_similarity/platform/api/` as a subpackage:
- `main.py` — app factory (`create_app`), `get_registry` dependency, uvicorn
  launcher (`python -m the_similarity.platform.api`).
- `routes.py` — endpoint handlers.
- `models.py` — Pydantic v2 models that mirror the `RunArtifact` dataclass.
- `__main__.py` — one-liner shim so `python -m ...` resolves.

## Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| GET  | `/healthz` | Smoke test + registry DB sanity + total run count |
| GET  | `/runs` | Newest-first list, optional `kind` filter |
| GET  | `/runs/{run_id}` | Single artifact by id (404 on miss) |
| GET  | `/runs/{run_id}/artifacts/{name}` | Stream artifact file by logical name |
| POST | `/runs/copies` | Run the synthetic copies pipeline, register result |
| POST | `/runs/worlds` | Subprocess Node worlds runner, register result |
| POST | `/runs/sweep` | Subprocess `run-example-sweep.js`, register result |
| POST | `/compare` | Diff two runs' summary dicts |

## Design decisions (frozen)

- **Synchronous** endpoints for MVP. All current runners finish inside a
  single request window (copies <1s, worlds ~2ms, sweep ~1.2s). Background
  jobs come later when something actually blocks.
- **Pydantic mirrors the dataclass** — `RunArtifactModel` exists for OpenAPI
  schema generation, but `RunArtifact` in `artifacts.py` stays the source of
  truth. Adapters `from_artifact` / `to_artifact` delegate to `to_dict`/
  `from_dict` so the serialization contract lives in one place.
- **Registry writes are mandatory**. Every POST that produces a run MUST
  `registry.register(artifact)` before returning. Without the register call
  the run is invisible to downstream consumers (UI, harness).
- **Copies pipeline is in-process**, not subprocess. `routes.py` uses the
  synthetic CLI's public helpers (`load_source`, `build_generator`,
  `run_scorecards`, `write_*`) so we own the `run_dir` directly — the CLI's
  `run(args)` only prints the dir and doesn't return it.
- **Worlds + sweep are subprocess Node**. The worlds engine is TypeScript-
  first (see [[Worlds product architecture]]); crossing the language boundary
  via `subprocess.run` is the only option.
- **Artifact streaming is path-traversal guarded.** Logical names resolve to
  `provenance["run_dir"] / artifact_paths[name]` and the result is checked
  with `is_relative_to(run_dir)` before serving.

## Registry dependency

```python
def get_registry() -> Iterator[RunRegistry]:
    registry = RunRegistry(_resolve_db_path())
    try:
        yield registry
    finally:
        registry.close()
```

One connection per request. SQLite WAL mode (set by `RunRegistry.__init__`)
keeps concurrent requests from blocking at the DB level. Tests override with
`app.dependency_overrides[get_registry]` pointing at a `tmp_path` DB.

## Config

- `THE_SIMILARITY_REGISTRY_DB` — DB path (default `~/.the_similarity/registry.db`
  — matches `python -m the_similarity.platform`).
- `THE_SIMILARITY_API_HOST` / `THE_SIMILARITY_API_PORT` — bind (default
  `0.0.0.0:8787`).
- CORS: `*` for MVP; lock down before any non-dev deploy.

## Running it

```bash
# Default port 8787
python -m the_similarity.platform.api

# Override
python -m the_similarity.platform.api --host 127.0.0.1 --port 9000
THE_SIMILARITY_REGISTRY_DB=/tmp/my.db python -m the_similarity.platform.api
```

## Tests

`the_similarity/tests/test_platform_api.py` — 14 tests using
`fastapi.testclient.TestClient` with a tmp-path registry override. Covers
health, list/get/stream, copies end-to-end against the demo CSV, compare,
and 404/400 paths. Worlds end-to-end is deliberately NOT tested (requires
Node + fractal package).

## Cross-links

- [[RunArtifact]] — the on-disk contract every endpoint emits and reads.
- [[Run registry]] — SQLite store behind `get_registry`.
- [[Platform thesis]] — why the API exists and what it locks in.
- `the_similarity/synthetic/cli.py` — copies pipeline helpers called in-process.
- `the-similarity-fractal/src/sim/headless/runner.js` — worlds subprocess target.
- `the-similarity-fractal/src/eval/run-example-sweep.js` — sweep subprocess target.
