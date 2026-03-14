# Self-Similarity, Fractal Analysis, and Power Laws in Financial Time Series

## 1. Self-Similarity and Power-Law Transforms

Self-similarity in financial markets refers to the phenomenon where price patterns appear statistically similar across different time scales. A stochastic process X(t) is self-similar with Hurst exponent H if X(at) has the same distribution as a^H * X(t) for all a > 0.

Two principal power laws in financial time series:
- **Power-law distribution of returns**: Tails follow P(|r| > x) ~ x^(-alpha), meaning extreme price moves occur far more often than Gaussian predicts
- **Power-law decay of autocorrelation**: Absolute returns and volatility exhibit slowly decaying autocorrelations (long memory)

Fractional Brownian motion (fBm) extends classical Brownian motion through the Hurst exponent H:
- H = 0.5: memoryless (standard random walk)
- H > 0.5: persistent (trending)
- H < 0.5: anti-persistent (mean-reverting)

## 2. Fractal Analysis (Hurst Exponent, Long-Range Dependence)

### The Fractal Market Hypothesis (FMH)

The FMH, proposed as an alternative to the Efficient Market Hypothesis, asserts that market stability arises from investors operating across multiple time horizons. When this diversity breaks down (e.g., during crises), liquidity evaporates and markets become unstable.

### Hurst Exponent Estimation Methods

| Method | Description | Notes |
|--------|-------------|-------|
| **Rescaled Range (R/S)** | Classical method by Mandelbrot & Wallis | Simple but biased for short series |
| **DFA** | Removes polynomial trends before computing fluctuation function | Robust to non-stationarity |
| **Periodogram Regression** | Estimates H from spectral density at low frequencies | Efficient for stationary series |
| **Aggregated Variance** | Examines how variance decays with aggregation level | Intuitive but less precise |
| **Local Whittle** | Semi-parametric frequency-domain method | Asymptotically optimal |
| **Wavelet Analysis** | Multi-resolution decomposition for scale-dependent H | Good for non-stationary data |

### DFA Algorithm Steps

1. **Integration**: Compute cumulative sum Y(i) = sum(x(k) - mean(x))
2. **Segmentation**: Divide Y into non-overlapping boxes of length n
3. **Local detrending**: Fit polynomial of order k to each box; subtract fit
4. **Fluctuation function**: Compute RMS of residuals: F(n)
5. **Scaling**: Repeat for multiple box sizes. Slope of log F(n) vs log n yields alpha (~ H)

Values: alpha = 0.5 (uncorrelated), alpha > 0.5 (persistent), alpha < 0.5 (anti-persistent)

## 3. Multifractal Analysis (MFDFA, Singularity Spectrum)

### Why Multifractal?

A single Hurst exponent (monofractal) cannot capture the full complexity of financial data. Multifractal analysis acknowledges that different moments scale differently -- small fluctuations may have different scaling than large ones.

### MFDFA Algorithm

1. Compute cumulative sum of the time series
2. Divide into non-overlapping segments of length s
3. For each segment, fit polynomial and compute variance of residuals
4. Compute q-th order fluctuation function: F_q(s) for varying q
5. Determine generalized Hurst exponent h(q) from scaling: F_q(s) ~ s^h(q)

### Key Outputs

- **h(q)**: If constant for all q = monofractal. If varying = multifractal.
- **tau(q)**: Renyi exponent, tau(q) = q*h(q) - 1. Nonlinear tau(q) confirms multifractality.
- **f(alpha)**: Singularity spectrum via Legendre transform. Width Delta alpha = alpha_max - alpha_min quantifies degree of multifractality.

### Mandelbrot's MMAR

The Multifractal Model of Asset Returns (MMAR) models returns as Brownian motion over multifractally distorted "trading time":
- Captures long tails without infinite variance
- Reproduces long memory in absolute returns
- Scale-consistent (unlike GARCH)

### Python Implementation

The `MFDFA` library provides efficient NumPy-based MFDFA:
- Install: `pip install MFDFA`
- Supports arbitrary polynomial detrending orders
- Vectorized computation
- [GitHub](https://github.com/LRydin/MFDFA) | [Docs](https://mfdfa.readthedocs.io/en/dev/)

## 4. L-BFGS-B Optimization for Time Series Fitting

L-BFGS-B (Limited-memory BFGS with Bound constraints) is ideal for fitting parametric models when parameters have physical bounds.

**Why L-BFGS-B:**
- **Bound constraints**: Financial model parameters often have natural bounds (Hurst in [0,1], volatility > 0)
- **Memory efficient**: Limited vectors to approximate inverse Hessian
- **Gradient-based**: Faster convergence than derivative-free methods

```python
from scipy.optimize import minimize
result = minimize(
    objective_function,
    x0=initial_params,
    method='L-BFGS-B',
    bounds=[(low1, high1), (low2, high2), ...],
    options={'ftol': 1e-12, 'maxiter': 1000}
)
```

## 5. Power-Law Scaling in Stock/Crypto Markets

### Empirical Evidence

Gabaix et al. (Nature, 2003): power laws describe distributions of stock returns, trading volume, and number of trades with remarkably consistent exponents. The "inverse cubic law": tail exponent alpha ~ 3.

### Stock Markets
- Return distributions: power-law tails with exponents 2-4
- Trading volume: power law with exponent ~1.5
- Mechanism: large market participants trading optimally generate the observed power laws

### Cryptocurrency Markets
- Bitcoin: exponentially decayed double power-law distribution (differs from stocks)
- Crypto momentum returns: alpha < 3, implying theoretically undefined variance
- Heavy tails occur with higher probability than traditional equities

## 6. Self-Affine vs Self-Similar

- **Self-similar**: Identical under uniform scaling in all directions
- **Self-affine**: Requires different scaling factors along different axes

Financial time series are **self-affine** because time and price are fundamentally different quantities. Methods designed for self-similar fractals (e.g., box-counting) give misleading results. DFA and MFDFA are designed for self-affine processes.

## Summary: Methods and Tools

| Method | What It Measures | Python Library | Key Output |
|--------|-----------------|----------------|------------|
| R/S Analysis | Hurst exponent (H) | `nolds`, custom | Single H value |
| DFA | Scaling exponent (alpha ~ H) | `nolds`, `MFDFA` | Monofractal scaling |
| MFDFA | Generalized Hurst h(q) | `MFDFA` (pip) | h(q), tau(q), f(alpha) |
| L-BFGS-B | Parameter optimization | `scipy.optimize` | Fitted parameters |
| Power-law fitting | Tail exponent (alpha) | `powerlaw` (pip) | Distribution exponent |

## References

- [Power Laws in Financial Time Series (Santa Fe Institute)](https://wiki.santafe.edu/images/5/52/Powerlaws.pdf)
- [Fractal Market Hypothesis (SSRN)](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=5137493)
- [FMH and Financial Stability (Bank of England)](https://www.bankofengland.co.uk/-/media/boe/files/financial-stability-paper/2013/the-fractal-market-hypothesis-and-its-implications-for-the-stability-of-financial-markets.pdf)
- [Improvement in Hurst Exponent Estimation (Springer)](https://link.springer.com/article/10.1186/s40854-022-00394-x)
- [Hurst Exponent (Wikipedia)](https://en.wikipedia.org/wiki/Hurst_exponent)
- [DFA (Wikipedia)](https://en.wikipedia.org/wiki/Detrended_fluctuation_analysis)
- [Detecting Trends with Hurst Exponent (Macrosynergy)](https://macrosynergy.com/research/detecting-trends-and-mean-reversion-with-the-hurst-exponent/)
- [MFDFA Library (GitHub)](https://github.com/LRydin/MFDFA)
- [Multifractal Model of Asset Returns (SSRN)](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=78588)
- [Multifractal Analysis of Bitcoin (Vilnius Tech)](https://journals.vilniustech.lt/index.php/JBEM/article/view/23025)
- [Power-law Distributions in Financial Fluctuations (Nature)](https://www.nature.com/articles/nature01624)
- [SciPy L-BFGS-B Documentation](https://docs.scipy.org/doc/scipy/reference/optimize.minimize-lbfgsb.html)
