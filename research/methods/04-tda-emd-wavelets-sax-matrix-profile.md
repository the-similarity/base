# Advanced Time Series Methods: TDA, EMD, Wavelets, SAX, Matrix Profile, Transfer Entropy

## 1. Topological Data Analysis (TDA) for Time Series

### Core Concepts

TDA uses **persistent homology** to extract topological features (connected components, loops, voids) from data. Betti numbers count k-dimensional holes: Betti-0 = connected components, Betti-1 = loops. **Persistence diagrams** plot birth-death pairs of topological features across a filtration parameter.

**Pipeline for time series:**
1. Apply **Takens time-delay embedding** to transform univariate series into a point cloud
2. Construct a filtration (typically Vietoris-Rips) over the point cloud
3. Compute persistent homology to obtain persistence diagrams

### Wasserstein Distance

The p-th Wasserstein distance between persistence diagrams is the cost of optimal matching between points (with option to match to diagonal). Provides a metric for comparing topological signatures of different time series windows.

### Financial Applications

- **Crash detection**: L^p norms of persistence landscapes show strong rising trend ~250 days before major crashes (Gidea & Katz, 2018)
- **Change point detection**: Using 98% significance threshold, detected 2011 European debt crisis, 2016 Brexit, 2020 COVID-19, 2022 Russia-Ukraine energy crisis
- **Regime identification**: During crashes, homology groups become less persistent as correlation structures fragment

### Python Libraries

- **[ripser.py](https://github.com/scikit-tda/ripser.py)**: Fast persistent homology wrapping C++ Ripser engine
- **[persim](https://pypi.org/project/persim/)**: Persistence diagram visualization and distance computation
- **[giotto-tda](https://github.com/giotto-ai/giotto-tda)**: Most comprehensive TDA toolkit, scikit-learn compatible. Has dedicated [stock market crash detection tutorial](https://dev.to/giotto_ai/detecting-stock-market-crashes-with-topological-data-analysis-322c)
- **[GUDHI](https://github.com/GUDHI/TDA-tutorial)**: Alternative TDA library with Python bindings

## 2. Empirical Mode Decomposition (EMD)

### Algorithm and IMFs

EMD is a data-driven, adaptive decomposition for non-stationary, non-linear signals (Huang et al., 1998). Decomposes signal into **Intrinsic Mode Functions (IMFs)** via the sifting process:

1. Identify all local maxima and minima
2. Fit upper and lower envelopes via cubic spline
3. Compute mean of envelopes
4. Subtract mean to get candidate IMF
5. Repeat until IMF conditions satisfied
6. Subtract IMF from original and repeat on residual

First IMF = highest-frequency; subsequent IMFs = progressively lower frequencies; final residual = trend.

### EEMD and CEEMDAN

- **EEMD (Ensemble EMD)**: Addresses mode mixing by adding white noise, performing EMD on each realization, averaging IMFs
- **CEEMDAN**: Adds noise adaptively at each stage, provides exact reconstruction, better spectral separation. Consistently outperforms EMD, EEMD, and CEEMD
- **ICEEMDAN**: Improved variant, combined with wavelet threshold denoising for financial classification

### Financial Applications

- **Denoising**: Decompose prices, discard high-frequency IMFs (noise), reconstruct
- **Multi-scale analysis**: Each IMF captures different market time scale
- **Hybrid models**: EMD/CEEMDAN decomposition + ML on individual IMFs

### Python Libraries

- **[PyEMD](https://github.com/laszukdawid/PyEMD)** (pip: `EMD-signal`): EMD, EEMD, CEEMDAN. Usage: `from PyEMD import EMD; IMFs = EMD()(signal)`
- **[emd](https://emd.readthedocs.io/en/stable/)** (pip: `emd`): From Oxford MRC BNDU, includes Hilbert-Huang spectral analysis

## 3. Wavelet Analysis

### Continuous vs Discrete

- **DWT (Discrete)**: Dyadic scales (powers of 2). O(n). Decomposes into approximation + detail coefficients
- **CWT (Continuous)**: Arbitrary scales, finer time-frequency resolution. More expensive but removes dyadic restriction
- **SWT (Stationary)**: Translation-invariant DWT variant, no downsampling

### Wavelet Leaders and Multifractal Spectrum

Wavelet leaders = supremum of wavelet coefficients in local neighborhood across scales. Foundation for robust multifractal singularity spectrum estimation (f(alpha) of Holder exponents).

Python:
- **[pymultifracs](https://github.com/neurospin/pymultifracs)**: Wavelet coefficients, leaders, p-leaders, structure functions, cumulants, multifractal spectrum, bootstrap CIs
- **[mfanalysis](https://github.com/omardrwch/mfanalysis)**: Based on PLBMF Matlab toolbox

### Financial Applications

- **Volatility analysis**: CWT (Morlet wavelet) characterizes periods of increased volatility
- **Regime detection**: Low-frequency = trend, high-frequency = daily volatility
- **Denoising**: Wavelet thresholding removes microstructure noise
- **Price jump detection**: Bouri et al. (PNAS, 2024) identified new classes of financial price jumps

### Python Library

- **[PyWavelets (pywt)](https://github.com/PyWavelets/pywt)**: Standard wavelet library. DWT, CWT, SWT, wavelet packets. [Docs](https://pywavelets.readthedocs.io/)
- **[PyCWT](https://pycwt.readthedocs.io/)**: Cross-wavelet and wavelet coherence analysis

## 4. SAX (Symbolic Aggregate approXimation)

### Algorithm

1. **PAA**: Divide z-normalized series into w segments; replace each with its mean
2. **Symbolic mapping**: Map PAA values to letters using breakpoints from standard normal (equiprobable symbols)

### MINDIST Distance

```
MINDIST(X, Y) = sqrt(n/w) * sqrt(sum(dist(x_i, y_i)^2))
```

Critical property: **MINDIST lower-bounds Euclidean distance** -- no false dismissals when used as pre-filter.

### Use as Pre-filter

1. Convert all time series to SAX representations
2. For query, convert to SAX, compute MINDIST against all candidates
3. Prune candidates where MINDIST exceeds threshold
4. Compute exact distance only on survivors

Dramatically reduces computation while guaranteeing no false dismissals.

### Python Libraries

- **[pyts](https://pyts.readthedocs.io/)**: `pyts.approximation.SymbolicAggregateApproximation`. scikit-learn compatible
- **[saxpy](https://github.com/seninp/saxpy)**: SAX + HOT-SAX (anomaly discovery) + SAX-VSM (motif discovery)

## 5. Matrix Profile

### Algorithms

The Matrix Profile stores, for every subsequence of length m, the z-normalized Euclidean distance to its nearest neighbor.

- **STAMP**: Original algorithm, O(n^2 log n)
- **STOMP**: Exploits ordering to reuse calculations, O(n^2)
- **SCRIMP++**: Further optimizations with anytime capabilities
- **GPU-STOMP**: GPU-accelerated variant
- **DAMP**: Optimized for streaming data, handles 100K+ Hz

### Motif Discovery and Discord Detection

- **Motifs**: Smallest matrix profile values = most repeated patterns
- **Discords**: Largest values = anomalies
- **Time Series Chains**: Gradually evolving sequences of motifs
- No false positives or false dismissals for both motifs and discords

### Python Library

**[STUMPY](https://github.com/stumpy-dev/stumpy)** (pip: `stumpy`):
- `stumpy.stump(T, m)`: Compute matrix profile (parallelized, JIT-compiled)
- `stumpy.gpu_stump(T, m)`: GPU version (up to 16 GPUs)
- `stumpy.stumpi`: Incremental/streaming matrix profile
- `stumpy.mstump`: Multidimensional matrix profile
- Tested on 100M+ data points with 256 distributed CPU cores
- [Docs](https://stumpy.readthedocs.io/en/latest/)

## 6. Transfer Entropy

### Definition

Transfer entropy (Schreiber, 2000) measures directed information transfer between stochastic processes:

```
T_{X->Y} = H(Y_t | Y_{t-1:t-L}) - H(Y_t | Y_{t-1:t-L}, X_{t-1:t-L})
```

Equivalently: conditional mutual information between past of X and future of Y, given past of Y.

Properties:
- **Asymmetric**: Captures directionality
- **Non-parametric**: No model assumptions
- **Generalizes Granger causality**: For Gaussian processes, reduces to Granger causality
- **Detects non-linear relationships** where linear methods fail

### Estimation Methods

- **Binning/histogram**: Simple but sensitive to bin size
- **Kernel density estimation**: Smooth probability estimation
- **KSG**: k-nearest-neighbor based, effective for continuous data
- **Ordinal/permutation**: Based on ordinal patterns, robust to noise

### Financial Applications

- Directional information flow between assets/sectors/markets
- Lead-lag relationships between stock indices
- Causal influence of social media sentiment on crypto prices
- Effective connectivity: economic policy uncertainty -> investor sentiment -> stock markets

### Python Libraries

- **[PyCausality](https://github.com/ZacKeskin/PyCausality)**: Purpose-built for causality on pandas DataFrames
- **[PyInform](https://elife-asu.github.io/PyInform/)**: Information-theoretic measures backed by C library
- **[infomeasure](https://www.nature.com/articles/s41598-025-14053-5)**: Comprehensive package, multiple estimation backends (Scientific Reports, 2025)
- **[JIDT](https://github.com/jlizier/jidt/wiki/PythonExamples)**: Java toolkit with Python bindings

## References

- [TDA Crash Detection (Gidea & Katz, arXiv)](https://arxiv.org/abs/1703.04385)
- [Change Point Detection via TDA (MDPI 2025)](https://www.mdpi.com/2079-8954/13/10/875)
- [giotto-tda (JMLR)](https://www.jmlr.org/papers/volume22/20-325/20-325.pdf)
- [EMD (Wikipedia)](https://en.wikipedia.org/wiki/Hilbert%E2%80%93Huang_transform)
- [CEEMDAN Comparison (PeerJ 2024)](https://peerj.com/articles/cs-1852/)
- [PyEMD GitHub](https://github.com/laszukdawid/PyEMD)
- [Wavelet Leaders (Jaffard et al., Springer)](https://link.springer.com/chapter/10.1007/978-3-7643-7778-6_17)
- [Financial Price Jumps with Wavelets (PNAS 2024)](https://www.pnas.org/doi/10.1073/pnas.2409156121)
- [pymultifracs GitHub](https://github.com/neurospin/pymultifracs)
- [SAX Original Paper](https://cs.gmu.edu/~jessica/SAX_DAMI_preprint.pdf)
- [UCR Matrix Profile Page](https://www.cs.ucr.edu/~eamonn/MatrixProfile.html)
- [STUMPY GitHub](https://github.com/stumpy-dev/stumpy)
- [Transfer Entropy (Wikipedia)](https://en.wikipedia.org/wiki/Transfer_entropy)
- [Transfer Entropy Financial Applications](https://bookdown.org/souzatharsis/open-quant-live-book/how-to-measure-statistical-causality-a-transfer-entropy-approach-with-financial-applications.html)
- [PyCausality GitHub](https://github.com/ZacKeskin/PyCausality)
