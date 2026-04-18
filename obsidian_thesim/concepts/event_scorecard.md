# Event Scorecard

Evaluation metrics for binary event predictions. The `EventScorecard` computes Brier score, log score, and calibration error from parallel lists of predicted probabilities and boolean outcomes.

## Metrics

### Brier Score
- **Formula**: `mean((predicted - outcome)^2)` where outcome is 0 or 1
- **Range**: [0, 1]. Lower is better.
- **Interpretation**: 0.0 = perfect, 0.25 = coin-flip baseline, 1.0 = maximally wrong
- **Why Brier**: It is a proper scoring rule — the optimal strategy is to report your true beliefs. No gaming possible.

### Log Score
- **Formula**: `mean(-[o*log(p) + (1-o)*log(1-p)])` with epsilon clamping
- **Range**: [0, inf). Lower is better.
- **Interpretation**: Penalizes confident wrong predictions much more harshly than Brier. A prediction of p=0.01 for an outcome that turns out True incurs a massive penalty.
- **Clamping**: Predictions are clamped to `[1e-15, 1-1e-15]` to avoid `log(0)`.

### Calibration Error
- **Formula**: `|mean(predicted) - mean(observed)|`
- **Range**: [0, 1]. Lower is better.
- **Interpretation**: Measures systematic bias. If you predict 0.7 on average but only 50% resolve True, calibration error = 0.2.
- **Limitation**: This is a single-bin calibration metric. A proper calibration curve (Agent 4's binned calibration) is more informative but requires more predictions.

### Grade
Letter grade derived from Brier score thresholds:

| Grade | Brier range | Interpretation |
|-------|-------------|----------------|
| A | < 0.10 | Excellent — well-calibrated and accurate |
| B | < 0.20 | Good — meaningfully better than chance |
| C | < 0.30 | Fair — some signal but noisy |
| D | < 0.40 | Poor — barely better than coin-flip |
| F | >= 0.40 | Failing — worse than naive baseline |

## Resolution

Questions must have a boolean `resolution` (True/False). Unresolved questions (resolution=None) are excluded from scoring. The scorecard raises `ValueError` on empty input.

## Registry integration

Scorecards are registered in the platform registry under `ScorecardKind.CALIBRATION` with `overall_score = brier_score` and a pass gate of `brier_score < 0.30`.

## Code paths

- v1 implementation: `examples/event_prediction_demo.py` (`EventScorecard` class)
- Agent 4's full scorecard (when landed): `the_similarity/events/scorecard.py`
- Platform contracts: `the_similarity/platform/contracts.py` (`ScorecardSummary`)

## Related

- [[event_contracts]] — data schemas feeding the scorecard
- [[batch6 world event prediction v1 2026-04-18]] — decision record
