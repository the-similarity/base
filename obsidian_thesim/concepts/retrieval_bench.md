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

## Findings

Findings are populated by the first real run. See `progress/autoresearch/reports/retrieval-bench-v1.md` for the current scorecard + verdict.
