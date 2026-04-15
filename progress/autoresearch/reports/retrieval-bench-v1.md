# Retrieval benchmark — Tier 1 vs Tier 1+2 ablation (`retrieval-bench-tiers-v1`)

- Generated: 2026-04-15T05:37:08Z
- Git SHA: `0c7ebdc`
- Trials per slice: 8
- Seeds: [42]
- Baseline arm: `tier1_only` (SAX+MASS → DTW + Pearson)
- Experiment arm: `tier1_plus_full` (current 9-method default)

## Scope caveat

This initial run is **budget-capped**: 3 of 6 spec slices (all three SPY
regimes) × 1 seed × 8 trials per slice. The other three slices
(`nvda-long-run`, `tsla-long-run`, `btc-long-run`) were deferred because
Tier 1+2 on their ~2k–7k-bar histories takes > 1 min per trial, which
pushed the full sweep outside the session's wall-clock budget.

Before promoting the verdict to a hard engine change, the follow-up lane
must (a) finish the remaining three slices and (b) run both seeds
(`42` and `314`). The decision below is therefore **preliminary but
directionally strong** — runtime is catastrophic and CRPS is flat.

## Decision

**Verdict: `DISCARD`**

Tier 1+2 is 37.0x slower than Tier 1 (> 3.0x budget) and only 1/3 slices improved CRPS (< 3 required).

- Slices with strict CRPS improvement: 1 / 3
- Slices with correlation lift: 1 / 3
- Mean Tier1+2 - Tier1 CRPS delta: +0.0000
- Mean correlation delta: -0.122
- Mean runtime multiplier: 37.0x

## Per-slice scorecard

Columns: `corr` = forward-return correlation (higher is better),
`CRPS` (lower is better), `cal` = |p10-p90 coverage - 0.80| (lower is better),
`hit` = sign hit rate, `rt_med` = median runtime per query.

| slice | T1 corr | T1+2 corr | Δcorr | T1 CRPS | T1+2 CRPS | ΔCRPS | T1 cal | T1+2 cal | T1 hit | T1+2 hit | T1 rt | T1+2 rt | rt× |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `spy-bull-2016-2019` | 0.931 | 0.570 | -0.362 | 0.0271 | 0.0285 | +0.0014 | 0.050 | 0.300 | 0.88 | 0.75 | 0.48s | 5.06s | 10.6x |
| `spy-covid-2020` | -0.283 | -0.349 | -0.066 | 0.0235 | 0.0277 | +0.0042 | 0.050 | 0.050 | 0.88 | 0.75 | 0.17s | 7.95s | 46.0x |
| `spy-rate-hike-2022` | 0.659 | 0.721 | +0.061 | 0.0401 | 0.0347 | -0.0054 | 0.050 | 0.175 | 0.12 | 0.12 | 0.12s | 6.46s | 54.3x |

## Tier bottleneck analysis

**Runtime bottleneck: Tier 2.** Tier 1 (DTW + Pearson on SAX+MASS
survivors) runs at 0.12–0.48 s/query on SPY. Tier 2 enrichment (Bempedelis
×2, Koopman, wavelet spectrum, EMD, TDA, transfer entropy — on 20
candidates) adds 5–8 s per query. On the 3 SPY slices the runtime
multiplier was 10.6×, 46.0×, and 54.3×. **Tier 2 is the wall-clock
bottleneck by ~1–2 orders of magnitude.**

**Quality bottleneck: Tier 2 does not pay its cost on this sample.**
Across the three SPY slices Tier 2 reduced CRPS on one (`spy-rate-hike-2022`,
ΔCRPS = -0.005) and increased CRPS on the other two. Correlation lift was
mixed (+0.06 on rate-hike, -0.36 on bull, -0.07 on COVID).

Conclusion — for SPY daily the answer to Phase 1A's question "is Tier 1 or
Tier 2 the real bottleneck?" is: **Tier 2 is the bottleneck on runtime and
also, on this sample, is net negative on calibrated forecast quality.**
Tier 1 alone looks surprisingly competitive on trending and mean-reverting
regimes; Tier 2 only earned its place on the rate-hike bear slice.

Note: the spec's `tier2_candidates=20` means Tier 2 runs 9 methods × 20
windows × per-window matrix builds per query; lowering this knob or
caching via `feature_store` may close much of the runtime gap without
touching the method list. That is the next lane to investigate.

## Next actions

- Do NOT change engine defaults from this run — this is measurement,
  not replacement. Keeping the current 9-method stack preserves the
  option value while we investigate.
- Identify which Tier 2 methods individually contribute (next lane:
  per-method ablation — drop one method at a time).
- Consider reducing Tier 2 cost (smaller `tier2_candidates`, feature
  store caching) rather than removing methods outright.
- Re-run with full `n_trials` and both seeds before a keep/discard on
  the default config; the current sample is budget-capped.

## Artefacts

- Raw per-(slice, arm) JSON: `progress/autoresearch/reports/retrieval-bench/`
- Ledger entry: `progress/autoresearch/experiments.jsonl`
- Spec: `research/autoresearch/retrieval_bench/slices.yaml`
