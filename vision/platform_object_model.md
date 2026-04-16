# Platform Object Model

> Canonical record of the cross-pillar artifact shape that Batch 1 of the platform spine (contracts + registry + API + adapters) landed. Companion to [`vision/platform.md`](./platform.md) (the five-layer thesis) and [`vision/platform_spine_batch1.md`](./platform_spine_batch1.md) (what shipped in Batch 1, what is still missing, smoke commands).

## 1. Scope

This document is the source of truth for **what every platform object looks like on disk, over the wire, and in the database**. It describes the Python dataclasses currently shipping in `the_similarity/platform/`:

- `RunArtifact`  (== the external-facing `RunRecord`)
- the `artifact_paths` entries  (== the external-facing `ArtifactRecord`)
- the `summary` block  (== the external-facing `ScorecardSummary`)
- the `provenance` block  (embeds either the copies-side `Provenance` dataclass or the worlds-side provenance dict)
- the pillar-specific **config** shapes (== `ScenarioSpec` for worlds, `DatasetSpec` for copies)

Every pillar (finance, copies, worlds, sweep, eval) flows through the same object model. Downstream surfaces (registry, HTTP, UI) never branch on pillar — they only branch on `RunKind`.

## 2. The five contracts

### 2.1 `RunRecord` — unified per-run record

Class: `the_similarity.platform.artifacts.RunArtifact`.

| field | type | required | invariant |
|---|---|---|---|
| `run_id` | `str` (32-char UUID4 hex) | yes | Primary key in the registry. |
| `kind` | `RunKind` (`copies`\|`worlds`\|`sweep`\|`eval`) | yes | Drives consumer dispatch. |
| `config` | `dict[str, Any]` | yes | JSON-safe. See `ScenarioSpec` / `DatasetSpec` below for per-pillar shape. |
| `seed` | `int \| None` | yes | `None` when a seed is not meaningful. |
| `artifact_paths` | `dict[str, str]` | yes | Logical name → relative path inside the run dir. |
| `summary` | `dict[str, Any]` | yes | Headline numbers only; never a substitute for the on-disk scorecard. |
| `provenance` | `dict[str, Any]` | yes | Generator, version, seed, scenario/source identifiers. |
| `created_at` | ISO-8601 UTC (seconds) | yes | Newest-first sort key in the registry. |

**Immutability.** Once `write_artifact(run_dir, record)` has written `<run_dir>/artifact.json`, the record MUST be treated as immutable. Re-issuing means producing a new `run_id`, not mutating an existing record. The registry's upsert path exists for a narrow case: a runner may register a partial summary early, then the eval harness re-registers with enriched fields — **by design, keyed on the same `run_id`.**

**JSON safety.** `to_dict()` emits only JSON-primitive values. `from_dict()` ignores unknown keys (forward-compat). No coercion pass — non-serializable values fail loudly at `json.dumps` rather than silently converting.

### 2.2 `ArtifactRecord` — a single `artifact_paths` entry

Not a standalone dataclass today; lives inline as `dict[str, str]`. Each entry maps a **logical name** (stable) to a **relative path** (may evolve). Canonical names per pillar:

| Pillar | Logical names |
|---|---|
| Copies | `real`, `synth`, `scorecard`, `provenance`, `report` |
| Worlds | `telemetry` |
| Sweep  | `scorecard`, `telemetry` |
| Eval (finance) | `forecast`, `metrics`, `report` |

**Resolution.** `GET /runs/{run_id}/artifacts/{name}` walks `artifact_paths[name]` relative to `provenance["run_dir"]`. The resolved absolute path MUST be `is_relative_to(run_dir)` — path-traversal attempts return 404.

### 2.3 `ScorecardSummary` — the `summary` block

Free-form `dict[str, Any]`. See [`obsidian_thesim/concepts/scorecard_summary.md`](../obsidian_thesim/concepts/scorecard_summary.md) for canonical keys per pillar. Invariants: JSON primitives only, keep under ~1KB per run (stored as a TEXT column in SQLite).

### 2.4 `Provenance` — the `provenance` block

Free-form `dict[str, Any]` that embeds one of:

- **Copies provenance** (`the_similarity.synthetic.contracts.Provenance` dumped to dict): `source_id`, `generator_name`, `generator_version`, `seed`, `created_at`, `params`.
- **Worlds provenance** (emitted by the JS runner as a JSONL `type=provenance` record): `generator_name`, `version`, `seed`, `scenario_name`, `scenario`, `params`, `created_at`.
- **Finance/eval provenance**: `generator_name` (e.g. `"backtester"`), `generator_version`, `seed`, `symbol`, `start`, `end`, `method`, `created_at`.

All three shapes always include `run_dir` (absolute path) after adapter processing. This is the anchor the artifact-streaming endpoint uses to resolve relative paths.

### 2.5 `ScenarioSpec` / `DatasetSpec` — per-pillar `config`

Not enforced as dataclasses in Batch 1; the `config` dict shape is pillar-defined. The HTTP wrapper exposes Pydantic request models that pin the minimum fields:

- **`DatasetSpec`** (copies): `input_path`, `n`, `seed`, `generator` — `the_similarity.platform.api.models.CreateCopiesRunRequest`.
- **`ScenarioSpec`** (worlds): `scenario_path`, `seed`, `steps` — `the_similarity.platform.api.models.CreateWorldsRunRequest`.
- **Sweep spec**: optional `sweep_script` — `the_similarity.platform.api.models.CreateSweepRequest`.
- **Finance spec** (eval): informal today — `symbol`, `start`, `end`, `method`, `seed` are the conventional keys.

When Batch 2 hardens these into typed dataclasses, they will sit alongside `RunArtifact` in `the_similarity/platform/` and be re-exported from the package. Until then, the Pydantic models are the de-facto schema.

## 3. End-to-end flow (per pillar)

```
                ┌─── finance backtester ───┐
                │   the_similarity/core/   │
                │   backtester.py          │
                └──────────┬───────────────┘
                           │ run outputs: forecast.parquet, metrics.json
                           ▼
                ┌─── finance adapter ──────┐
                │   builds RunRecord(      │
                │     kind=EVAL,           │
                │     config={symbol,...}, │
                │     summary={hit_rate,..}│
                │   )                      │
                └──────────┬───────────────┘
                           │ write_artifact → artifact.json
                           │ registry.register(artifact)
                           ▼
   ┌────────── the_similarity/platform/registry.py ──────────┐
   │   SQLite: runs(run_id, kind, config_json, seed,         │
   │                 artifact_paths_json, summary_json,       │
   │                 provenance_json, created_at)             │
   └──────────┬───────────────────────────┬───────────────────┘
              │                           │
              ▼                           ▼
    ┌── CLI ─────────────┐      ┌── HTTP API ────────────────┐
    │ python -m          │      │ the_similarity/platform/   │
    │  the_similarity.   │      │   api/routes.py            │
    │  platform          │      │ GET  /runs                 │
    │  {register,list,   │      │ GET  /runs/{id}            │
    │   show,compare}    │      │ GET  /runs/{id}/artifacts/ │
    └────────────────────┘      │ POST /runs/{copies,worlds, │
                                │      sweep}                │
                                │ POST /compare              │
                                └──────────┬─────────────────┘
                                           ▼
                                  ┌── consumer surfaces ───┐
                                  │  UI, eval harness,      │
                                  │  the-similarity-app,    │
                                  │  Next.js dashboard      │
                                  └─────────────────────────┘
```

The **copies** and **worlds** flows are identical in structure — the only difference is the pipeline box on the left (Python `synthetic.cli` vs. Node `runner.js` subprocess).

## 4. Example `RunRecord` payloads

### 4.1 Finance (eval) example

```json
{
  "run_id": "8b62e4a9fd1a40b3a0e0f5c6a1b2c3d4",
  "kind": "eval",
  "config": {
    "symbol": "SPY",
    "start": "2020-01-01",
    "end": "2020-06-30",
    "method": "dtw"
  },
  "seed": 42,
  "artifact_paths": {
    "forecast": "forecast.parquet",
    "metrics": "metrics.json",
    "report": "report.md"
  },
  "summary": {
    "hit_rate": 0.62,
    "crps": 0.18,
    "mae": 0.012,
    "calibration_error": 0.04
  },
  "provenance": {
    "generator_name": "backtester",
    "generator_version": "0.2.1",
    "seed": 42,
    "symbol": "SPY",
    "start": "2020-01-01",
    "end": "2020-06-30",
    "created_at": "2026-04-15T19:05:00+00:00",
    "run_dir": "/tmp/finance-runs/eval-42-20260415-190500"
  },
  "created_at": "2026-04-15T19:05:00+00:00"
}
```

### 4.2 Copies example

```json
{
  "run_id": "a1b2c3d4e5f60718293a4b5c6d7e8f90",
  "kind": "copies",
  "config": {
    "input_path": "/repo/the_similarity/synthetic/demos/sample.csv",
    "n": 100,
    "seed": 7,
    "generator": "block_bootstrap"
  },
  "seed": 7,
  "artifact_paths": {
    "real": "real.parquet",
    "synth": "synth.parquet",
    "scorecard": "scorecard.json",
    "provenance": "provenance.json",
    "report": "report.md"
  },
  "summary": {
    "passed": true,
    "fidelity_score": 0.87,
    "privacy_score": 0.91,
    "utility_transfer_gap": 0.04
  },
  "provenance": {
    "source_id": "sample",
    "generator_name": "block_bootstrap",
    "generator_version": "0.1.0",
    "seed": 7,
    "created_at": "2026-04-15T18:44:00+00:00",
    "params": {"block_size": 32},
    "run_dir": "/repo/artifacts/copies-runs/block_bootstrap-7-20260415-184400"
  },
  "created_at": "2026-04-15T18:44:00+00:00"
}
```

### 4.3 Worlds example

```json
{
  "run_id": "c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0",
  "kind": "worlds",
  "config": {
    "scenario_path": "/repo/the-similarity-fractal/scenarios/small_village.json",
    "seed": 1,
    "steps": 500
  },
  "seed": 1,
  "artifact_paths": {
    "telemetry": "run.jsonl"
  },
  "summary": {
    "n_ticks": 500,
    "regime_coverage": 0.73,
    "controllability_p_value": 0.01,
    "runtime_ms": 4821
  },
  "provenance": {
    "generator_name": "small_village",
    "version": "0.3.0",
    "seed": 1,
    "scenario_name": "small_village",
    "scenario": {"actors": 40, "cadence": "daily"},
    "params": {},
    "created_at": "2026-04-15T18:50:00+00:00",
    "run_dir": "/repo/artifacts/worlds-runs/worlds-1-20260415-185000"
  },
  "created_at": "2026-04-15T18:50:00+00:00"
}
```

## 5. Cross-pillar isolation

The registry treats every pillar identically — there is no pillar column. **Pillar isolation is done at query time via `RunKind`.**

- `registry.list(kind=RunKind.COPIES)` returns only copies runs.
- `GET /runs?kind=eval` returns only eval/finance runs.
- `compare()` happily diffs two runs of the same *or* different kinds; the caller is responsible for deciding whether that is meaningful.

A run's **pillar is inferred from `kind`**:

| kind    | Pillar |
|---|---|
| `copies` | Data Layer — synthetic copies |
| `worlds` | World Layer — headless simulations |
| `sweep`  | Eval Layer — parameter sweeps over worlds |
| `eval`   | Eval Layer — finance / model evaluation runs |

This mapping is informal today. When Batch 2 adds a dedicated `pillar` column (or promotes `RunKind` to first-class pillars), the migration is additive — existing runs continue to resolve via `kind`.

## 6. JSON schema

The on-disk JSON schema is hand-kept at `the_similarity/platform/artifacts_schema.json`. The TypeScript worlds runner validates against this schema without importing Python. When a field is added to `RunArtifact`, `artifacts_schema.json` MUST be updated in the same commit.

## 7. Related documents

- [`vision/platform.md`](./platform.md) — five-layer platform thesis
- [`vision/platform_spine_batch1.md`](./platform_spine_batch1.md) — what Batch 1 landed, what is missing, smoke commands
- [`obsidian_thesim/concepts/run_record.md`](../obsidian_thesim/concepts/run_record.md)
- [`obsidian_thesim/concepts/artifact_record.md`](../obsidian_thesim/concepts/artifact_record.md)
- [`obsidian_thesim/concepts/scorecard_summary.md`](../obsidian_thesim/concepts/scorecard_summary.md)
- [`obsidian_thesim/concepts/platform_registry.md`](../obsidian_thesim/concepts/platform_registry.md)
- [`obsidian_thesim/concepts/platform_adapters.md`](../obsidian_thesim/concepts/platform_adapters.md)

## 8. Code references (repo-relative)

- `the_similarity/platform/artifacts.py` — `RunArtifact`, `RunKind`, `write_artifact`, `read_artifact`, `new_run_id`
- `the_similarity/platform/artifacts_schema.json` — JSON schema for cross-language validation
- `the_similarity/platform/registry.py` — `RunRegistry`
- `the_similarity/platform/__main__.py` — CLI
- `the_similarity/platform/api/` — FastAPI surface
- `the_similarity/tests/test_platform_artifacts.py`, `test_platform_registry.py`, `test_platform_api.py`, `test_platform_integration.py` — test coverage
