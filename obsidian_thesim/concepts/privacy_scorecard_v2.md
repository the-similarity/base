# Privacy Scorecard v2

Expanded privacy scorecard in `the_similarity/synthetic/privacy.py`. Supersedes the original 3-metric [[privacy_scorecard]] with 6 heuristic probes.

## The 6 heuristics

### 1. DCR (distance to closest record)
For every synthetic row, compute min L2 distance to the real set. Compare against the real-to-real nearest-neighbour baseline (5th percentile). Emits `leakage_ratio = p05_dcr / real_baseline_p05`. Ratio near 1.0 = healthy spacing; much less than 1.0 = synthetic data hugs real rows.

### 2. Memorization count
Exact duplicates (`L2 < 1e-9`) and near duplicates (`L2 < 1%` of median real-to-real spacing, auto-scaled). Returns counts and `near_dupe_frac`.

### 3. Membership inference AUC proxy
Split-half MIA: first half of real = members, second half = non-members. Score each row by `-min_L2(row, synth)`. `roc_auc_score(labels, scores)` -- 0.5 = no signal, > 0.5 = leakage. Avoids the cost of shadow models.

### 4. Attribute inference risk (NEW in v2)
Per-column decision tree probe: train a classifier on synthetic data, evaluate on real data. Compare accuracy against a random baseline (`1/n_classes`). Delta = `accuracy - baseline`. Any column where the generator lets you infer real attribute values better than chance is a risk signal.

### 5. Holdout leakage ratio (NEW in v2)
Split real data into train/holdout. Compute median DCR from synthetic to train vs. synthetic to holdout. `ratio = train_dcr / holdout_dcr`. Healthy generators produce ratio near 1.0 (equidistant). Ratio >> 1 means synthetic rows cluster closer to training data = memorization.

### 6. Tail exposure rate (NEW in v2)
Fraction of real outliers (beyond 2 sigma column-wise) reproduced in the synthetic set within close L2 distance. High tail exposure = an adversary could identify individuals with extreme attribute values.

## Scoring: fail-closed aggregation

```
risks = {
    nn_leakage:           weight 0.30
    memorization:         weight 0.20
    membership_proxy:     weight 0.20
    attribute_inference:  weight 0.10
    holdout_leakage:      weight 0.10
    tail_exposure:        weight 0.10
}
weighted_sum = sum(risk * weight)
worst_single_risk = max(all risks)
overall_score = 1 - max(weighted_sum, worst_single_risk)
passed = overall_score >= 0.6
```

The `max(weighted_sum, worst_single_risk)` is deliberately fail-closed: one catastrophic leak tanks the score even if all other metrics are clean. Averaging would let a memorization disaster be diluted by benign signals.

## Honest caveat

These are **heuristic probes, not formal privacy guarantees**. The scorecard catches obvious leaks (memorization, overfitting, outlier reproduction) but does not provide differential privacy or any cryptographic bound. The code docstrings say this explicitly. Formal DP is a future layer -- see [[batch3 synthetic copies v2 2026-04-17]].

## Links

- Code: `the_similarity/synthetic/privacy.py`
- Tests: `the_similarity/tests/test_synthetic_privacy.py`
- Original 3-metric version: [[privacy_scorecard]]
- Contracts: [[synthetic_contracts]]
- Batch context: [[batch3 synthetic copies v2 2026-04-17]]
