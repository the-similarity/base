# Trust filter

Opt-in gating layer that decides whether a forecast cone is reliable
enough to act on. Lives in `the_similarity/core/trust_filter.py`.
Paired with [[finance_pilot]] and the calibration-aware decision rules
in `the_similarity/core/decision_rules.py`.

## What it does

Takes a match pool, a projection ([[Forecast]] or [[EnsembleForecast]]),
an optional query regime, and an optional [[BacktestReport]]-like
calibration anchor. Returns a `TrustDecision(trust: bool, score:
float in [0,1], reasons: list[str], signals: dict)`.

Default engine behavior is unchanged — callers explicitly opt in.

## Signals

Each produces a sub-score in [0, 1]; overall score is a weighted mean.

1. **Calibration error (weight 0.35)** — MAE between stated percentile
   and empirical rate in a recent backtest. Hard gate at MAE > 0.15
   by default.
2. **Match-pool agreement (weight 0.25)** — dispersion across the
   forward paths (fallback: normalised P90-P10 spread). 1 / (1 +
   normalised_dispersion). Soft signal.
3. **Regime novelty (weight 0.15)** — fraction of matches whose regime
   label equals the query regime. Soft signal.
4. **Sample size (weight 0.25)** — smooth logistic `n / (n +
   min_matches)`. Hard gate at `n < min_matches` (default 5).

## Hard gates vs soft signals

- Hard: sample size, calibration MAE. Fail → `trust=False` regardless
  of the other signals.
- Soft: agreement and regime novelty. Contribute to the continuous
  score; only enforce a floor if the caller lowers their threshold.

Rationale: tiny pools and catastrophic calibration failures are the
most common production false-positives; knife-edge thresholds on soft
signals create discontinuous position sizing.

## Defaults (conservative)

- `min_matches = 5`
- `max_calibration_mae = 0.15`
- `min_score = 0.5`
- Signal weights as listed above.

Relax via keyword args to `TrustFilter(...)` or the shortcut
`trust_filter.evaluate(...)`.

## How it is used

`CalibrationAwareStrategy` (see `the_similarity/core/decision_rules.py`)
runs any existing [[Strategy]] and post-filters its signals:

- trust=False → collapse to FLAT (or keep direction with size=0).
- trust=True → position_size scales with `trust.score *
  (confidence/100)`.

Entry threshold defaults to `P25 >= +threshold` for longs (and the
symmetric `P75 <= -threshold` for shorts). This targets the
conservative tail, not the median.

## Related
- [[finance_pilot]] — design-partner workflow that consumes this.
- `the_similarity/core/strategy.py` — underlying rule engine.
- `the_similarity/core/backtester.py` — where calibration comes from.
- `the_similarity/core/ensemble.py` — conformal gives a second take on
  interval reliability.

## Tests

- `the_similarity/tests/test_trust_filter.py` — 14 unit tests per
  signal and gate.
- `the_similarity/tests/test_decision_rules_integration.py` —
  end-to-end through `api.backtest`.
