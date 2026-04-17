# Finance Operating Product

## What is it?

The finance operating product is a **production-grade analogue forecasting pipeline** where every run is registered, trust-scored, calibration-audited, and reviewable. It turns the similarity engine from a research tool into an operational decision system.

The key difference from a research backtest: every run produces a durable record in the platform registry, with structured metadata that downstream surfaces (CLI, HTTP API, UI) can query, compare, and audit. No run is fire-and-forget.

## The Workflow

```
Load data → Search analogues → Backtest → Score → Review → Decide → Monitor
```

### 1. Load data

Load historical price data from CSV, parquet, or a DataFrame.

```python
from the_similarity.api import load
ts = load("path/to/SPY_daily.csv")
```

**Platform primitive**: `api.load()` — returns a `TimeSeries` with `.values` (numpy array) and `.dates` (optional index).

### 2. Search analogues

Find historical patterns similar to the current market regime.

```python
from the_similarity.api import search
results = search(query=ts.values[-60:], history=ts.values)
results.summary()  # Print top matches with score breakdowns
```

**Platform primitive**: `api.search()` — runs the 9-method tiered pipeline (SAX+MASS prefilter, DTW+Pearson scoring, Tier 2 enrichment).

### 3. Backtest

Run a walk-forward backtest to validate forecast quality. Registration is opt-in via `register=True`.

```python
from the_similarity.api import backtest
report = backtest(
    ts,
    window_size=60,
    forward_bars=20,
    n_trials=100,
    seed=42,
    register=True,        # <-- lands a row in the platform registry
    source_id="spy",      # <-- provenance label
)
print(f"hit_rate={report.hit_rate:.2f} crps={report.crps:.4f}")
print(f"run_id={report.run_id}")  # reference for downstream queries
```

**Platform primitive**: `api.backtest(register=True)` — calls `platform.adapters.finance.register_backtest_run()` under the hood.

### 4. Score (trust + calibration)

The registered run's summary contains headline metrics:

| Metric | What it measures | Good range |
|--------|-----------------|------------|
| `hit_rate` | Directional accuracy (P50 vs actual) | > 0.55 |
| `crps` | Probabilistic forecast quality (lower = better) | < 0.03 |
| `coverage` | Empirical P10-P90 interval coverage | 0.75 - 0.85 |
| `calibration` | Per-percentile observed vs expected frequencies | Close to diagonal |
| `trust_score` | Composite reliability score (0-1) | > 0.6 |
| `calibration_grade` | Letter grade (A-F) for calibration quality | A or B |

**Platform primitives**:
- `trust_score` — computed by `TrustArtifact` (Agent 1 enrichment). Combines hit_rate, calibration error, and coverage into a single [0,1] score.
- `calibration_grade` — computed by `CalibrationArtifact`. Maps average absolute calibration error to a letter grade.

### 5. Review

A `ReviewArtifact` (Agent 2) captures the human or automated review decision:

- **Status transitions**: `pending` → `approved` / `flagged` / `rejected`
- **Risk flags**: automated warnings (e.g. low coverage, calibration drift, regime mismatch)
- **Signal summary**: condensed narrative of what the analogues suggest

**Platform primitive**: `ReviewArtifact` with `review.status`, `review.risk_flags`, `review.signal_summary`.

### 6. Decide

The review status drives downstream action:
- `approved` — the forecast is actionable; propagate to trading signals / alerts
- `flagged` — requires human attention before acting
- `rejected` — discard; the forecast is unreliable for this regime

### 7. Monitor realized outcomes

After the forecast window elapses, compare projected vs actual:

```python
# Future: review.realized_outcome = compare(forecast, actual)
```

This closes the feedback loop — calibration metrics update with real outcomes, not just in-sample backtests.

## How Each Step Maps to Platform Primitives

| Workflow step | API call | Platform primitive |
|--------------|----------|-------------------|
| Load | `api.load()` | `TimeSeries` |
| Search | `api.search()` | `SearchResults` |
| Backtest | `api.backtest(register=True)` | `BacktestReport` + `RunArtifact(kind=FINANCE)` |
| Score | (enriched adapter) | `TrustArtifact` + `CalibrationArtifact` |
| Review | (review API) | `ReviewArtifact` |
| Decide | `review.status` | `RunStatus` |
| Monitor | (future) | `review.realized_outcome` |

## CLI Commands

### Run a single backtest with registration

```bash
export THE_SIMILARITY_REGISTRY_DB=/tmp/finance.db
python -c "
from the_similarity.api import backtest, load
ts = load('path/to/SPY_daily.csv')
r = backtest(ts, window_size=60, forward_bars=20, n_trials=100, seed=42, register=True, source_id='spy')
print(f'run_id={r.run_id} hit_rate={r.hit_rate:.2f} crps={r.crps:.4f}')
"
```

### List finance runs

```bash
python -m the_similarity.platform list --kind finance
```

### Show a specific run

```bash
python -m the_similarity.platform show <run_id>
```

### Compare two runs

```bash
python -m the_similarity.platform compare <run_id_a> <run_id_b>
```

### Run the benchmark CLI (Agent 4)

```bash
# Single symbol benchmark
python -m the_similarity.finance.benchmark run --symbol SPY --n-trials 50 --seed 42

# Multi-symbol sweep
python -m the_similarity.finance.benchmark sweep --symbols SPY,QQQ,IWM --n-trials 50

# Query benchmark results
python -m the_similarity.platform list --kind finance --limit 20
```

### Smoke test

```bash
bash scripts/smoke_finance_operating.sh
```

## What Exists Now vs. What's Next

### Shipped (Batch 1 + Batch 2)

- Walk-forward backtester with 10+ metrics
- Finance adapter: `backtest(register=True)` -> registry row
- Platform registry: SQLite-backed, WAL mode, kind/pillar/status filters
- CLI: list / show / compare
- REST API: /runs, /runs/{id}/artifacts, /compare
- Trust scoring and calibration grading (enriched adapter)
- Review workflow with risk flags and signal summary
- Benchmark CLI: single-run and multi-symbol sweep
- Finance runs browser (Next.js UI)

### What's Next

- **Benchmark harness for customer models**: bring-your-own-forecast and compare against the similarity engine baseline
- **Live monitoring**: real-time pipeline that runs search + project on new bars as they arrive
- **Alert-triggered runs**: when regime detection fires, auto-run a backtest and register the result
- **Realized outcome tracking**: after the forecast window closes, auto-compare forecast vs actual and update calibration
- **Cross-asset regime aggregation**: aggregate signals across correlated assets for portfolio-level views
- **Historical review audit trail**: full history of review status transitions with timestamps and reviewer identity
