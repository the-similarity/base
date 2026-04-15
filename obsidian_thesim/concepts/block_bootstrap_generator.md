# Block Bootstrap Generator

First-tier realism-first synthetic generator for time series. Lives in
[[the_similarity/synthetic/copies.py]] and satisfies the
[[synthetic_contracts|GeneratorProtocol]].

## Why

Block bootstrap is the simplest generator that preserves local
autocorrelation and heavy-tailed marginals by construction — it just
resamples contiguous chunks of the real series. Before investing in
GANs/diffusion/copulas, we need a baseline that *already* passes marginal
and short-horizon ACF scorecards. This is that baseline.

## Variants

- **`BlockBootstrapGenerator`** — classic moving-block bootstrap. Uniform
  random start indices over `[0, T - block_len]`, concatenate blocks, trim
  to `n`. Univariate and multiseries (column-aligned).
- **`RegimeBlockBootstrapGenerator`** — tags each timestep with a regime
  label (default: rolling-vol quantile split, two regimes), samples blocks
  whose entire span sits inside one regime. Preserves regime-duration
  structure that plain bootstrap smears. Falls back to plain start-sampling
  when a regime has no contiguous `block_len` window (`regime_fallback=True`
  in provenance).

## Determinism

`numpy.random.default_rng(seed)` only — no global state. Same
`(real, block_len, regime_params, seed)` → bit-identical samples. Covered
by tests in `the_similarity/tests/test_synthetic_copies.py`.

## Key tradeoffs

- `block_len` too small → autocorrelation destroyed; too large → low
  variety, risk of near-memorization. 5–40 for daily finance.
- Regime-aware variant keeps vol clustering but concentrates mass on
  observed regimes — won't generate truly unseen regimes (that's what the
  [[worlds_runner|worlds tier]] is for).
- Pure resampling: every synthetic value is a real value. Fidelity high,
  privacy low — use the [[privacy_scorecard]] before publishing.

## Version

`generator_version = "0.1.0"`. Bump when sampling behavior changes for
the same seed.
