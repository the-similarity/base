# Gaussian Copula Generator

Part of [[synthetic_copies_v2|Copies v2]]. Implemented by Agent 1 in `the_similarity/synthetic/copies.py`.

## How it works

1. **Fit marginals.** For each column of the real dataset, estimate the empirical CDF (or fit a parametric distribution — e.g. Student-t for fat tails).
2. **Transform to uniform.** Apply the probability integral transform: each column becomes U(0,1) via its fitted CDF.
3. **Fit Gaussian copula.** Transform the uniform margins to standard normal via the inverse normal CDF, then estimate the correlation matrix (Kendall's tau inversion for robustness to outliers).
4. **Sample.** Draw from the multivariate normal with the estimated correlation matrix, transform back through the normal CDF to get uniform margins, then invert each column's marginal CDF to get synthetic data in the original scale.

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
- Easy to extend: swap the Gaussian copula for Student-t, vine, or empirical copula.

## Weaknesses

- Ignores temporal structure unless augmented with lag features or a time-series copula.
- Gaussian copula cannot capture tail dependence (asymptotic independence in the tails). Real financial data often has tail dependence.
- Marginal CDF estimation is a separate modeling choice that can go wrong silently.
- Not calibrated — no formal guarantee on distributional closeness.

## Key parameters

- `marginal_fit`: method for fitting column-wise CDFs (empirical, parametric).
- `correlation_method`: Kendall's tau (robust) or Pearson (fast but outlier-sensitive).

## Code path

- Generator class: `the_similarity/synthetic/copies.py::GaussianCopulaGenerator`
- Follows [[generator_protocol|GeneratorProtocol]]: `fit(real) -> sample(n, seed) -> SyntheticDataset`
- Scored by the same three scorecards: [[fidelity_scorecard]], [[privacy_scorecard]], [[utility_scorecard]]
