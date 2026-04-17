# ScorecardSummary (a.k.a. `RunRecord.summary`)

> 60-second onboarding. Part of [[run_record]]. Superset of [[fidelity_scorecard]], [[privacy_scorecard]], [[utility_scorecard]] headline numbers.

## What it is

A **ScorecardSummary** is the small, indexable `summary: Dict[str, Any]` block on every [[run_record]]. It is the "is this run good?" readout the UI shows without loading bulk artifacts (parquet, JSONL, scorecard JSON).

Code: lives inline as `RunArtifact.summary: Dict[str, Any]` in `the_similarity/platform/artifacts.py`. No dataclass today — free-form dict so every pillar picks the headline numbers that matter to them.

## Canonical keys per pillar

| Pillar | Keys (best-effort) |
|---|---|
| Copies | `passed`, `fidelity_score`, `privacy_score`, `utility_transfer_gap` |
| Worlds | `n_ticks`, `regime_coverage`, `controllability_p_value`, `runtime_ms` |
| Sweep  | `n_cells`, `n_rows`, `global_coverage`, `runtime_ms`, `passed` |
| Eval (finance) | `hit_rate`, `crps`, `mae`, `calibration_error` |

See `_copies_summary` in `the_similarity/platform/api/routes.py` for the copies extractor shape.

## Why a free-form dict rather than a typed dataclass

- **Pillar plurality.** Fidelity doesn't apply to finance; hit_rate doesn't apply to copies. A typed union would multiply classes with every new pillar.
- **Forward-compat.** New scorecard versions can add keys without breaking old consumers — UIs that render only known keys continue to work.
- **Diff-friendly.** [[platform_registry]]'s `compare()` iterates the union of summary keys across two runs, returning `(a_value, b_value)` tuples. Free-form dicts plug in directly.

## Invariants

- **JSON primitives only.** `summary` values are serialized via `json.dumps`; anything that fails serialization is a bug in the runner.
- **Small.** Stored as a TEXT column in SQLite. Keep under ~1KB per run. Bulk numbers go in artifact files referenced via [[artifact_record]].
- **Never load-bearing for reproducibility.** Reproducibility lives in `provenance`, not `summary`. `summary` is derived, `provenance` is authoritative.

## Related

- [[run_record]] — the container
- [[fidelity_scorecard]], [[privacy_scorecard]], [[utility_scorecard]] — source scorecards the copies summary aggregates
- [[platform_registry]] — indexes `summary` as a JSON column; drives `compare()`
- `the_similarity/platform/api/routes.py::_copies_summary`
