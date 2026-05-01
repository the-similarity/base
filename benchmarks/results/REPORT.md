# Benchmark report

Cross-system forecasting benchmark. One table per (dataset, horizon) combo. The Chronos reference row uses published numbers from arxiv 2403.07815v3 and is **not** from a fresh inference run — see Caveats.

### m4_daily — horizon 5

| System | MAE | sMAPE | CRPS | MASE | P10/P90 cov. | median query ms | peak MB |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| engine | **109.1943** | **1.998** | **0.1444** | **0.693** | **0.796** | 1118.5 | 56.2 |
| matrix_profile | 1838.7840 | 26.805 | 0.2767 | 11.017 | 0.300 | 1.2 | 2.7 |
| naive | 195.5430 | 3.359 | 0.1449 | 1.130 | 0.794 | **0.0** | **0.1** |
| Chronos-T5-small (published, in-domain) | - | - | - | 3.148 | - | - | - |

### m4_daily — horizon 14

| System | MAE | sMAPE | CRPS | MASE | P10/P90 cov. | median query ms | peak MB |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| engine | **169.7614** | **3.261** | **0.1399** | **1.050** | **0.813** | 1114.9 | 4.6 |
| matrix_profile | 1828.3488 | 26.973 | 0.2761 | 11.033 | 0.303 | 1.0 | 0.5 |
| naive | 229.9234 | 4.086 | 0.1591 | 1.335 | 0.741 | **0.0** | **0.1** |
| Chronos-T5-small (published, in-domain) | - | - | - | 3.148 | - | - | - |

### m4_hourly — horizon 5

| System | MAE | sMAPE | CRPS | MASE | P10/P90 cov. | median query ms | peak MB |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| engine | **202.2044** | 5.101 | 0.1510 | **0.408** | **0.771** | 31585.2 | 1.5 |
| matrix_profile | 587.5429 | 9.494 | 0.2500 | 0.895 | 0.400 | 1.8 | 0.1 |
| naive | 304.4857 | **5.037** | **0.1052** | 0.603 | 0.943 | **0.0** | **0.0** |
| Chronos-T5-small (published, in-domain) | - | - | - | 0.721 | - | - | - |

### m4_hourly — horizon 20

| System | MAE | sMAPE | CRPS | MASE | P10/P90 cov. | median query ms | peak MB |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| engine | 591.1666 | 10.452 | 0.1678 | 1.035 | **0.708** | 33243.9 | 1.4 |
| matrix_profile | 1241.1643 | 10.314 | 0.2614 | 1.411 | 0.357 | 1.6 | 0.1 |
| naive | **364.3643** | **5.310** | **0.1052** | **0.617** | 0.943 | **0.0** | **0.0** |
| Chronos-T5-small (published, in-domain) | - | - | - | 0.721 | - | - | - |

### nn5_daily — horizon 5

| System | MAE | sMAPE | CRPS | MASE | P10/P90 cov. | median query ms | peak MB |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| engine | 5.3946 | 27.477 | 0.1674 | 1.219 | **0.710** | 1208.6 | 53.7 |
| matrix_profile | 3.5417 | **16.161** | 0.2063 | 0.789 | 0.564 | 1.8 | 2.3 |
| naive | **3.4358** | 17.752 | **0.1073** | 0.804 | 0.935 | **0.0** | **0.0** |
| Chronos-T5-small (published, zero-shot) | - | - | - | **0.169** | - | - | - |

### nn5_daily — horizon 20

| System | MAE | sMAPE | CRPS | MASE | P10/P90 cov. | median query ms | peak MB |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| engine | 5.4626 | 31.170 | 0.1717 | 1.250 | 0.694 | 1208.6 | 1.3 |
| matrix_profile | **4.1738** | **21.879** | 0.2135 | 0.952 | 0.537 | 1.6 | 0.1 |
| naive | 4.3134 | 24.862 | **0.1270** | 1.000 | **0.861** | **0.0** | **0.0** |
| Chronos-T5-small (published, zero-shot) | - | - | - | **0.169** | - | - | - |

### spy_daily — horizon 5

| System | MAE | sMAPE | CRPS | MASE | P10/P90 cov. | median query ms | peak MB |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| engine | **2.3304** | **0.513** | **0.0900** | **0.885** | **1.000** | 2255.9 | 4.2 |
| matrix_profile | 350.6330 | 125.411 | 0.3567 | 133.220 | 0.000 | 1.8 | 0.5 |
| naive | 5.4152 | 1.204 | 0.1967 | 2.057 | **0.600** | **0.0** | **0.1** |

### spy_daily — horizon 20

| System | MAE | sMAPE | CRPS | MASE | P10/P90 cov. | median query ms | peak MB |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| engine | 16.4593 | 3.722 | **0.1167** | 6.254 | **0.900** | 2104.1 | 4.1 |
| matrix_profile | 336.9279 | 124.056 | 0.3567 | 128.013 | 0.000 | 2.1 | 0.5 |
| naive | **13.5160** | **3.076** | 0.2633 | **5.135** | 0.350 | **0.0** | **0.1** |

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
