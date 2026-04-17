# RunRecord (a.k.a. RunArtifact)

> 60-second onboarding. See [[platform_registry]] for storage, [[artifact_record]] for per-file structure.

## What it is

The **canonical on-disk record describing a single run** on the synthetic environment platform. Every runner — finance backtester, synthetic copies generator, headless worlds simulator, evaluation sweep — emits exactly one `RunRecord` (named `RunArtifact` in code) per run.

Code: `the_similarity/platform/artifacts.py` → class `RunArtifact`.

## Why

- **One shape for every pillar.** Copies (pandas pipeline), Worlds (TypeScript runner), Finance (backtester), Eval (harness) all serialize to the same JSON shape so downstream consumers (registry, API, UI) never branch on pillar.
- **Cross-language.** The Python dataclass and `artifacts_schema.json` are hand-kept in lockstep; the TS worlds side validates against the JSON schema without importing Python.
- **Reproducibility first.** `provenance` carries the generator name + version + seed + created_at so any run can be re-executed from the record alone.

## Fields

| field | type | required | purpose |
|---|---|---|---|
| `run_id` | `str` (32-char UUID4 hex) | yes | Primary key in [[platform_registry]] |
| `kind` | `RunKind` enum | yes | One of `copies`, `worlds`, `sweep`, `eval` — drives consumer dispatch |
| `config` | `dict[str, Any]` | yes | Run *inputs* (generator + params, scenario id, etc.) — JSON-safe |
| `seed` | `int \| None` | yes | RNG seed; `None` when not meaningful (e.g. eval over a corpus) |
| `artifact_paths` | `dict[str, str]` | yes | Logical name → relative path inside the run dir ([[artifact_record]]) |
| `summary` | `dict[str, Any]` | yes | Headline numbers safe to index without loading bulk data ([[scorecard_summary]]) |
| `provenance` | `dict[str, Any]` | yes | Generator, version, seed, scenario, created_at — reproducibility record |
| `created_at` | ISO-8601 UTC | yes | Seconds precision; indexed for newest-first queries |

## Invariants

- **Immutable once written.** `write_artifact()` dumps to `artifact.json` with 2-space indent + trailing newline. Callers MUST NOT mutate; re-issuing means new `run_id`.
- **JSON-safe.** Nested `config`, `summary`, `provenance` must contain only JSON-primitive values. No coercion pass — non-serializable values fail loudly at `json.dumps`.
- **Forward-compatible reads.** `RunArtifact.from_dict` ignores unknown keys so an older reader can consume a newer writer's artifact without crashing.

## Lifecycle

```
runner → build RunRecord → write_artifact(run_dir, rec) → RunRegistry.register(rec)
                                              ↓
                                        <run_dir>/artifact.json  (pretty-printed)
                                              ↓
                                        SQLite row in runs table
```

## Example (finance pillar)

```json
{
  "run_id": "8b62e4a9fd1a40b3a0e0f5c6a1b2c3d4",
  "kind": "eval",
  "config": {"symbol": "SPY", "start": "2020-01-01", "end": "2020-06-30", "method": "dtw"},
  "seed": 42,
  "artifact_paths": {"report": "report.md", "forecast": "forecast.parquet"},
  "summary": {"hit_rate": 0.62, "crps": 0.18, "mae": 0.012},
  "provenance": {"generator_name": "backtester", "generator_version": "0.2.1", "seed": 42, "created_at": "2026-04-15T19:05:00+00:00"},
  "created_at": "2026-04-15T19:05:00+00:00"
}
```

## Related

- [[artifact_record]] — the per-file logical entries inside a run dir
- [[scorecard_summary]] — canonical headline numbers block
- [[platform_registry]] — SQLite index keyed on `run_id`
- [[platform_adapters]] — per-pillar conversions into `RunRecord`
- [[synthetic_contracts]] — `Provenance` dataclass the copies side uses
- `the_similarity/platform/artifacts.py`, `the_similarity/platform/artifacts_schema.json`
