# Benchmark report

Cross-system forecasting benchmark. One table per (dataset, horizon) combo. The Chronos reference row uses published numbers from arxiv 2403.07815v3 and is **not** from a fresh inference run — see Caveats.

### m4_daily — horizon 14

| System | MAE | sMAPE | CRPS | MASE | P10/P90 cov. | median query ms | peak MB |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| seasonal_naive | 19.3000 | 7.067 | 14.5333 | 3.560 | 0.633 | **0.5** | **4.2** |
| the_similarity | **13.1333** | **4.600** | **10.1000** | **2.980** | **0.793** | 32.0 | 152.0 |
| Chronos-T5-small (published, in-domain) | - | - | - | 3.148 | - | - | - |

### nn5_daily — horizon 7

| System | MAE | sMAPE | CRPS | MASE | P10/P90 cov. | median query ms | peak MB |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| seasonal_naive | 0.7733 | 20.367 | 0.6700 | 0.433 | 0.577 | **0.5** | **4.5** |
| the_similarity | **0.4833** | **12.300** | **0.3700** | 0.197 | **0.800** | 23.6 | 112.0 |
| Chronos-T5-small (published, zero-shot) | - | - | - | **0.169** | - | - | - |

### spy_daily — horizon 5

| System | MAE | sMAPE | CRPS | MASE | P10/P90 cov. | median query ms | peak MB |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| seasonal_naive | 2.4100 | 0.550 | 1.9500 | 1.180 | 0.400 | **0.3** | **3.8** |
| the_similarity | **1.8400** | **0.420** | **1.4200** | **0.910** | **0.800** | 18.2 | 92.0 |

## Caveats

- **Chronos numbers are paper-aggregate over the full Monash split**;
  ours are computed on a 100-series subset of each dataset. The two
  numbers are not strictly comparable — treat the Chronos row as a
  ballpark reference, not a head-to-head.
- **All systems run with default config, no tuning.** No hyperparameter
  search, no per-dataset overrides, no ensembling beyond what each
  system does internally.
- **SPY / BTC have no Chronos comparison row** — those instruments are
  not part of the Monash benchmark, so no published number exists.
- **Pretraining contamination warning.** Chronos was pretrained on
  millions of public time series; the paper itself flags M4 (Daily)
  and M4 (Hourly) as Benchmark I (in-domain), meaning the model has
  effectively seen them during training. NN5 (Daily) is the only
  truly zero-shot reference here.
