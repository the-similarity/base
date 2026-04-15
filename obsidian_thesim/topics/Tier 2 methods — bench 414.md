# Tier 2 methods — bench 414

**Status**: preliminary "discard as default" verdict from first bench. Not yet
acted on. Budget-expanded rerun pending.

**Source**: PR #113, `progress/autoresearch/reports/retrieval-bench-v1.md`,
ledger row `retrieval-bench-tiers-v1-2026-04-15T05:37:08Z`. See
[[phase_1_findings_414]] for the compiled cross-finding narrative.

## Claim being tested

The current matcher runs a 9-method tiered pipeline (see
[[Code — matcher tiers and modules]]):

- **Tier 1**: SAX + MASS (prefilter) → DTW + Pearson (rerank). Cheap.
- **Tier 2**: wavelet leaders, Koopman, EMD, TDA, transfer entropy. Expensive.

The original design argument for Tier 2 was: *"Tier 1 finds shape-similar
windows; Tier 2 adds structure-aware signals (frequency regimes, dynamics,
topology) that make the final ranking richer, especially on complex regimes
like crisis or trend-break."*

That argument costs compute per query. The bench was built to price it.

## Method

See `research/autoresearch/retrieval_bench/`. Two arms, walk-forward, per-arm
identical backtester path. Same projector. Same scorer (minus Tier 2 weights
when Tier 2 is off). Same seed.

Engine defaults are not modified by the run — it monkey-patches the matcher
config for the duration of the arm and restores it afterward, **so the bench
is itself falsifiable**: you can't claim Tier 2 is bad because it was
subtly disadvantaged.

## Headline result

37× mean runtime multiplier (10.6× / 46.0× / 54.3× on SPY bull-market /
COVID / rate-hike slices), CRPS flat, correlation −0.12.

See [[phase_1_findings_414#Finding 1]] for the full table and gates.

## Why correlation actually dropped

This is the detail worth chewing on. Tier 2 did not just "not help"; it
*hurt* the correlation between query-forward-return and weighted-match-
predicted-return. Hypotheses, in decreasing order of how likely they seem:

1. **Tier 2 weights are mis-tuned.** The scorer still renormalizes weights
   but Tier 2 methods get a fixed slice of the score vector. On SPY, those
   weights may be actively down-ranking windows that Tier 1 correctly
   picked as most forward-return-informative. This is a weight bug, not a
   method bug.
2. **Regime-averaged weights fail inside each regime.** The scorer has one
   set of weights across all regimes. Tier 2 signals (wavelet scale
   exponents, EMD IMFs) shift meaning across regimes; a single weight per
   method cannot capture this. On regime-heterogeneous slices like
   `spy-rate-hike-2022` this manifests as noise.
3. **Tier 2 methods themselves are poorly parameterized for intraday-scale
   daily bars on SPY.** Wavelet leaders in particular are sensitive to
   scale choice and can produce unstable rank contributions on short
   windows.
4. **Noise-amplification by score-vector averaging.** Even with perfect
   per-method rankings, averaging noisier rank signals with cleaner ones
   can reduce ensemble-level correlation. This is classic garbage-in
   behavior and the cheapest fix is reweighting or dropping.

None of those are "Tier 2 is fundamentally useless." They are "Tier 2, as
currently deployed, hurts this benchmark on SPY."

## What would change the verdict

- Cross-asset retrieval (Tier 2 is supposed to shine when shape is borrowed
  across assets).
- Regime-transition slices, not just regime-interior slices.
- Seed-expanded rerun that controls for the single seed=42 draw.
- Tier 2 weight sweep; right now we tested "Tier 2 on vs off," not "Tier 2
  with its weights right."

## Action

**Short term (before Phase 2):**
- Run the budget-expanded bench: NVDA, TSLA, BTC, seed=314, crisis-entry
  slices. Same schema.
- If the verdict holds, add `Config.enable_tier2 = False` as the new default
  and make Tier 2 opt-in. Keep the code, demote the default.
- If the verdict flips on any cross-asset or regime-transition slice, the
  story is "Tier 2 is context-sensitive" and the fix is per-regime or
  per-asset weight adjustment.

**Do not do now:**
- Don't remove Tier 2 code. Discard-as-default ≠ discard-as-concept.
- Don't promote Tier 1 as "the new engine." It hasn't been benched against
  foundation models yet; that is Phase 2.

## Related

- [[retrieval_bench]] — concept note
- [[Code — matcher tiers and modules]]
- [[Benchmark slices]]
- [[Keep-discard thresholds]]
- [[phase_1_findings_414]]
