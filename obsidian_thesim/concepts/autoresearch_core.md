# autoresearch core — canonical schema for every lane

**Why this note exists.** Every autoresearch lane (retrieval-bench, projector-v2, the Phase 2 foundation bench, the future synthetic-data and JEPA lanes) used to roll its own ledger row shape, its own delta sign convention, its own "what counts as a keep" logic, and its own report structure. That worked at 2–3 lanes; at the Phase 2 target of 5+ lanes it became an accountability hole — reviewers could not compare two lanes without reading source. The `research/autoresearch/core/` package fixes that.

## What lives in `research/autoresearch/core/`

- `ledger.py` — canonical append-only JSONL schema + helpers (`LedgerEntry`, `append_entry`, `iter_entries`, `entries_for_lane`, `latest_run`, `compare_runs`, `append_entries`). Writes to `progress/autoresearch/experiments.jsonl`.
- `metrics_delta.py` — scalar `compute_delta(baseline, candidate, direction=...)` and `paired_bootstrap(...)` (1000 resamples, seed=42 by default). Both are direction-aware so sign of an "improvement" is never ambiguous.
- `gates.py` — declarative `Gate(name, metric, threshold, direction, required)` + `evaluate_gates(deltas=..., gates=...)`. Gates are **data**, not control flow — the full audit surfaces in `GateDecision.gate_results`.
- `report.py` — `LaneReport(...)` renders the canonical markdown layout: Metadata → Slice × arm scorecard → Deltas → Gates → Verdict → Discussion → Open questions → Artifacts. Pure function of its inputs so snapshot tests stay deterministic.
- `rejection_log.py` — `RejectionEntry` + `append_rejection` + `is_rejected` + `get_rejection` + `revisit_ready`. Writes to `progress/autoresearch/rejections.jsonl`. This is the machine-readable memory of killed directions (see [[Rejected directions 414]]).

## Gate vocabulary

- **`direction`**: `"lower_is_better"` (CRPS, calibration error) or `"higher_is_better"` (hit rate, forward-return correlation). Every delta and every gate carries one.
- **`threshold`**: a **signed delta** (candidate − baseline). For `lower_is_better` the gate passes iff `raw_delta <= threshold` (so `-0.005` = "must improve by at least 0.005"). For `higher_is_better` iff `raw_delta >= threshold`. Inclusive at the boundary.
- **`required`**: `True` gates must all pass for `keep=True`. Any required failure flips the decision to `discard` with a reason string. `required=False` gates are advisory — reported but never block.
- Missing metric in `deltas` = failed gate. A required failure blocks keep; an advisory failure is just logged.
- `standard_forecast_gates()` returns the default preset (CRPS improvement required at −0.005; calibration improvement advisory at −0.005).

## Rejection-log concept

The ledger is per-run and granular. The rejection log is **per-direction** and coarser — one entry per killed research direction, carrying:

- `direction_id`: short snake_case ID (`tier2_as_default`, `regime_aware_widening`).
- `lane_id` + `evidence_refs` (list of `run_id` strings from the ledger).
- `summary`: one paragraph — what was tried, what happened, why it was killed.
- `revisit_conditions`: declarative statements describing under what circumstances the direction is worth re-testing (e.g. *"expanded-slice rerun on NVDA/TSLA/BTC shows any regime where Tier 2 improves CRPS"*, *"someone refits the per-regime multiplicative factors against real residuals"*).

`is_rejected(direction_id)` gives a fast short-circuit for discovery agents; `revisit_ready(direction_id, current_state)` does a keyword-match heuristic against the revisit conditions so agents can decide "has the world changed enough to re-test?" without reading prose.

## "Where does a new lane put its output?" — the rule

| Artifact | Location | Canonical schema |
|---|---|---|
| Per-run structured row | `progress/autoresearch/experiments.jsonl` | `LedgerEntry` via `core.ledger.append_entry` |
| Per-run markdown report | `progress/autoresearch/reports/<lane>-<slug>-canonical.md` | `LaneReport.write(...)` from `core.report` |
| Killed direction | `progress/autoresearch/rejections.jsonl` | `RejectionEntry` via `core.rejection_log.append_rejection` |

New lanes import `core.*` directly instead of duplicating the ledger/report/gate logic. Lane code stays responsible only for **producing the lane-specific raw metrics**. The `core` package standardizes the *contract* so downstream tooling (dashboards, discovery agents, decision auditors) can treat every lane uniformly.

The legacy `research/autoresearch/retrieval_bench/{ledger,report,compare}.py` modules carry `.. deprecated::` shims pointing here. They still work for existing callers; new code should not import them.

## Invariants

- **Append-only.** `append_entry` never rewrites. To correct a wrong row, append a new row whose `notes` carries `{"supersedes": "<old_run_id>"}`.
- **Sort-safe timestamps.** All rows use `YYYY-MM-DDTHH:MM:SSZ`, so lexicographic == chronological.
- **Fail-soft readers.** `iter_entries` and `iter_rejections` skip blank / malformed lines so a crashed half-written ledger does not cripple downstream tooling.
- **Deterministic renderer.** `LaneReport.render()` is a pure function — `render() == render()` byte-for-byte. Bootstrap is deterministic given `(seed, n_resamples)`.

## Code paths

- `research/autoresearch/core/__init__.py`
- `research/autoresearch/core/ledger.py`
- `research/autoresearch/core/metrics_delta.py`
- `research/autoresearch/core/gates.py`
- `research/autoresearch/core/report.py`
- `research/autoresearch/core/rejection_log.py`
- Tests: `the_similarity/tests/test_autoresearch_core.py` (46 tests, happy path + edge cases + schema validation per module).

## Related

- [[Experiment report format]] — prior per-lane convention this canonicalises.
- [[Keep-discard thresholds]] — where the gate thresholds come from.
- [[retrieval_bench]] — first lane that uses the canonical layer.
- [[projector_v2]] — second lane ported to canonical.
- [[Rejected directions 414]] — narrative companion to the rejection log.
