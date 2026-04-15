# Foundation-bench v1 — scorecard

- **benchmark_id:** `foundation-bench-v1`
- **timestamp:** 2026-04-15T17:50:20Z
- **git_sha:** `da3ebb8`
- **n_trials:** 12
- **seeds:** [42]
- **per_cell_budget_seconds:** 180

Walk-forward quantile-forecast evaluation. Metric helpers reused from `research/autoresearch/retrieval_bench/metrics.py`. Slices are the SPY/BTC subset of retrieval-bench-tiers-v1 so per-trial deltas are joinable with 1A artefacts.

## Per-slice scorecards

### spy-bull-2016-2019

| model | n | skipped | crps | cal | hit | rt_med (s) | rt_p95 (s) | status |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| timesfm | 12 | 0 |  0.0333 |   0.050 |    0.42 |   0.024 |   0.070 | partial_synthetic_fallback |
| chronos | 12 | 0 |  0.0333 |   0.050 |    0.42 |   0.023 |   0.025 | partial_synthetic_fallback |
| moirai | 12 | 0 |  0.0449 |   0.717 |    0.42 |   0.000 |   0.295 | partial_synthetic_fallback |
| moment | 12 | 0 |  0.0333 |   0.050 |    0.42 |   0.029 |   0.035 | partial_synthetic_fallback |
| wavelet_baseline | 12 | 0 |  0.0372 |   0.383 |    0.50 |   0.034 |   0.043 | ok |

### spy-covid-2020

| model | n | skipped | crps | cal | hit | rt_med (s) | rt_p95 (s) | status |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| timesfm | 12 | 0 |  0.1056 |   0.133 |    0.50 |   0.029 |   0.035 | partial_synthetic_fallback |
| chronos | 12 | 0 |  0.1056 |   0.133 |    0.50 |   0.024 |   0.025 | partial_synthetic_fallback |
| moirai | 12 | 0 |  0.1128 |   0.550 |    0.50 |   0.000 |   0.000 | partial_synthetic_fallback |
| moment | 12 | 0 |  0.1056 |   0.133 |    0.50 |   0.026 |   0.033 | partial_synthetic_fallback |
| wavelet_baseline | 12 | 0 |  0.1160 |   0.300 |    0.58 |   0.031 |   0.032 | ok |

### spy-rate-hike-2022

| model | n | skipped | crps | cal | hit | rt_med (s) | rt_p95 (s) | status |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| timesfm | 12 | 0 |  0.0315 |   0.033 |    0.33 |   0.026 |   0.027 | partial_synthetic_fallback |
| chronos | 12 | 0 |  0.0315 |   0.033 |    0.33 |   0.025 |   0.027 | partial_synthetic_fallback |
| moirai | 12 | 0 |  0.0409 |   0.633 |    0.25 |   0.000 |   0.001 | partial_synthetic_fallback |
| moment | 12 | 0 |  0.0315 |   0.033 |    0.33 |   0.023 |   0.037 | partial_synthetic_fallback |
| wavelet_baseline | 12 | 0 |  0.0330 |   0.133 |    0.50 |   0.031 |   0.033 | ok |

### btc-long-run

| model | n | skipped | crps | cal | hit | rt_med (s) | rt_p95 (s) | status |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| timesfm | 12 | 0 |  0.2032 |   0.217 |    0.42 |   0.026 |   0.027 | partial_synthetic_fallback |
| chronos | 12 | 0 |  0.2032 |   0.217 |    0.42 |   0.026 |   0.028 | partial_synthetic_fallback |
| moirai | 12 | 0 |  0.2297 |   0.633 |    0.17 |   0.000 |   0.001 | partial_synthetic_fallback |
| moment | 12 | 0 |  0.2032 |   0.217 |    0.42 |   0.026 |   0.026 | partial_synthetic_fallback |
| wavelet_baseline | 12 | 0 |  0.2470 |   0.300 |    0.33 |   0.030 |   0.030 | ok |

## Cross-slice aggregate (arithmetic mean over slices)

| model | n_cells | mean_crps | mean_cal | mean_hit | mean_rt_med (s) | fallback_cells | explainability |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| timesfm | 4 |  0.0934 |   0.108 |    0.42 |   0.026 | 4 | low |
| chronos | 4 |  0.0934 |   0.108 |    0.42 |   0.024 | 4 | low |
| moirai | 4 |  0.1071 |   0.633 |    0.33 |   0.000 | 4 | low |
| moment | 4 |  0.0934 |   0.108 |    0.42 |   0.026 | 4 | low |
| wavelet_baseline | 4 |  0.1083 |   0.279 |    0.48 |   0.032 | 0 | medium |

## Fallback / budget summary

- Total cells: **20**
- Fully synthetic fallback cells: **16**
- Partial fallback cells: **0**
- Real / classical cells: **4**
- Cells that hit the budget cap: **0**

