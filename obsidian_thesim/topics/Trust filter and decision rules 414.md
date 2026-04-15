# Trust filter and decision rules 414

**Status**: shipped as opt-in production modules. Engine defaults unchanged.
No real pilot yet — framework only.

**Source**: PR #111,
`the_similarity/core/trust_filter.py`, `the_similarity/core/decision_rules.py`,
`examples/finance_workflow_v1.py`, `docs/planning/finance_pilot_v1.md`.

## What this solves

Before this PR, the engine could answer "what are analogous windows and what
is their forward cone?" That is a research question. A product has to answer
*"should I act on this cone right now, and if so, how?"*

The four gaps between "fan chart" and "decision":

1. **No gate on miscalibration.** A cone that has been under-covering
   recently is actively misleading; the engine had no mechanism to decline
   the call.
2. **No gate on match-pool quality.** If all the matches disagree with each
   other, the cone is a average-over-chaos and the confidence number is
   mechanical, not meaningful.
3. **No gate on regime novelty.** If the query is far from any region the
   engine has analogues for, the cone is extrapolation, not retrieval.
4. **No review artifact.** Users can't later audit *why* a decision was
   made — signals, gate states, sizing reasoning.

1C closes all four without touching the default projector path.

## Architecture

### `TrustFilter` (gate)

```
TrustFilter(config).evaluate(match_pool, projection, regime_state)
  -> TrustDecision(trust: bool, score: float ∈ [0,1],
                   reasons: list[str], signals: dict)
```

Four signals:

| Signal | Source | Gate type | What it measures |
|--------|--------|-----------|------------------|
| `calibration_mae` | recent coverage error stream | hard | is the cone well-calibrated right now? |
| `match_pool_agreement` | std of match forward-returns | soft | do the analogues agree? |
| `regime_novelty` | distance-to-nearest regime state | soft | is the query inside the engine's known world? |
| `sample_size` | `len(match_pool)` | hard | do we have enough analogues? |

Hard gates produce `trust = False` unconditionally. Soft gates scale `score`
down but don't veto. `score` is a multiplicative combination of the soft
signals bounded to `[0, 1]`.

### `CalibrationAwareStrategy` (wrapper)

Wraps any existing `the_similarity.core.strategy.Strategy`. On each bar:

1. Ask `TrustFilter.evaluate(...)` — if `trust == False`, emit FLAT with
   `size = 0` and record the veto in the review log.
2. Check tail-percentile entry threshold: longs require `P25 > threshold`,
   shorts require `P75 < threshold`. Default thresholds chosen to reject
   ambiguous entries where the bulk of the distribution straddles zero.
3. If both gates pass, call the inner strategy for the raw signal.
4. Scale `size = raw_size * trust.score * confidence`. Low trust shrinks
   positions naturally; a barely-trusted signal takes a small position.

### `ReviewSummary` (artifact)

For each decision, logs:
- timestamp
- signals (all four)
- trust outcome + reasons
- entry/exit check results
- final size
- realized outcome (after forward_bars)

`summarise_review(...)` renders to plaintext. Pilot surface would move this
to structured JSON.

## Pilot spec (`docs/planning/finance_pilot_v1.md`)

Target user: small fund / prop trader, $5M-$500M AUM, daily equities,
2-10 day hold window. The 2-10 day window is deliberate — it is:
- long enough that the trust-gate + calibration-aware sizing dominates
  transaction costs
- short enough that walk-forward analogue retrieval has enough forward
  outcomes per slice to calibrate against

### Four sign-a-pilot success gates

These are ambitious but measurable:

1. **Coverage within 5pp of stated.** On live paper trading, if we say
   P10/P90, those bounds must contain actuals 78-82% of the time. This is
   the single most important gate — a user who can't trust the cone can't
   trust the product.
2. **Hit rate ≥ 55%.** Directional accuracy on gated signals.
3. **Veto rate 20-40%.** If we never veto, the trust gate is cosmetic.
   If we veto everything, we're not differentiated from cash. This range
   is a guess for "sensible" — pilot data will calibrate it.
4. **Sharpe lift ≥ 0.3.** Improvement over a naive threshold strategy on
   the same underlying projections.

## What this is and isn't

- **Is**: a runnable technical prototype of the end-to-end decision loop.
  28 new tests. Engine defaults untouched.
- **Is not**: a polished UI, an identified design partner, a tested
  pricing model, a signed pilot. The spec says what a pilot would look
  like; we have not put it in front of anyone.

Calling it "pitch-ready" is wrong. Calling it "pilot-shaped" is right.

## Open questions

1. Trust weights and thresholds are plausibly motivated but not tuned.
   When we run pilots, sweep them against pilot P&L, not toy data.
2. The four signals are a starter set. Two candidates to add later:
    - **Crowding**: are the forward-return paths of the matches bunched
      on the same time window? Bunching indicates the analogy is
      driven by a single historical event, not a recurring pattern.
    - **Information freshness**: recent matches vs distant matches. A
      distribution dominated by 2008-era matches on a 2026 query is
      informational, but probably wants a trust penalty.
3. The review artifact is plaintext; should be structured JSON for a
   pilot surface.

## Related

- [[trust_filter]] — concept note
- [[finance_pilot]] — concept note
- [[Calibration and coverage]]
- [[Agent decision model]]
- [[Adaptive conformal calibration 414]] — the projector-side half of the
  "make the cone trustworthy" story
- [[phase_1_findings_414]]
