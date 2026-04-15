# Fidelity scorecard

Module: `the_similarity/synthetic/fidelity.py` · Class: `FidelityScorecard` · Shipped: 2026-04-15 (PR #132).

Implements [[ScorecardProtocol]] for synthetic-vs-real time-series comparison. Produces a `FidelityReport` ([[synthetic contracts]]) covering four axes:

- **Marginals** — per-column KS statistic, Wasserstein-1 distance, mean/std/skew/kurtosis diffs. Catches distribution shape mismatches.
- **Temporal** — ACF and PACF deltas at lags [1, 5, 10]. Catches serial-dependence mismatches (the thing a naive shuffle fails).
- **Cross-series** — Pearson correlation matrix Frobenius diff and max-absolute diff. None when input is univariate.
- **Tails** — p01/p99 ratios and CVaR differences at 5%/95%. Catches tail-behavior divergence that mean/std miss.

Overall score is a weighted combination in [0, 1]; `passed = overall_score >= 0.7` (class attr threshold, first-pass uncalibrated).

Uses `scipy.stats.ks_2samp` and `scipy.stats.wasserstein_distance`. Handles both ndarray and DataFrame inputs by duck-typing.

See [[block_bootstrap_generator]] for what it grades, and [[synthetic launch 2026-04-15]] for the broader context.
