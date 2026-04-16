# Platform Registry (RunRegistry)

> 60-second onboarding. The platform's persistent memory — one row per [[run_record]].

## What it is

An SQLite-backed index of every [[run_record]] the platform produces. "Persistent memory" for the [[platform_rest_api]], the CLI, the eval harness, and the UI. Every run that writes an `artifact.json` to disk also lands a row here.

Code: `the_similarity/platform/registry.py` → class `RunRegistry`. CLI entrypoint: `python -m the_similarity.platform`. See also `the_similarity/platform/__main__.py`.

## Why SQLite (and why stdlib-only)

- **Zero setup.** Any developer can `sqlite3 registry.db` and inspect. No Postgres, no migrations framework, no async driver.
- **WAL journal mode.** Set on every connection so concurrent readers never block writers — essential because the orchestrator may spawn many parallel runners.
- **JSON as TEXT, not BLOB.** `config`, `artifact_paths`, `summary`, `provenance` are JSON-encoded text columns. Humans can read them; we lose JSON1 query support but keep the registry portable across sqlite builds.
- **Years of agent churn survivability.** The stdlib sqlite3 module has been stable since Python 2.5; the DB will outlive any given orchestration layer.

## Schema

```sql
CREATE TABLE runs (
    run_id              TEXT PRIMARY KEY,
    kind                TEXT NOT NULL,
    config_json         TEXT NOT NULL,
    seed                INTEGER,
    artifact_paths_json TEXT NOT NULL,
    summary_json        TEXT NOT NULL,
    provenance_json     TEXT NOT NULL,
    created_at          TEXT NOT NULL
);
CREATE INDEX idx_runs_kind_created ON runs (kind, created_at DESC);
```

The composite index covers the hot read path: `WHERE kind = ? ORDER BY created_at DESC LIMIT N`.

## DB path resolution

1. Explicit constructor arg `RunRegistry(db_path)`.
2. `THE_SIMILARITY_REGISTRY_DB` env var (CLI + API surface).
3. Default `~/.the_similarity/registry.db` (parent dirs auto-created).

The default lives under `$HOME` so the registry survives across worktrees and project clones — it is meant to outlive any single check-out.

## Key methods

| method | purpose |
|---|---|
| `register(artifact)` | Upsert on `run_id`. Re-registration is intentional (early partial → later enriched). |
| `get(run_id)` | Fetch one record or `None`. |
| `list(kind=None, limit=100)` | Newest-first slice, optional `RunKind` filter. |
| `compare(run_id_a, run_id_b)` | Diff the `summary` dicts; returns `{a, b, diff}`. |
| `delete(run_id)` | Idempotent; returns `True` if a row was removed. |
| `close()` | Release the sqlite connection. Also runs on context-manager exit. |

## Invariants

- **Upsert on conflict.** Registering the same `run_id` twice does NOT raise — it overwrites. Eval harness may re-register an enriched summary.
- **Not thread-safe.** One `RunRegistry` per thread. Cross-*process* concurrency is fine (WAL).
- **No schema versioning.** YAGNI — add a `schema_version` table if we need a migration later. Current schema is committed-to-memory stable.

## Surfaces on top

- **CLI** — `python -m the_similarity.platform {register,list,show,compare}`. See `the_similarity/platform/__main__.py`.
- **HTTP** — `the_similarity/platform/api/routes.py` wraps every method. See [[platform_rest_api]].
- **Tests** — `the_similarity/tests/test_platform_registry.py` (14 tests), `test_platform_integration.py` (cross-pillar).

## Related

- [[run_record]] — what every row contains
- [[platform_rest_api]] — HTTP wrapper
- [[platform_adapters]] — pillar-specific registrars
- `the_similarity/platform/registry.py`, `the_similarity/platform/__main__.py`
