---
type: concept
status: active
created: 2026-04-14
---

# Foundation-bench (v1)

A walk-forward measurement lane that benchmarks pretrained time-series
foundation models against the engine on the same slices used by
[[retrieval-bench-tiers]]. **Measurement only** — the engine default is
never changed by this lane.

## Scope

- **Code:** `research/autoresearch/foundation_bench/`
- **Artefacts:** `progress/autoresearch/reports/foundation-bench/*.json`
  (per-cell) + `progress/autoresearch/reports/foundation-bench-v1.md`
  (consolidated)
- **Ledger:** appended to `progress/autoresearch/experiments.jsonl`

## Models

Registered in `research/autoresearch/foundation_bench/models.yaml`:

| id | type | ctx_len | params (M) | cone shape |
| --- | --- | --- | --- | --- |
| timesfm | foundation | 512 | 200 | bootstrap residual |
| chronos | foundation | 512 | 46 | bootstrap residual |
| moirai | foundation | 5000 | 14 | AR(1) Gaussian |
| moment | foundation | 512 | 40 | bootstrap residual |
| wavelet_baseline | classical | 512 | 0 | bootstrap residual (AR(p) on DWT-denoised returns) |

Every foundation adapter ships with a synthetic fallback so the runner
can produce artefacts in offline CI where the pretrained weights are
unreachable. When a fallback fires, the cell is flagged
`status: partial_synthetic_fallback` in both the artefact and the
ledger row. See [[Foundation-model baselines 414]] for the first
numbers.

## Adapter contract

All adapters implement `research.autoresearch.foundation_bench.adapters.base.ForecastAdapter`:

```python
class ForecastAdapter(Protocol):
    name: str
    def predict_quantiles(
        self,
        history: np.ndarray,
        forward_bars: int,
        percentiles: Sequence[int],
    ) -> ForecastResult: ...
```

Walk-forward invariant: the adapter sees `history[:query_start]` only.
Realised forward returns live in `values[query_end:]` and are never
revealed during inference.

`ForecastResult.fallback_reason` is `None` only for the real inference
path. In practice this means `wavelet_baseline` is the only adapter that
never falls back in offline CI (pywt is a core repo dep).

## Fallback primitives

`adapters/base.py` provides two reusable synthetic cones:

- `ar1_cone(history, forward_bars, percentiles)` — closed-form Gaussian
  cone from an AR(1) fit on the log-returns. Used by `moirai` because
  its real output is a parametric mixture.
- `bootstrap_residual_cone(history, forward_bars, percentiles, n_paths)` —
  AR(1) mean + bootstrapped in-sample residuals → empirical quantile
  cone. Used by `timesfm`, `chronos`, `moment`, and the wavelet baseline
  because their real outputs are point forecasts wrapped into quantiles.

## Runner

`research/autoresearch/foundation_bench/run_bench.py` iterates every
`(model × slice × seed)` cell and writes per-cell JSON + a consolidated
markdown report + a ledger row.

CLI knobs:
- `--smoke` uses `n_trials_smoke` (3) instead of `n_trials` (12)
- `--n-trials N` overrides both
- `--slices csv` / `--slice id` filter by slice
- `--model id` (repeatable) filter by model
- `--per-cell-budget-seconds S` hard wall-clock cap per cell; trials
  past the cap are recorded with `status: skipped_budget` and excluded
  from metric aggregation
- `--skip-ledger` / `--skip-report` for ad-hoc re-runs

Metric helpers are **reused** from
`research/autoresearch/retrieval_bench/metrics.py` (CRPS,
calibration error p10-p90, hit rate, runtime summariser). No duplication.

## Synthetic-data fallback

When `--data-root` points at a directory without the expected parquet
files, `load_slice_values` emits a deterministic geometric random walk
tuned per regime (drift + vol lookup). Lets CI produce artefacts even
without the `the-similarity-data` checkout. Real slices override the
synthetic path transparently.

## Decision semantics

The ledger row always has `decision: "measured"` — this lane never
promotes or demotes the engine default. Downstream dashboards should
read `metrics_before` (wavelet_baseline aggregate) and `metrics_after`
(best foundation model aggregate by mean CRPS) to sort runs by
primary-metric delta.

## Cross-lane joining

Slice ids and seed=42 match
`research/autoresearch/retrieval_bench/slices.yaml` exactly — you can
join on `(slice_id, trial_index)` to compare 1A retrieval-bench metrics
with 2A foundation-bench metrics per trial.
