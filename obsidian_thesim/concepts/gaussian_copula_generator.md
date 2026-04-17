# Gaussian Copula Generator

Part of [[synthetic_copies_v2|Copies v2]]. Implemented by Agent 1 in `the_similarity/synthetic/copies.py`.

## How it works

1. **Fit marginals.** For each column of the real dataset, compute the empirical CDF. Constant columns are detected and frozen to their value.
2. **Transform to uniform.** Apply the probability integral transform: each column becomes U(0,1) via its empirical CDF.
3. **Fit Gaussian copula.** Transform the uniform margins to standard normal via `norm.ppf`, then compute the Pearson correlation matrix of the Gaussian-transformed data. If the matrix is not positive semi-definite (degenerate due to collinear columns or small samples), apply nearest-PSD projection via eigenvalue clamping.
4. **Sample.** Use `numpy.random.default_rng(seed)` for deterministic draws from the multivariate normal with the estimated correlation matrix. Transform back through the normal CDF to get uniform margins, then invert each column's empirical CDF (via `interp1d`) to produce synthetic data in the original scale.

## vs. Block Bootstrap

| Dimension | Block Bootstrap | Gaussian Copula |
|-----------|----------------|-----------------|
| Autocorrelation | Preserved by construction (contiguous blocks) | Not preserved (iid samples unless augmented) |
| Marginals | Exact (resampling) | Approximate (CDF fitting) |
| Cross-series | Preserved within blocks | Captured by the copula correlation matrix |
| Tails | Exact (samples come from real data) | Depends on marginal fit — can under/overestimate |
| Novel values | Never — pure resampling | Yes — interpolates between real values |
| Stationarity assumption | None | Implicit — fits one joint distribution to entire series |

## Strengths

- Produces smooth, continuous synthetic data (no blockiness).
- Captures cross-column dependence explicitly via the copula.
- Generates genuinely new value combinations (unlike bootstrap which only resamples).
- Easy to extend: swap the Gaussian copula for Student-t, vine, or empirical copula.

## Weaknesses

- Ignores temporal structure unless augmented with lag features or a time-series copula.
- Gaussian copula cannot capture tail dependence (asymptotic independence in the tails). Real financial data often has tail dependence.
- Empirical CDF estimation is sensitive to sample size — small datasets produce coarse marginals.
- Not calibrated — no formal guarantee on distributional closeness.

## Key parameters

- Marginals: empirical CDF (current implementation).
- Correlation: Pearson in Gaussian space (after uniform -> normal transform).
- Nearest-PSD: eigenvalue clamping for degenerate correlation matrices.
- Determinism: `numpy.random.default_rng(seed)` — no global RNG state.

## Code path

- Generator class: `the_similarity/synthetic/copies.py::GaussianCopulaGenerator`
- Follows [[generator_protocol|GeneratorProtocol]]: `fit(real) -> sample(n, seed) -> SyntheticDataset`
- Scored by the same three scorecards: [[fidelity_scorecard]], [[privacy_scorecard]], [[utility_scorecard]]
