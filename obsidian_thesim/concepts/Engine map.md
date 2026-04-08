# Engine map

How the Python engine is laid out (authoritative detail stays in code and `CLAUDE.md`).

## Core modules

| Area | Path | Role |
|------|------|------|
| Pipeline | `the_similarity/core/matcher.py` | Tiered search: SAX + MASS prefilter → DTW + Pearson → Tier 2 enrichment → ranking |
| Config | `the_similarity/config.py` | Hyperparameters (e.g. `confidence_decay_rate`, `koopman_blend_weight`) |
| Scoring | `the_similarity/core/scorer.py` | `ScoreBreakdown`, `MatchResult`, dynamic weight renormalization |
| Forecast | `the_similarity/core/projector.py` | Quantile cone + confidence decay + Koopman blend |
| Backtest | `the_similarity/core/backtester.py` | Walk-forward evaluation |
| Features | `the_similarity/core/feature_store.py` | SQLite cache for expensive Tier 2 work |
| Metrics | `the_similarity/core/metrics.py` | Hit rate, MAE, calibration, CRPS |
| API | `the_similarity/api.py` | `load`, `search`, `project`, `plot`, `backtest` |

## Methods package

Implementations live in `the_similarity/methods/` (one module per method). See [[Nine-method pipeline]] for how tiers slot together.

## Related

- [[Nine-method pipeline]]
- [[Repo research and docs]]
