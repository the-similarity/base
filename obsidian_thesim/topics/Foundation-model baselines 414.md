---
type: finding
status: active
created: 2026-04-14
run_id: foundation-bench-v1-2026-04-15T17:50:20Z
---

# Foundation-model baselines — 2026-04-14 findings

First end-to-end run of the [[foundation_bench]] lane. All five models
scored against the SPY/BTC subset of the retrieval-bench slices with
`n_trials=12`, `seed=42`, `query_window=60`, `forward_bars=30`.

> **IMPORTANT CAVEAT.** Every foundation adapter (TimesFM, Chronos,
> Moirai, MOMENT) ran under the **synthetic-fallback** path — none of
> the pretrained weights are reachable in the current environment.
> `wavelet_baseline` was the only adapter that executed real
> classical code. The numbers below are therefore a measurement of the
> FALLBACK cones, not the real foundation models. They are still
> informative because they validate the runner + report + ledger
> payload, and because the fallback cones themselves are reasonable
> strawmen (AR(1) Gaussian for Moirai; AR(1) + bootstrap residual for
> TimesFM/Chronos/MOMENT).

## Cross-slice aggregate (arithmetic mean over 4 slices)

| model | mean_crps | mean_cal | mean_hit | mean_rt_med (s) | fallback cells | explain |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| timesfm | **0.0934** | 0.108 | 0.42 | 0.026 | 4/4 | low |
| chronos | 0.0934 | 0.108 | 0.42 | 0.024 | 4/4 | low |
| moment | 0.0934 | 0.108 | 0.42 | 0.026 | 4/4 | low |
| moirai | 0.1071 | 0.633 | 0.33 | 0.000 | 4/4 | low |
| wavelet_baseline | 0.1083 | 0.279 | 0.48 | 0.032 | 0/4 | medium |

## Per-slice summary

| slice | best CRPS (model) | wavelet_baseline CRPS | cal_err (best / wavelet) |
| --- | --- | ---: | --- |
| spy-bull-2016-2019 | 0.0333 (timesfm / chronos / moment) | 0.0372 | 0.050 / 0.383 |
| spy-covid-2020 | 0.1056 (timesfm / chronos / moment) | 0.1160 | 0.133 / 0.300 |
| spy-rate-hike-2022 | 0.0315 (timesfm / chronos / moment) | 0.0330 | 0.033 / 0.133 |
| btc-long-run | 0.2032 (timesfm / chronos / moment) | 0.2470 | 0.217 / 0.300 |

## Observations

1. **Bootstrap-residual fallback ≡ for three models.** TimesFM, Chronos,
   and MOMENT all use `bootstrap_residual_cone(n_paths=200)` in
   fallback mode, so they produce IDENTICAL forecasts for identical
   histories and seeds. This is by design — the fallbacks are
   calibrated to be fair stand-ins when real weights aren't loaded.
2. **Moirai (AR(1) Gaussian cone) is systematically over-confident.**
   `mean_cal` of 0.633 vs ~0.108 for the bootstrap cones says the
   analytic Gaussian cone is too narrow for fat-tailed price returns,
   especially on bull and bear slices. This is a known property of
   AR(1) — the bootstrap cone captures residual kurtosis.
3. **Wavelet baseline (real classical) has the best hit rate (0.48).**
   On a signed-p50 basis it ties or beats every fallback cone on
   directional accuracy. Its calibration error (0.279) is worse than
   the bootstrap cones in aggregate — but it's also the only adapter
   that actually ran real code.
4. **Runtime parity.** All adapters run in ~20-30 ms on these slices.
   Moirai reads as 0.000 because the AR(1) closed-form is sub-ms and
   gets rounded by the runtime summariser. Budget cap (180 s/cell)
   never triggered.
5. **BTC slice stresses every cone.** CRPS ~10× larger on btc-long-run
   than on spy-bull. Calibration errors uniformly worse. Consistent
   with the crypto_highvol regime.

## Run artefacts

- ledger row: `foundation-bench-v1-2026-04-15T17:50:20Z`
- report: `progress/autoresearch/reports/foundation-bench-v1.md`
- per-cell JSON: `progress/autoresearch/reports/foundation-bench/` (20 files)

## What to do next

- **Get real weights working** — highest leverage. Install
  `timesfm`/`chronos`/`momentfm`/`uni2ts` in a dedicated CI image and
  rerun. The runner is already weight-aware: `any_fallback` flips to
  False and the ledger status becomes `ok`.
- **Add ensemble/2d models.** `models.yaml` is the only file that
  needs to change.
- **Join with [[retrieval-bench-tiers]] per-trial.** Slice ids and
  seeds match exactly — dashboards can join on (slice_id,
  trial_index) to compute foundation vs engine deltas.

## Relevant files

- `research/autoresearch/foundation_bench/run_bench.py`
- `research/autoresearch/foundation_bench/report.py`
- `research/autoresearch/foundation_bench/ledger.py`
- `research/autoresearch/foundation_bench/adapters/`
