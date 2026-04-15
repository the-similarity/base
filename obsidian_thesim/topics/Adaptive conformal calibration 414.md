# Adaptive conformal calibration 414

**Status**: winning variant in the `projector-v2` lane (synthetic-fallback
sweep). Needs real-parquet confirmation before promotion to default.

**Source**: PR #114,
`the_similarity/core/projector_adaptive_conformal.py`,
`progress/autoresearch/reports/projector-v2-v1.md`, ledger rows
`projector-v2-adaptive_conformal-2026-04-15T05:20:38Z` and
`projector-v2-change_aware_conformal-2026-04-15T05:20:38Z`. See
[[phase_1_findings_414#Finding 2]] for cross-finding narrative.

## What it is

Standard conformal prediction gives a fixed coverage guarantee
(1 − α) under i.i.d. calibration. Time series are not i.i.d. — regime
shifts, non-stationarity, and fat tails all break the assumption. Empirical
coverage drifts from nominal over time.

Adaptive conformal (Gibbs & Candès, 2021) updates the effective α online
based on recent coverage error. If the cone has been under-covering
(actuals landing outside more often than the nominal rate), α shrinks and
the cone widens. If the cone has been over-covering, α grows and the cone
narrows. The update is bounded to keep α ∈ (0, 1).

The change-aware variant adds a CUSUM-style change detector on top of the
running coverage statistic. When a change is detected (large recent
coverage error spike), the running state resets — so a regime shift
doesn't require the slow adaptive update to catch up; the projector
"forgets" the stale calibration and starts fresh.

## Why we care

Calibration is the projector's job. A cone that claims 80% coverage but
delivers 55% coverage is worse than useless; it produces decisions with
the wrong risk profile. See [[Calibration and coverage]].

The original weighted-quantile projector has no online calibration
mechanism — its cone is a function of match-derived return samples and
confidence decay, but it has no feedback loop from recent miscoverage to
next-cone-width. Adaptive conformal adds exactly that feedback loop, and
it does so *independent of the underlying projector* — it wraps any fan.

## What the bench measured

Walk-forward sweep, SPY-1d + BTC-1d, 15 trials per cell,
window=50, forward_bars=20, top_k=5. Runner:
`research/autoresearch/scripts/run_projector_v2_sweep.py`.

Per-variant artifacts at
`progress/autoresearch/reports/projector-v2-<variant>-<slice>.json`.

### Numbers (mean across both slices)

| Metric | Baseline | Adaptive | Change-aware |
|--------|----------|----------|--------------|
| CRPS | 0.191 | **0.164** (−14%) | **0.164** (−14%) |
| Cal err P10/P90 | 0.100 | **0.067** (−0.033) | **0.067** (−0.033) |
| Joint-path CRPS | 0.212 | 0.183 | 0.183 |
| Hit rate | 0.50 | 0.50 | 0.50 |
| Runtime | 296s | 262s | 247s |

Runtime is actually *lower* on adaptive / change-aware than baseline,
because the lane's sweep reuses in-memory match pools between trials;
comparing runtime per-trial at the projector step, the overhead is
negligible (<1% per call).

## Decision

**KEEP** adaptive conformal. **KEEP** change-aware as a separate variant,
pending a shift-rich slice (COVID-entry, VIX spike, rate-hike week)
to prove its CUSUM reset does something the plain adaptive variant
doesn't. On smooth SPY/BTC they are numerically identical.

## Why not promote to default yet

1. **Synthetic-fallback data.** The sweep used the synthetic series
   generator when real parquets were absent — deterministic Gaussian-ish
   samples, not real returns. Real SPY/BTC have:
    - fatter tails (t-like, not Gaussian)
    - volatility clustering (GARCH structure)
    - overnight/weekend gaps
    - regime shifts
   A variant that wins on synthetic can fail on real. **Real-parquet
   confirmation sweep is required before promotion.**
2. **Only two slices.** Need to confirm on at least one crisis slice
   (COVID entry, 2020-03-16 crash, Volmageddon) before flipping the
   default.
3. **Window length not tuned.** The online coverage window is fixed at
   50 trials — too short on stable regimes, too long on fast shifts.
   Window-length sweep is its own follow-up bench.
4. **Composition not tested.** If we later adopt the joint-path projector
   as baseline, does adaptive conformal still win on top? Likely yes (it
   wraps any projector), but we should bench-confirm before assuming.

## How to promote once confirmed

Suggested rollout path:
1. Real-parquet confirmation sweep on SPY/BTC/NVDA + one crisis slice.
2. Window-length sweep to pick the best coverage window (likely between
   30 and 100 trials).
3. Add `Config.projector: Literal["baseline","adaptive_conformal",
   "change_aware_conformal"]` with default remaining `baseline`.
4. After a second independent confirmation run (different seed set,
   different data snapshot), flip the default to `adaptive_conformal`.

Keep baseline behind the flag indefinitely — it is the reference a future
bench might need to reproduce.

## Related

- [[projector_v2]] — concept note for the whole lane
- [[Calibration and coverage]]
- [[Fan charts and forecast cones]]
- [[Confidence decay]]
- [[CRPS score]]
- [[Projector calibration lane]]
- [[phase_1_findings_414]]

## References

- Gibbs, I. & Candès, E. (2021). *Adaptive conformal inference under
  distribution shift*. NeurIPS. [[research/full-text/notes/]] — pending
  ingest.
