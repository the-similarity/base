# Utility scorecard

Module: `the_similarity/synthetic/utility.py` · Class: `UtilityScorecard` · Shipped: 2026-04-15 (PR #130).

Implements [[ScorecardProtocol]] for downstream-task-transfer evaluation of synthetic copies. Answers: **does a model trained on synthetic data still perform on real data?**

## Method

- Downstream task: **one-step-ahead forecasting** with lag features (lags 1..5), `sklearn.linear_model.Ridge`. Picked as the cheapest reliable baseline with an obvious sensitivity to temporal structure.
- Chronological 70/30 split on the real series (never random — would leak future into past).
- Three runs per call:
  - **real_baseline**: train on real_train, test on real_test — ceiling reference.
  - **TRTS** (train-real, test-synth): train on real_train, test on synth.
  - **TSTR** (train-synth, test-real): train on synth, test on real_test. The honest transfer metric.
- Reports `{mae, rmse, r2}` per run plus `transfer_gap = (TSTR.mae - real_baseline.mae) / real_baseline.mae`. Lower transfer_gap = better utility.
- `passed = transfer_gap < 0.3` (class attr, first-pass uncalibrated).

## Invariants

- Deterministic — all RNG seeded explicitly.
- Univariate on the first column. Multi-series only if trivial to lift; current shipped version is single-column.
- Fail-closed on too-short input or non-finite metrics.

## Why it matters

Fidelity scores can look great while the synthetic data is useless for training. Utility is the ground-truth check on whether the generator preserved the signal a model cares about. See [[block_bootstrap_generator]] for the target generator and [[fidelity_scorecard]] for the complementary distributional check.
