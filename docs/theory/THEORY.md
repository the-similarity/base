# The Similarity — Theory & Methods

This document describes the mathematical foundations behind each of the 9 scoring methods in The Similarity's tiered pipeline, along with the forecasting and validation framework.

---

## Table of Contents

1. [Pipeline Architecture](#pipeline-architecture)
2. [Tier 1: Prefilters](#tier-1-prefilters)
   - [SAX (Symbolic Aggregate approXimation)](#sax)
   - [Matrix Profile (MASS)](#matrix-profile)
3. [Tier 1: Cheap Scoring](#tier-1-cheap-scoring)
   - [DTW (Dynamic Time Warping)](#dtw)
   - [Pearson Correlation](#pearson-correlation)
4. [Tier 2: Enrichment Methods](#tier-2-enrichment-methods)
   - [Bempedelis Self-Similarity Transform](#bempedelis)
   - [Koopman EDMD](#koopman-edmd)
   - [Wavelet Leaders Multifractal Spectrum](#wavelet-leaders)
   - [EMD (Empirical Mode Decomposition)](#emd)
   - [TDA (Topological Data Analysis)](#tda)
   - [Transfer Entropy](#transfer-entropy)
   - [Regime Tagger](#regime-tagger)
5. [Scoring & Confidence](#scoring--confidence)
6. [Forecast Cone](#forecast-cone)
7. [Koopman Forward Evolution](#koopman-forward-evolution)
8. [Backtester](#backtester)
9. [References](#references)

---

## Pipeline Architecture

The Similarity uses a tiered pipeline to balance accuracy against computational cost:

```
All windows (~10,000s)
  │
  ├─ Tier 1 Prefilter: SAX MINDIST + MASS + Pearson
  │  Blend: 0.4 × SAX + 0.4 × MASS + 0.2 × Pearson
  │  → top 1,000 candidates (O(n log n) via FFT)
  │
  ├─ Cheap Scoring: DTW + Pearson on 1,000 survivors
  │  → top 20 candidates
  │
  ├─ Tier 2 Enrichment: 7 methods on 20 candidates
  │  Bempedelis, Koopman, Wavelet, EMD, TDA, TE, Regime
  │
  └─ Final Rank: weighted composite → top_k results
```

Each tier is progressively more expensive but more discriminating. The prefilter eliminates ~95% of candidates in milliseconds; Tier 2 methods spend compute only on the most promising survivors.

---

## Tier 1: Prefilters

### SAX

**Symbolic Aggregate approXimation** converts continuous time series into discrete symbol strings, enabling fast lower-bound distance computation.

**Algorithm:**
1. **PAA (Piecewise Aggregate Approximation):** Divide series into `n_segments` equal segments, replace each with its mean
2. **Symbolization:** Map each PAA value to an integer symbol using Gaussian breakpoints (`scipy.stats.norm.ppf`)
3. **MINDIST:** Distance between symbol strings that provably lower-bounds Euclidean distance

```
MINDIST(Q, C) = √(n/w) × √(Σ dist(q_i, c_i)²)
```

where `dist(a, b)` is the breakpoint distance table lookup.

**Key property:** MINDIST ≤ Euclidean distance, guaranteeing **no false dismissals**. Any true nearest neighbor will survive the SAX filter.

**References:**
- Lin et al., "SAX: A Novel Symbolic Representation of Time Series" (DAMI)

### Matrix Profile

**MASS (Mueen's Algorithm for Similarity Search)** computes the z-normalized Euclidean distance between a query and every subsequence of a longer series in O(n log n) via FFT.

**Algorithm:**
1. Compute sliding dot product via FFT: `QT = IFFT(FFT(Q_rev) × FFT(H))`
2. Convert to z-normalized distance using precomputed rolling mean/std
3. Score: `exp(-distance / √window_size)` → [0, 1]

MASS is computed once on the full history, producing a complete distance profile. Individual candidate scores are then looked up by position in O(1).

**References:**
- Rakthanmanon et al. (2012), "Searching and Mining Trillions of Time Series Subsequences under Dynamic Time Warping"
- STUMPY library — STAMP, STOMP, SCRIMP++ algorithms

---

## Tier 1: Cheap Scoring

### DTW

**Dynamic Time Warping** measures shape similarity with elastic temporal alignment. Unlike Euclidean distance, DTW handles phase shifts and local speed variations.

**Algorithm:**
1. Build cost matrix `C[i,j] = (q_i - h_j)²`
2. Find optimal warping path minimizing total cost (dynamic programming)
3. **Sakoe-Chiba band** constrains warping to ±R of the diagonal (default R = 10% of window), reducing complexity from O(n²) to O(n × R)
4. Score: `exp(-dtw_distance / window_size)` → [0, 1]

**Batch optimization:** Uses `dtaidistance.distance_matrix_fast` with `block` parameter to compute all pairwise DTW distances in C, eliminating the Python loop over candidates.

**References:**
- Sakoe & Chiba (1978), dynamic programming warping constraint
- Wu & Keogh (2020), "FastDTW is approximate and Generally Slower than the Algorithm it Approximates" (arXiv:2003.11246)

### Pearson Correlation

Pearson correlation after DTW alignment measures linear agreement between the query and matched window. Applied to z-scored log returns, it captures whether the two series move in the same direction with the same relative magnitude.

Score is `(pearson_r + 1) / 2` → [0, 1].

---

## Tier 2: Enrichment Methods

These 7 methods run only on the top 20 candidates (configurable via `tier2_candidates`). Each captures a different mathematical property of time series similarity.

### Bempedelis

**Self-similarity transform** based on power law analysis. Fits a transform `y = α × x^β` across multiple sub-windows of each series, measuring whether two series exhibit the same scaling behavior.

**Algorithm:**
1. Divide each window into `n_subwindows` overlapping segments
2. For each segment, fit power law parameters (α, β) via multi-start L-BFGS-B optimization
3. Compute R² of the power law fit
4. Score components:
   - `bempedelis_r2`: How well both series follow power law scaling
   - `bempedelis_smoothness`: Total variation of α and β across sub-windows (smoother = more self-similar)

**What it captures:** Scale invariance — whether the series "looks the same" at different magnifications. Financial series with similar fractal structure will have similar Bempedelis scores even if their shapes differ.

**References:**
- Mandelbrot & Wallis, Rescaled Range analysis
- Gabaix et al. (2003), "A Theory of Power-Law Distributions in Financial Market Fluctuations" (Nature)
- Mandelbrot, MMAR (Multifractal Model of Asset Returns)

### Koopman EDMD

**Extended Dynamic Mode Decomposition** approximates the Koopman operator — the infinite-dimensional linear operator that governs the evolution of observables of a nonlinear dynamical system.

**Algorithm:**
1. **Delay embedding** (Takens' theorem): embed scalar series into ℝ^d via `[x(t), x(t-τ), ..., x(t-(d-1)τ)]`
   - Lag τ: first minimum of auto-mutual information
   - Dimension d: false nearest neighbors criterion
2. **EDMD:** Fit linear operator K such that `X' ≈ K × X` (least squares on delay-embedded trajectories)
3. **Eigendecomposition:** Extract eigenvalues λ of K
   - |λ| encodes growth/decay rates
   - arg(λ) encodes oscillation frequencies
4. **Matching:** Hungarian algorithm on eigenvalue sets in ℂ
   - Distance: `|λ₁ - λ₂|` in the complex plane (preserves phase)
   - Unequal sets: pad smaller with zeros; unmatched eigenvalues penalized by modulus
   - Sort by modulus descending, truncate to top-k above |λ| > 0.05

**What it captures:** Whether two series are governed by the same underlying dynamical process, regardless of initial conditions or amplitude.

**References:**
- Koopman (1931), operator theory
- Takens (1981), delay embedding theorem
- Brunton et al., "Modern Koopman Theory for Dynamical Systems" (SIAM Review)
- Mann & Kutz (2016), "Dynamic Mode Decomposition for Financial Trading Strategies" (arXiv:1508.04487)

### Wavelet Leaders

**Multifractal spectrum analysis** via wavelet leaders characterizes the full spectrum of scaling exponents f(α) of a time series.

**Algorithm:**
1. Compute discrete wavelet transform (PyWavelets)
2. Extract wavelet leaders (local suprema of wavelet coefficients across scales)
3. Estimate multifractal spectrum f(α) via structure functions
4. Match spectra: distance between f(α) curves of query and candidate

**What it captures:** The full multifractal fingerprint — not just "is it fractal?" but "what kind of fractal?" Two series with the same f(α) spectrum exhibit the same distribution of local regularity exponents across scales.

**References:**
- Jaffard et al., "Wavelet Leaders in Multifractal Analysis" (Springer)
- Bouri et al. (2024), financial price jump detection via wavelets (PNAS)

### EMD

**Empirical Mode Decomposition** decomposes a signal into Intrinsic Mode Functions (IMFs) — data-driven basis functions that capture oscillations at different scales.

**Algorithm:**
1. Decompose both query and candidate into IMFs via sifting process (EMD-signal library)
2. Match IMFs by energy-weighted DTW distance
3. Score: weighted average of per-IMF similarities

**What it captures:** Multi-scale shape agreement. Two series can have different raw shapes but decompose into similar oscillatory components. EMD is adaptive (no predetermined basis) and handles nonlinear, non-stationary signals.

**References:**
- Huang et al. (1998), "The Empirical Mode Decomposition and the Hilbert Spectrum for Nonlinear and Non-Stationary Time Series Analysis"

### TDA

**Topological Data Analysis** via persistent homology extracts topological features (connected components, loops) from point clouds constructed via delay embedding.

**Algorithm:**
1. Delay-embed both series into ℝ^d (shared embedding module with Koopman)
2. Build Vietoris-Rips filtration on each point cloud
3. Compute persistence diagrams (birth-death pairs of topological features)
4. Match diagrams via bottleneck or Wasserstein distance
5. Score: `exp(-distance / scale)` → [0, 1]

**What it captures:** The "shape of the shape" — topological invariants that are stable under continuous deformations. Two series with the same persistence diagram have the same qualitative dynamical structure (number and prominence of cycles, connectivity patterns).

**References:**
- Gidea & Katz (2018), "Topological Data Analysis of Financial Time Series" (arXiv)
- Giotto-TDA (JMLR, 2021)

### Transfer Entropy

**Transfer entropy** measures the directed information flow from one series to another — how much knowing the past of series X reduces uncertainty about the future of series Y.

**Algorithm:**
1. Estimate conditional entropies via histogram binning
2. `TE(X→Y) = H(Y_future | Y_past) - H(Y_future | Y_past, X_past)`
3. Normalize to [0, 1]
4. Score: symmetric TE similarity between query and candidate

**What it captures:** Causal/predictive relationships. Two series with high mutual transfer entropy share similar predictive dynamics — the past of each is informative about the future of the other.

**References:**
- Schreiber (2000), "Measuring Information Transfer"

### Regime Tagger

Lightweight classification of each window's market regime. Not a scoring method per se, but enriches `MatchResult` with a regime label.

**Labels:** `trending_up`, `trending_down`, `mean_reverting`, `high_vol`, `low_vol`

**Features:**
- Linear regression slope (trend direction)
- Hurst exponent via DFA (trending vs. mean-reverting)
- Realized volatility percentile

---

## Scoring & Confidence

The composite confidence score combines all active method scores via weighted sum with dynamic renormalization:

```
confidence = 100 × Σ (w_i / Σ w_active) × score_i
```

where `w_active` are weights of methods in `config.active_methods`. This means:
- Disabling a method doesn't drag scores to zero
- Adding a method immediately gives it proper weight
- Weights always sum to 1.0 across active methods

**Default weights:**

| Method | Weight | Rationale |
|--------|--------|-----------|
| Bempedelis R² | 0.20 | Strong discriminator for fractal similarity |
| Koopman | 0.20 | Captures dynamical equivalence |
| Wavelet spectrum | 0.15 | Multi-scale fingerprint |
| Bempedelis smoothness | 0.10 | Regularizer for transform quality |
| EMD | 0.10 | Complementary multi-scale view |
| TDA | 0.08 | Topological invariants |
| DTW | 0.07 | Baseline shape (cheap, always available) |
| Pearson warped | 0.05 | Correlation sanity check |
| Transfer entropy | 0.05 | Information-theoretic signal |

---

## Forecast Cone

After finding similar historical patterns, the projection engine extracts what happened after each match and builds a probabilistic forecast cone.

**Algorithm:**
1. For each match, extract `forward_bars` of history after the match end
2. Convert to cumulative returns relative to match end price
3. Weight paths by confidence score
4. Compute weighted quantiles at each forward bar: P10, P25, P50, P75, P90
5. **Confidence decay** (optional): widen bands over time by factor `1 + decay_rate × bar`

**Koopman blend** (optional): Blend the Koopman forward evolution trajectory into P50:

```
P50_blended[t] = (1 - w) × P50_historical[t] + w × koopman_trajectory[t]
```

---

## Koopman Forward Evolution

Beyond matching, the Koopman operator can evolve the query pattern forward in time.

**Algorithm:**
1. Fit Koopman operator K on delay-embedded query
2. **Eigenvalue clamping:** Project eigenvalues to unit disk (|λ| ≤ 1) to prevent explosive trajectories, preserving phase (oscillation frequency)
3. Evolve last state forward: `x(t+1) = K × x(t)` for `forward_bars` steps
4. Uncertainty: reconstruction residual σ × √t

**Output:** `KoopmanForecast` with `.trajectory` (point forecast) and `.uncertainty` (growing error bars).

This provides a physics-informed complement to the statistical forecast cone — the Koopman trajectory encodes the system's own dynamics, while the historical cone encodes what "similar situations" led to.

**References:**
- Koopa (NeurIPS 2023), "Learning Non-stationary Time Series with Koopman Predictors"
- KoopSTD (ICML 2025), "Reliable Similarity Analysis via Koopman Spectrum"
- Koopman Neural Forecaster (arXiv:2210.03675)

---

## Backtester

Walk-forward validation with no look-ahead bias.

**Protocol:**
1. For each trial, pick random position `p` in history (minimum lookback = 3× window_size)
2. `query = history[p : p + window_size]`
3. `lookback = history[:p]` (strict no-future data)
4. Run `search(query, lookback)` → `project()` → forecast cone
5. Compare forecast to `actual = history[p + window_size : p + window_size + forward_bars]`

**Metrics:**

| Metric | Description |
|--------|-------------|
| **Hit rate** | Fraction of trials where P50 predicted correct direction |
| **MAE** | Mean absolute error of P50 endpoint vs actual |
| **Calibration** | For each percentile P, what fraction of actuals fell below P? (should equal P/100) |
| **CRPS** | Continuous Ranked Probability Score — measures sharpness + calibration jointly (lower = better) |

**References:**
- Bank of England (1990s), fan chart introduction
- ECB Fan Charts 2.0 — flexible forecast distributions
- RBA (2017), fan charts from historical errors (RDP 2017-01)

---

## References

### Core Methods
1. Sakoe, H. & Chiba, S. (1978). Dynamic programming algorithm optimization for spoken word recognition. *IEEE Trans. ASSP*.
2. Lin, J. et al. SAX: A Novel Symbolic Representation of Time Series. *DAMI*.
3. Rakthanmanon, T. et al. (2012). Searching and Mining Trillions of Time Series Subsequences under Dynamic Time Warping. *KDD*.
4. Huang, N.E. et al. (1998). The Empirical Mode Decomposition and the Hilbert Spectrum. *Proc. Royal Society A*.
5. Schreiber, T. (2000). Measuring Information Transfer. *Physical Review Letters*.
6. Gidea, M. & Katz, Y. (2018). Topological Data Analysis of Financial Time Series. *arXiv*.

### Dynamical Systems
7. Koopman, B.O. (1931). Hamiltonian Systems and Transformations in Hilbert Space. *PNAS*.
8. Takens, F. (1981). Detecting Strange Attractors in Turbulence. *Springer Lecture Notes in Mathematics*.
9. Brunton, S.L. et al. Modern Koopman Theory for Dynamical Systems. *SIAM Review*.
10. Mann, J. & Kutz, J.N. (2016). Dynamic Mode Decomposition for Financial Trading Strategies. *arXiv:1508.04487*.

### Fractal & Multifractal Analysis
11. Mandelbrot, B.B. & Wallis, J.R. Rescaled Range Analysis.
12. Gabaix, X. et al. (2003). A Theory of Power-Law Distributions in Financial Market Fluctuations. *Nature*.
13. Jaffard, S. et al. Wavelet Leaders in Multifractal Analysis. *Springer*.

### Forecasting & Validation
14. Koopa (NeurIPS 2023). Learning Non-stationary Time Series with Koopman Predictors.
15. KoopSTD (ICML 2025). Reliable Similarity Analysis via Koopman Spectrum.
16. Wu, R. & Keogh, E. (2020). FastDTW is approximate and Generally Slower than the Algorithm it Approximates. *arXiv:2003.11246*.
