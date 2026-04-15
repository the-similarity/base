# Privacy scorecard

`the_similarity/synthetic/privacy.py` — `PrivacyScorecard` implementing
[[synthetic module contracts|ScorecardProtocol]].

Fast, attack-free privacy gate for a synthetic dataset vs. its real source.
Three cheap diagnostics, worst-case aggregation, fail-closed threshold.

## Sub-metrics

- **DCR (nn_leakage)** — for every synth row, min L2 distance to the real
  set. Compared against the real↔real nearest-neighbour baseline (5th
  percentile). Emits `median_dcr`, `p05_dcr`, `real_baseline_p05`,
  `leakage_ratio = p05_dcr / real_baseline_p05`. Ratio ≈ 1 means normal
  spacing; much less than 1 means synth hugs the real set.
- **Memorization** — exact dupes (`L2 < exact_eps`, default `1e-9`) and
  near dupes (`L2 < near_eps`, auto-derived as 1% of median real↔real
  spacing so the gate adapts to the data's scale). Returns counts and
  `near_dupe_frac`.
- **Membership proxy** — split `real` in half: first half = members,
  second half = non-members. Score each row by `-min_L2(row, synth)` (lower
  distance = more "member-like"). `auc = roc_auc_score(labels, scores)`;
  0.5 = no signal, > 0.5 = leakage.

## Aggregation

```
risks = [nn_risk(leakage_ratio), near_dupe_frac, membership_risk(auc)]
overall_score = 1 - max(risks)
passed = overall_score >= 0.6
```

- `nn_risk = clip(1 - leakage_ratio, 0, 1)`
- `membership_risk = clip(2*(auc - 0.5), 0, 1)`
- `passed_threshold` is a class attr — override per-instance or class-wide.

## Why these choices

- Worst-of aggregation is deliberately fail-closed: one leaky signal tanks
  the score. Averaging would let a catastrophic memorization be "diluted"
  by a benign AUC.
- Split-half MIA avoids the cost of shadow models while still giving a
  non-trivial signal for generators that overfit training data.
- Near-dupe epsilon is data-scaled because raw-return series and
  normalised series differ by orders of magnitude; a fixed absolute
  tolerance would either miss leaks on small-scale data or flag benign
  matches on large-scale data.

## Tests

`the_similarity/tests/test_synthetic_privacy.py` — covers protocol
conformance, happy path (independent gaussian draws pass), failure path
(exact + near-copy attacks fail), pandas/numpy/univariate shapes, and
fail-closed on empty/non-finite inputs.
