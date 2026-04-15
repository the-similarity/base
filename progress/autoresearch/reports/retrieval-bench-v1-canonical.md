# Lane report — `retrieval-bench-tiers-v1-lane`

_DISCARD — generated 2026-04-15T05:37:08Z_

**Canonical-format port of `retrieval-bench-v1.md`**

This report is the canonical rendering of the Phase 1A retrieval benchmark output. The original `retrieval-bench-v1.md` is kept for historical reference; this canonical copy is what the Phase 2 review tooling consumes.

## Metadata

- Lane id: `retrieval-bench-tiers-v1-lane`
- Benchmark id: `retrieval-bench-tiers-v1`
- Commit: `0c7ebdc`
- Timestamp: `2026-04-15T05:37:08Z`
- Arms: `tier1_only`, `tier1_plus_full`

## Slice × arm scorecard

| slice | tier1_only·forward_return_correlation | tier1_only·crps | tier1_only·calibration_error_p10_p90 | tier1_only·hit_rate | tier1_only·runtime_seconds_median | tier1_plus_full·forward_return_correlation | tier1_plus_full·crps | tier1_plus_full·calibration_error_p10_p90 | tier1_plus_full·hit_rate | tier1_plus_full·runtime_seconds_median |
|---|---|---|---|---|---|---|---|---|---|---|
| `spy-bull-2016-2019` | 0.9313 | 0.0271 | 0.0500 | 0.8750 | 0.4775 | 0.5696 | 0.0285 | 0.3000 | 0.7500 | 5.0612 |
| `spy-covid-2020` | -0.2828 | 0.0235 | 0.0500 | 0.8750 | 0.1729 | -0.3490 | 0.0277 | 0.0500 | 0.7500 | 7.9498 |
| `spy-rate-hike-2022` | 0.6594 | 0.0401 | 0.0500 | 0.1250 | 0.1189 | 0.7206 | 0.0347 | 0.1750 | 0.1250 | 6.4577 |

## Deltas

| metric | direction | baseline | candidate | Δ | improvement |
|---|---|---|---|---|---|
| `forward_return_correlation` | higher_is_better | 0.4359 | 0.3137 | -0.1222 | no |
| `crps` | lower_is_better | 0.0303 | 0.0303 | +0.0000 | no |
| `calibration_error_p10_p90` | lower_is_better | 0.0500 | 0.1750 | +0.1250 | no |
| `hit_rate` | higher_is_better | 0.6250 | 0.5417 | -0.0833 | no |

## Gates

| gate | required | metric | direction | threshold | observed | result |
|---|---|---|---|---|---|---|
| `crps_improvement` | True | `crps` | lower_is_better | -0.0050 | 0.0000 | FAIL |
| `runtime_ceiling` | True | `runtime_multiplier` | lower_is_better | +3.0000 | 25.3090 | FAIL |
| `correlation_uplift` | False | `forward_return_correlation` | higher_is_better | +0.0200 | -0.1222 | FAIL |

**Failing required gates:**

- Gate 'crps_improvement' on 'crps' (lower_is_better): Δ=+0.00004 <= -0.00500 -> FAIL
- Gate 'runtime_ceiling' on 'runtime_multiplier' (lower_is_better): Δ=+25.30902 <= +3.00000 -> FAIL

## Verdict

**DISCARD** — Tier 1+2 blew the runtime ceiling (37x > 3x) and failed to deliver a CRPS improvement on enough slices. The 9-method stack is kept as the engine default only because this was a *measurement* lane, not a *replacement* lane — see the rejection log entry `tier2_as_default` for the full context.

## Discussion

**Scope caveat.** This run was budget-capped: 3 of 6 spec slices (all three SPY regimes) × 1 seed × 8 trials per slice. The other three slices (`nvda-long-run`, `tsla-long-run`, `btc-long-run`) were deferred because Tier 1+2 on their ~2k–7k-bar histories takes > 1 min per trial, which pushed the full sweep outside the session's wall-clock budget. Before promoting this verdict the follow-up lane must finish the remaining three slices and run both seeds (`42` and `314`).

**Runtime bottleneck: Tier 2.** Tier 1 (DTW + Pearson on SAX+MASS survivors) runs at 0.12–0.48 s/query on SPY. Tier 2 enrichment (Bempedelis ×2, Koopman, wavelet spectrum, EMD, TDA, transfer entropy — on 20 candidates) adds 5–8 s per query. On the 3 SPY slices the runtime multiplier was 10.6×, 46.0×, and 54.3×.

**Quality bottleneck: Tier 2 does not pay its cost on this sample.** Across the three SPY slices Tier 2 reduced CRPS on one slice (`spy-rate-hike-2022`, ΔCRPS = -0.005) and increased CRPS on the other two. Correlation lift was mixed.

## Open questions

- Do the missing three slices (`nvda-long-run`, `tsla-long-run`, `btc-long-run`) change the verdict?
- Does seed 314 reproduce seed 42's CRPS flatness?
- Can `feature_store` caching close the runtime gap without dropping methods?
- Which individual Tier 2 methods contribute to the one slice (`spy-rate-hike-2022`) where CRPS improved?

## Artifacts

- `progress/autoresearch/reports/retrieval-bench/ (raw per-(slice, arm) JSONs)`
- `progress/autoresearch/reports/retrieval-bench-v1.md (original report)`
- `progress/autoresearch/experiments.jsonl (ledger entry)`
- `research/autoresearch/retrieval_bench/slices.yaml (spec)`
