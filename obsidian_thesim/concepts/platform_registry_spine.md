# Platform registry spine

The platform registry (`the_similarity/platform/registry.py`) is SQLite-backed and the single index every downstream surface consults. The "spine" extension adds richer row types and sibling tables on top of the original single-table `RunArtifact` index.

## Why

`RunArtifact` alone collapses too much into `artifact_paths` and `summary` as free-form JSON. The UI, eval harness, and six-pillar filters ([[Vision pillars]]) need SQL-native indexes on pillar, status, artifact list, and scorecard kind. Encoding those in JSON-as-TEXT columns worked for v0 but blocks cheap queries like "newest failed finance runs with a FIDELITY scorecard under 0.8".

## Schema (v1)

| Table | Primary key | Purpose |
|-------|-------------|---------|
| `runs` | `run_id` | v0 columns + `status` (enum) + `pillar` (free text) |
| `artifacts` | `(run_id, name)` | Typed per-file rows with content_type / size / checksum |
| `scorecards` | `(run_id, kind)` | Headline scorecard (overall, passed, thresholds, details) |
| `scenarios` | `scenario_id` | Registered scenario specs (worlds / sweep inputs) |
| `datasets` | `dataset_id` | Registered dataset specs (finance / eval inputs) |

Indexes: `idx_runs_kind_created`, `idx_runs_pillar`, `idx_runs_status`, `idx_artifacts_run_id`, `idx_scorecards_kind`.

## Migration

v0 DBs (only the `runs` table, no `status`/`pillar`, no siblings) are migrated in place on first open. The constructor uses `CREATE TABLE IF NOT EXISTS` for every table plus a guarded `ALTER TABLE ADD COLUMN` that catches `sqlite3.OperationalError` when the column is already present (SQLite has no `ADD COLUMN IF NOT EXISTS`). Legacy rows read back with `status=SUCCEEDED` and `pillar=None`.

## Contracts

See [[synthetic_contracts]] for the v0 `RunArtifact`. New spine types live in `the_similarity/platform/contracts.py`:

- `RunRecord` — superset of RunArtifact with `status` + `pillar`.
- `ArtifactRecord`, `ScorecardSummary`, `ScenarioSpec`, `DatasetSpec` — one dataclass per new table.
- `RunStatus`, `ScorecardKind` — string enums.
- `RunKind` — re-exported from `artifacts.py`, extended with `FINANCE`, `EVENTS`, `NL_TS`.

## Deterministic ids

`derive_run_id(kind, config, seed) -> str` returns a stable 32-char hex (UUID5 under a fixed namespace) so reproducibility tests can assert equality across pipeline reruns. Default id generation stays `uuid4().hex` for non-reproducible runs.

## Relationships

- Legacy `RunRegistry.register / get / list / delete / compare` still accept and return `RunArtifact` — they adapt to `RunRecord` internally.
- [[platform_rest_api]] should grow endpoints mirroring the new list_runs/list_artifacts/get_scorecards methods.
- [[fidelity_scorecard]] and [[privacy_scorecard]] become rows in the `scorecards` table via `register_scorecard`.
