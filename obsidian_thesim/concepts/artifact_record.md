# ArtifactRecord (a.k.a. `artifact_paths` entries)

> 60-second onboarding. Part of [[run_record]].

## What it is

An **ArtifactRecord** is a single entry in `RunRecord.artifact_paths` — a `(logical_name, relative_path)` pair pointing at one file produced by a run. A run typically has several: `real.parquet`, `synth.parquet`, `scorecard.json`, `provenance.json`, `report.md`, `telemetry.jsonl`, etc.

Code: lives inline in `the_similarity/platform/artifacts.py` as `RunArtifact.artifact_paths: Dict[str, str]`; not a standalone dataclass today.

## Why logical name → path

- **Schema stability.** Downstream consumers look up `"scorecard"`, not `"runs/foo/scorecard-v3.json"`. Runners can change on-disk layout without breaking the UI or API.
- **Portability.** Paths are stored *relative to the run dir*. Moving / rehosting a whole run dir preserves all artifact references.
- **API streaming.** `GET /runs/{run_id}/artifacts/{name}` resolves the logical name via `artifact_paths[name]` and serves the file — no path-traversal because the resolved absolute path is required to stay inside the run dir (see `_resolve_artifact_file` in `the_similarity/platform/api/routes.py`).

## Canonical logical names per pillar

| Pillar | Names we always emit |
|---|---|
| Copies | `real`, `synth`, `scorecard`, `provenance`, `report` |
| Worlds | `telemetry` (JSONL stream) |
| Sweep  | `scorecard`, `telemetry` |
| Eval (finance) | `forecast`, `metrics`, `report` |

## Invariants

- **Relative paths only (preferred).** The run_dir anchor for resolution comes from `provenance["run_dir"]`; absolute paths are tolerated only if the file exists on disk and the caller does not need portability.
- **Path-traversal guard.** Resolved paths MUST be `is_relative_to(run_dir)`; otherwise the API returns 404 rather than leak out-of-dir files.
- **Missing file ≠ missing name.** Both surface as 404 through the API — we do not distinguish because the distinction would leak registry internals.

## Related

- [[run_record]] — the container
- [[platform_registry]] — indexes `artifact_paths` as a JSON column
- `the_similarity/platform/api/routes.py` — `_resolve_artifact_file` + `GET /runs/{run_id}/artifacts/{name}`
- `the_similarity/platform/artifacts_schema.json` — JSON schema
