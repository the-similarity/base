> [!warning] Status: placeholder
> Trust score formula is uncalibrated. Weights are arbitrary. Do not rely on for decisions until validated against realized outcomes.

# Trust Artifact

## What it is

The **trust score** is a composite reliability metric (0-1) that summarizes how much confidence to place in a given backtest run's forecast. It is computed by the enriched finance adapter and stored in the run's `summary["trust_score"]`.

## How it's computed

The trust score combines three signals:

1. **Hit rate contribution** — directional accuracy of P50 forecasts. A hit_rate of 0.5 is coin-flip (no signal); scores above 0.55 contribute positively.
2. **Calibration error** — average absolute deviation between expected and observed percentile frequencies. Perfect calibration = 0.0; practical target < 0.05.
3. **Coverage contribution** — empirical P10-P90 interval coverage. Target is ~0.80 (matching the 80% nominal interval). Too high (>0.95) means the cone is too wide to be useful; too low (<0.60) means the cone is unreliable.

Rough formula: `trust = w1 * hit_rate_score + w2 * (1 - calib_error) + w3 * coverage_score`, where weights are tuned to penalize poor calibration more heavily than slightly low hit rates.

## Thresholds

| Score | Interpretation |
|-------|---------------|
| >= 0.8 | High trust — forecast is well-calibrated and directionally accurate |
| 0.6 - 0.8 | Moderate trust — usable with caution |
| 0.4 - 0.6 | Low trust — review risk flags before acting |
| < 0.4 | Unreliable — do not use for decisions |

## Why it matters

Without a trust score, operators must manually inspect hit_rate, calibration, and coverage independently. The trust score is the single number a [[finance_review|review workflow]] checks first: if trust < 0.4, the run is auto-flagged.

## Code paths

- Enriched adapter: `the_similarity/platform/adapters/finance.py` (stamps `trust_score` into `summary`)
- Registry row: `summary_json` column in the `runs` table
- CLI: `python -m the_similarity.platform show <run_id>` displays the full summary including trust_score

## Calibration grade pairing

The trust score is paired with a letter calibration grade (A/B/C/D/F).
The decision gate requires **both** a trust_score >= 0.7 **and** a
grade of A or B for the run to land TRUSTED. See [[finance_trust_grades]]
for the locked contract and [[calibration_artifact]] for the threshold map.

## Related

- [[calibration_artifact]] — per-percentile calibration details
- [[finance_trust_grades]] — letter-grade decision record (A/B/C/D/F)
- [[finance_review]] — review workflow that consumes trust_score
- [[finance_benchmark]] — benchmark harness for comparing trust scores across symbols
