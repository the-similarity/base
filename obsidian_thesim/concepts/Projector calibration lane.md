# Projector calibration lane

The **projector calibration lane** is an autoresearch lane focused on improving the forecast cone's statistical calibration and probabilistic accuracy (CRPS) through tuning of the projector module.

## What it tunes

The [[Nine-method pipeline]] produces ranked matches. The projector (`the_similarity/core/projector.py`) then extracts forward paths from those matches and builds a weighted percentile forecast cone. This lane tunes the cone-shaping parameters **without** altering the retrieval/ranking pipeline.

Key knobs:
- **`confidence_decay_rate`** -- linearly widens non-median percentile curves over the forecast horizon. Default `0.0` (no decay). Positive values increase cone width at longer horizons.
- **`koopman_blend_weight`** -- fraction of P50 blended from Koopman operator evolution vs. purely historical analogues. Default `0.0` (historical only).
- **Quantile interpolation** -- the `_weighted_quantile` function uses piecewise-linear CDF center interpolation. Alternative estimators may improve calibration.
- **Cone width scaling** -- a post-hoc multiplicative correction to the P10/P90 distance from median.

## Metrics

| Metric | Direction | What it measures |
|--------|-----------|------------------|
| CRPS | Lower is better | Integrated CDF error (calibration + sharpness) |
| Calibration error P10/P90 | Lower is better | Mean absolute deviation of P10/P90 containment from nominal |
| Hit rate | Higher is better | Fraction of trials where P50 predicts correct direction |

## Relevant files

- `the_similarity/core/projector.py` -- projection logic, weighted quantile, confidence decay
- `the_similarity/core/metrics.py` -- CRPS, calibration, hit rate, MAE
- `the_similarity/core/backtester.py` -- walk-forward backtester producing `TrialResult`
- `the_similarity/config.py` -- `confidence_decay_rate`, `koopman_blend_weight`, `percentiles`
- `research/autoresearch/benchmarks/projector-calibration-core-v1.yaml` -- benchmark manifest
- `research/autoresearch/playbooks/PROJECTOR_CALIBRATION_LANE.md` -- lane playbook
- `research/autoresearch/scripts/run_projector_experiment.py` -- experiment runner

## Links

- [[Engine map]] -- full codebase layout
- [[Nine-method pipeline]] -- how matches are produced before projection
- [[Repo research and docs]] -- other research paths
