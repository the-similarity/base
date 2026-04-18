# Finance trust grades (letter contract)

> [!info] Status: locked
> Decided 2026-04-18. The contract for `summary["calibration_grade"]` is the 5-tier letter scale A/B/C/D/F. Do not regress to qualitative labels.

## What it is

Every finance run's registry summary carries a `calibration_grade` field that renders how well the forecast cone matched realized outcomes, on a **5-tier letter scale**: A (best) -> B -> C -> D -> F (worst). The scale is intentionally the same idiom used by S&P bond ratings, investor decks, and the existing `[[calibration_artifact]]` concept note — a universal finance-UX shorthand.

## Threshold map

Based on mean absolute calibration error (|observed - expected|, averaged across percentiles).

| Grade | Mean abs error | Interpretation |
|-------|----------------|---------------|
| A | < 0.03 | Excellent — cone widths match reality |
| B | 0.03 - 0.06 | Good — minor drift, usable |
| C | 0.06 - 0.10 | Fair — cone may be too narrow or wide |
| D | 0.10 - 0.15 | Marginal — review before acting |
| F | >= 0.15 | Unreliable — do not use |

Upper bounds are **exclusive**: `error == 0.03` is a B, not an A. Empty or malformed calibration data fails closed to **F** — a missing grade must never render as a pass in a trading UI.

## Decision gate

The trust artifact combines `trust_score` and `calibration_grade` into a final `TrustDecision`:

```
trust_score >= 0.7 AND grade in (A, B) -> TRUSTED
trust_score >= 0.5 OR  grade == C      -> REVIEW
else                                   -> REJECTED
```

Note the asymmetry:
- A high trust_score alone is not enough — the cone must also be well-calibrated (A or B).
- A C-grade cone alone triggers REVIEW regardless of trust_score.
- A D-grade cone does **not** qualify for the review escape hatch — only trust_score >= 0.5 pulls it out of REJECTED.

## Why letters, not qualitative labels

We considered three options:

1. **Qualitative labels** (`excellent/good/fair/poor`) — 4 tiers, ambiguous ("is 'good' the top or second-tier?"), hard to stack-rank in a grid UI.
2. **Numeric score** (0-100) — maximally informative, but then the UI has to re-quantize anyway, and traders pattern-match on "A-grade" far faster than "87%".
3. **Letter scale (A/B/C/D/F)** — 5 tiers, universal idiom, stack-rankable, compact. This is what the integration test at `the_similarity/tests/test_finance_operating.py:233` locked in before the adapter caught up.

Decision: **letter scale**. The code was drifting from the contract the tests and the vault had already written down.

## Code paths

Authoritative implementation:

- `the_similarity/platform/adapters/trust.py::compute_calibration_grade` — the grade function.
- `the_similarity/platform/adapters/trust.py::VALID_GRADES` — the canonical tuple `("A", "B", "C", "D", "F")`.
- `the_similarity/platform/adapters/trust.py::compute_decision` — the trust gate.
- `the_similarity/platform/adapters/finance.py::_enrich_summary` — stamps the grade into `summary["calibration_grade"]`.

Mirrors (kept in lock-step manually — the test suite catches drift):

- `the_similarity/finance/signal_summary.py::_calibration_grade` — free-form scalar-or-dict input for one-line summaries.

Consumers that should NOT re-implement the thresholds:

- `the-similarity-app/app/finance/*.tsx` — renders `calibration_grade` as a string pass-through.
- `the_similarity/finance/review.py` — reads the grade for risk-flag narratives.
- `the_similarity/finance/risk_flags.py::POOR_CALIBRATION` — runs on numeric calibration_error, not the grade string.

## Related

- [[trust_artifact]] — composite trust_score that pairs with this grade
- [[calibration_artifact]] — per-percentile calibration detail feeding the grade
- [[finance_review]] — review workflow that consumes grade + trust_score
