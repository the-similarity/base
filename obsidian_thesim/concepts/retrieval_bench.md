# Retrieval benchmark lane (retrieval_bench)

An ablation lane that asks one measurable question: **does Tier 2 enrichment earn its CPU over Tier 1 alone?**

## Location

- Spec, runner, comparator, reporter: `research/autoresearch/retrieval_bench/`
- Per-(slice, arm) JSON: `progress/autoresearch/reports/retrieval-bench/`
- Consolidated scorecard: `progress/autoresearch/reports/retrieval-bench-v1.md`
- Ledger entry: `progress/autoresearch/experiments.jsonl`

## What the lane compares

| Arm | Active methods | Runtime behaviour |
|-----|----------------|-------------------|
| `tier1_only` | `dtw`, `pearson_warped` + SAX+MASS prefilter (Tier 0, always on) | Cheap shape matcher. Engine skips Tier 2 enrichment when only Tier 1 fields are active. |
| `tier1_plus_full` | All 9 methods (current `the_similarity/config.py` default) | Adds Bempedelis R²/smoothness, Koopman, wavelet leaders, EMD, TDA, transfer entropy. |

Tier gating is controlled at the engine via `Config(active_methods=..., tier2_candidates=...)`; the bench does not mutate the engine itself.

## Metrics

- `forward_return_correlation` — Pearson correlation of (mean forward return across the top-K matches) against the realised forward return. Top-K precision proxy. Higher is better.
- `crps` — empirical CRPS of the quantile forecast built from each arm's matches. Lower is better.
- `calibration_error_p10_p90` — absolute deviation of the p10–p90 empirical coverage from 0.80.
- `hit_rate` — sign agreement between p50 and realised.
- `runtime_seconds[median/p95]` — per-query runtime, reported at two percentiles so slow tails cannot hide cost.

## Decision gates

See `research/autoresearch/retrieval_bench/slices.yaml` -> `thresholds`:

- `min_crps_improvement = 0.005` — absolute delta required to count as a CRPS win.
- `min_forward_corr_improvement = 0.02` — absolute delta for correlation win (secondary pathway).
- `max_runtime_multiplier = 3.0` — Tier 1+2 median runtime must stay within 3× Tier 1 unless CRPS wins.
- `min_slices_improved = 3` — of the six slices, at least three must meet the bar.

The four ordered gates (in `compare.decide`) are:

1. Runtime blowout AND no CRPS majority → `discard`.
2. CRPS majority → `keep`.
3. Correlation majority (secondary) → `keep`.
4. Otherwise → `discard`.

Two agents running the same artefacts always reach the same verdict.

## Walk-forward invariant

Each trial gives the matcher only `dataset[:query_start]` as history. Forward returns are extracted from `dataset[query_end:query_end + forward_bars]` for the realised value and from `history[match.end_idx:...]` for each match's forward window. No branch ever leaks post-query information into retrieval.

## Related notes

- [[Nine-method pipeline]] — describes the Tier 0/1/2 pipeline this lane probes.
- [[Benchmark slices]] — the canonical slice taxonomy that `slices.yaml` extends.
- [[Retrieval evaluation harness]] — the retrieval-function-vs-retrieval-function harness that `retrieval_bench` builds on.
- [[Keep-discard thresholds]] — the cross-lane convention this lane inherits.
- [[Experiment report format]] — the ledger/schema this lane conforms to.

## Findings (first run, 2026-04-15, budget-capped)

First run covered the three SPY regime slices (bull 2016–19, COVID 2020, rate-hike 2022) at 8 trials / slice / seed. NVDA, TSLA, and BTC slices were deferred: Tier 1+2 on their 2k–7k-bar histories exceeded the session's wall-clock budget.

Headline:

- **Runtime bottleneck is Tier 2, decisively.** Tier 1 runs at ~0.12–0.48 s/query on SPY; Tier 1+2 adds 5–8 s/query (10×–54× slower). The [[Nine-method pipeline]]'s enrichment stage dominates wall-clock when enabled.
- **CRPS is essentially flat** between the two arms on the sampled SPY slices (mean ΔCRPS = +0.00004). Tier 2 improved CRPS only on the 2022 rate-hike bear (ΔCRPS = -0.005).
- **Forward-return correlation drops on average** with Tier 2 on SPY (mean Δ = -0.12). Only the rate-hike slice saw a correlation lift.
- **Verdict: `discard`** under the lane's decision gates — runtime blowout with no CRPS majority. Logged to `progress/autoresearch/experiments.jsonl`.

Caveats:

- Three slices is the minimum for `min_slices_improved=3`; a larger sweep across NVDA/TSLA/BTC could flip the correlation sign. Re-run with both seeds (42, 314) before making engine-level decisions.
- `tier2_candidates=20` (the spec's current arm value) means Tier 2 runs 9 methods × 20 windows per query. Reducing this knob is a cheaper intervention than removing methods entirely.
- This lane measures forecast/retrieval quality with a fixed percentile grid; it does not cover regime-conditional or conformal extensions already present in [[Nine-method pipeline]] ensemble mode.

Immediate next lanes (queued in `progress/autoresearch/reports/retrieval-bench-v1.md`):

1. Finish remaining three slices + second seed (budget-expanded rerun).
2. Per-method ablation (drop one of bempedelis/koopman/wavelet/emd/tda/TE at a time).
3. Tier 2 cost reduction (lower `tier2_candidates`, enable `feature_store` caching).

## Findings (Run 2, 2026-04-15, SPY-only partial, expanded seeds)

Partial rerun on `bench/retrieval-expanded-budget`. Worktree agent crashed at cell 13 of 24 with an API connection error; the 12 paired SPY cells (3 slices × 2 seeds × 2 arms) are complete and committed. NVDA / TSLA / BTC were not reached.

Protocol change vs Run 1: `n_trials` 8 → 40, seeds `[42]` → `[42, 314]`.

What held:
- **Seed 42 and seed 314 agree** on direction across every SPY slice — Run 1 discard was not a seed artifact.
- **Runtime blowout unchanged** (8.3×–47.5×, every cell over the 3× gate).
- **CRPS improvement only on `spy-rate-hike-2022`** (both seeds, clean −0.00569). Bull and COVID remain flat-to-worse. 1 of 3 SPY slices pass CRPS, far below the 3-of-6 bar.

What reversed:
- **Forward-return correlation now lifts on every SPY cell**, including +0.427 on covid seed 42 where Tier 1 was strongly anti-correlated. Tier 2 *is* finding more informative analogues; the cone construction is losing that signal before CRPS. Run 1's "correlation regresses" claim fails to replicate at 40 trials.

Status: **partial discard confirmed on SPY**, single-name / crypto untested. Engine defaults untouched. Next lane resumes NVDA / TSLA / BTC before any verdict is promoted.
