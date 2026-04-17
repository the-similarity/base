# Synthetic Copies v2

## What v2 adds

Copies v1 shipped a single generator (block bootstrap) with three scorecards
(fidelity, privacy, utility) and CLI + registry integration. It proved the
pipeline works. v2 extends the system along four axes:

1. **Second generator: Gaussian Copula.** Fits marginal distributions per
   column and a Gaussian copula to model cross-column dependence. Produces
   smooth, parametric synthetic data that complements the non-parametric
   block bootstrap. Neither dominates the other — bootstrap preserves
   autocorrelation by construction; copula captures marginals + cross-series
   structure better when the real series is stationary.

2. **Comparison and promotion.** A ComparisonRunner takes N generator outputs
   scored on the same source data, ranks them by a configurable composite
   metric (default: fidelity + privacy - |utility_gap|), and promotes the
   winner. This is the first step toward automated generator selection.

3. **Expanded privacy scorecard.** Three new diagnostics beyond DCR /
   memorization / membership inference:
   - Attribute inference risk (can an attacker reconstruct a dropped column
     from the remaining synthetic columns?).
   - Holdout leakage (does the synthetic set systematically crowd holdout
     rows that were not part of the generator's fit set?).
   - Tail exposure (are extreme real values reproduced with suspiciously
     high fidelity?).

4. **Synthetic dataset catalog.** A persistent index of all generated
   datasets: source, generator, seed, scorecard summary, artifact paths.
   Queryable by kind, source, or score range. Feeds the platform API and
   future UI.

## The workflow

```
source.csv
   |
   v
[Generator A]  [Generator B]  ...
   |                |
   v                v
synth_a.parquet   synth_b.parquet
   |                |
   v                v
[Fidelity]      [Fidelity]
[Privacy]       [Privacy]
[Utility]       [Utility]
   |                |
   v                v
scorecard_a.json  scorecard_b.json
   |                |
   +-------+--------+
           |
           v
   [ComparisonRunner]
           |
           v
   promoted = best generator
           |
           v
   [Catalog entry]  -->  Platform API  -->  UI
```

Each step is independently runnable via CLI or Python API. The pipeline is
idempotent — re-running with the same (source, generator, seed) produces
identical output and upserts the registry row.

## What's honest

- **Privacy scorecard is heuristic.** DCR + memorization + membership
  inference proxy are cheap, interpretable diagnostics — not formal privacy
  guarantees. They catch obvious leaks but will not satisfy a regulator
  asking for differential privacy bounds.

- **Gaussian copula is not calibrated.** It fits a Gaussian copula to the
  empirical marginals via Kendall's tau inversion. This works well for
  light-tailed, near-elliptical data. It fails on heavy tails, regime
  switches, and strong nonlinear dependence — all common in finance.

- **Comparison is a heuristic ranking.** The composite metric
  (fidelity + privacy - |utility_gap|) weights the three dimensions
  equally. There is no formal Pareto front or multi-objective optimization.

- **Attribute inference is a proxy.** We train a ridge regressor to predict
  a held-out column from the rest and measure R^2. This is not a full
  attack surface — a motivated adversary with side information can do
  better.

## What's next

1. **More generators.** TimeGAN, diffusion-based, and
   regime-conditional copula are candidates. Each must beat the bootstrap
   baseline on at least one scorecard dimension to earn its complexity.

2. **Formal privacy.** Differential privacy noise injection as a
   post-processing step, with calibrated epsilon accounting. The scorecard
   would then report (epsilon, delta) alongside the heuristic diagnostics.

3. **Customer-uploaded source data.** Today, source data is a local CSV.
   The next step is an upload endpoint that validates schema, runs a data
   quality check, and stores the source in the catalog before generation.

4. **Comparison as a service.** The ComparisonRunner today is a local
   function. Expose it via the platform API so the UI can trigger
   multi-generator sweeps and display the Pareto front.

5. **Adaptive block length.** The block bootstrap's block_len is a
   hyperparameter the user picks. Auto-tuning it (e.g. via Politis-Romano
   optimal block length) would remove a footgun and improve out-of-box
   fidelity.
