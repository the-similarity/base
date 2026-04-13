# Experiment report format

Every autoresearch experiment produces a **standardized JSON report** so results are auditable, machine-readable, and diffable across runs.

## Schema

`research/autoresearch/ledger/experiment-report.schema.json`

### Top-level fields

| Field | Type | Purpose |
|-------|------|---------|
| `report_id` | string | Unique UUID for this report |
| `run_id` | string | Links to the [[Nine-method pipeline\|experiment-ledger]] entry |
| `benchmark_id` | string | Which benchmark manifest was used |
| `lane_id` | string | Which autoresearch lane |
| `timestamp` | datetime | When the report was generated |
| `branch`, `commit` | string | Git provenance |
| `datasets_used` | array | Dataset names evaluated |
| `retrieval_comparison` | object? | Top-K overlap, rank correlation, rank lift |
| `backtest_metrics` | object | Per-dataset before/after breakdown |
| `aggregate_metrics` | object | Mean-aggregated before/after/deltas |
| `recommendation` | enum | `keep` / `discard` / `needs_review` |
| `rationale` | string | Explanation of the recommendation |
| `artifacts` | array | Repo-relative paths to outputs |

### Backtest metrics (per dataset)

Each entry in `backtest_metrics.before` and `backtest_metrics.after`:

- **crps** — Continuous Ranked Probability Score (lower = better)
- **calibration_error** — Average absolute calibration error P10-P90
- **hit_rate** — Fraction of trials within the forecast cone
- **mean_error** — Mean absolute forecast error
- **runtime_seconds** — Wall-clock time

### Recommendation heuristic

The automated recommendation in `report_generator.py` uses CRPS deltas:

- CRPS delta <= -0.005 and no large hit-rate regression --> **keep**
- CRPS delta >= +0.02 --> **discard**
- Otherwise --> **needs_review** (human override expected)

## Generator script

`research/autoresearch/scripts/report_generator.py`

Four public functions:

1. `generate_report(run_id, benchmark_id, metrics_before, metrics_after, ...)` — builds the dict
2. `save_report(report, output_dir)` — writes to `progress/autoresearch/reports/<run_id>.json`
3. `validate_report(report)` — checks against the JSON Schema (returns error list)
4. `compare_reports(report_a, report_b)` — side-by-side delta comparison

## Relationship to existing artifacts

- The **experiment-ledger** (`experiment-ledger.schema.json`) stores per-run metadata and decisions. The report's `run_id` links back to it.
- The **baseline report** (`smoke-baseline-jepa-report.json`) predates this schema; future baselines should use the standardized format.
- Reports land in `progress/autoresearch/reports/` as write-once artifacts.

## See also

- [[Research hub]]
- [[Repo research and docs]]
- `research/autoresearch/README.md`
