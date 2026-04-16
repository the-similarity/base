# Platform contracts — the cross-pillar object model

The unified platform object model lives in `the_similarity/platform/contracts.py`.
It is the single source of truth for every persisted record across the five
pillars ([[finance_pilot]], synthetic / [[synthetic_contracts]],
[[synthetic_worlds_runner|worlds]], events, nl_ts) plus cross-pillar
evaluation.

## Relationship to legacy `RunArtifact`

`the_similarity/platform/artifacts.py` already defined `RunArtifact` (the on-disk
`artifact.json` shape consumed by the TS worlds runner, the SQLite registry, and
every adapter written so far). The contracts module is **additive** — it does
not replace `RunArtifact`:

- `RunArtifact` remains the canonical on-disk manifest shape.
- `RunRecord` is a strict superset used by the registry and API, adding
  `status` ([[RunStatus|pending/running/succeeded/failed]]) and a free-form
  `pillar` tag.
- `RunRecord.from_run_artifact` and `RunRecord.from_dict` both load the legacy
  shape with sensible defaults (`status=SUCCEEDED`, `pillar` inferred from
  `kind`). Every historical `artifact.json` still loads.

## Dataclasses

| Name | Purpose | FK to |
|------|---------|-------|
| `RunRecord` | Canonical run row (superset of `RunArtifact`) | — |
| `ArtifactRecord` | File-level metadata (content_type, size, sha256) | `RunRecord.run_id` |
| `ScorecardSummary` | Condensed scorecard row indexed by the UI | `RunRecord.run_id` |
| `Provenance` | Reproducibility record, extends synthetic `Provenance` with `env` block | embedded in `RunRecord` |
| `ScenarioSpec` | World/simulation scenario registration | `RunRecord.config` |
| `DatasetSpec` | Dataset registration row | `RunRecord.config` |

## Enums

- `RunKind` — extended from the original four (copies/worlds/sweep/eval) to
  include `finance`, `events`, `nl_ts`. Legacy values are frozen forever —
  removing any would invalidate every `artifact.json` on disk.
- `RunStatus` — linear MVP state machine: `pending -> running -> (succeeded|failed)`.
- `ScorecardKind` — `fidelity / privacy / utility / controllability / calibration / backtest`.

## JSON schema

`the_similarity/platform/platform_schema.json` is the Draft-07 mirror consumed
by TS validators. Every dataclass + enum has a `$defs` entry. The legacy
`the_similarity/platform/artifacts_schema.json` stays in place for `artifact.json`
validation; its `RunKind` enum was extended in lockstep with the Python side.

## Invariants

1. `run_id` is UUID4 hex (32 lowercase chars) and unique across all pillars.
2. All timestamps are ISO-8601 UTC at seconds precision (`iso_now()` in
   `the_similarity/platform/artifacts.py`).
3. All `config` / `summary` / `params` / `metadata` / `thresholds` / `details`
   dicts must be JSON-serializable — no coercion pass, values fail loudly at
   `json.dumps`.
4. Dataclasses are mutable while being built; once persisted, treat as
   immutable and mint a new `run_id` for any mutation.
5. Enum string values are frozen wire values. Additive changes only.

## Tests

`the_similarity/tests/test_platform_contracts.py` — 27 tests covering
round-trip, enum membership, schema shape + enum parity, backward compat with
legacy `RunArtifact` and legacy synthetic `Provenance`, and worlds-runner
provenance ingest (`version` vs `generator_version`).
