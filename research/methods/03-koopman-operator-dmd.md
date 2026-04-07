# Koopman Operator Theory & Dynamic Mode Decomposition for Financial Time Series

## 1. Koopman Operator Theory -- Basics

### Core Concept

The Koopman operator (1931) represents **nonlinear dynamical systems as infinite-dimensional linear operators**. Rather than tracking state evolution in the original nonlinear space, it tracks how *measurement functions* (observables) evolve -- and this evolution is always linear.

Given a discrete-time system `x_{k+1} = F(x_k)`, the Koopman operator `K` acts on observable `g` as:

```
(K g)(x) = g(F(x))
```

This is linear in `g` even when `F` is nonlinear.

### Key Properties
- **Spectral decomposition**: eigenvalues encode growth/decay rates and oscillation frequencies; eigenfunctions define intrinsic coordinate systems; Koopman modes capture spatial structures
- **Eigenvalue interpretation**: magnitude `|lambda|` = growth/decay rate; phase `arg(lambda)` = oscillation frequency
- **Practical challenge**: finding a finite-dimensional approximation of this infinite-dimensional operator

## 2. Extended Dynamic Mode Decomposition (EDMD)

### DMD vs EDMD

**DMD** fits `X' ~ A X` from snapshot pairs. Limited to linear observables (state variables).

**EDMD** introduces a **dictionary of nonlinear observables** `Psi(x) = [psi_1(x), ..., psi_K(x)]` and approximates the Koopman operator in the dictionary's span.

### EDMD Algorithm

1. **Collect snapshot pairs**: `{(x_k, y_k)}` where `y_k = F(x_k)`
2. **Choose dictionary** `Psi`: polynomials, RBFs, Fourier features, or time-delay coordinates
3. **Lift data**: `Psi_X = [Psi(x_1), ..., Psi(x_M)]` and `Psi_Y = [Psi(y_1), ..., Psi(y_M)]`
4. **Solve for Koopman matrix**: `K = Psi_Y * pinv(Psi_X)`
5. **Spectral decomposition**: Eigendecompose `K` for eigenvalues and modes

### Dictionary Choices

| Type | Use Case |
|------|----------|
| Monomials/Polynomials | Low-dimensional polynomial nonlinearities |
| Radial Basis Functions | Localized nonlinear features |
| Random Fourier Features | Kernel approximation (Gaussian) |
| Time-delay coordinates | Scalar time series (connects to Takens) |
| Neural network features | Learned dictionaries (EDMD-DL) |

## 3. Applications to Financial Data

### Why Koopman for Finance?
- **Equation-free modeling**: Dynamics learned from data, no governing equations needed
- **Linear framework for nonlinear dynamics**: Standard linear tools become applicable
- **Spectral decomposition**: Identifies dominant frequencies, growth/decay modes, regime structures

### Key Research

**DMD for Financial Trading (Mann & Kutz, 2016)**:
- Applied DMD to portfolios for algorithmic trading
- DMD provides regression to best-fit linear dynamical system
- Trading strategies beat benchmarks across sectors

**KASSNet (2024-2025)**:
- Integrates Koopman with Neural ODEs and structured state-space modeling
- Regime-resilient financial forecasting

**Koopman Neural Forecaster (KNF)**:
- Uses DNNs to learn linear Koopman space
- Designed for temporal distribution shifts

**Koopa (NeurIPS 2023)**:
- Learns non-stationary dynamics with Koopman predictors
- Decomposes operators as linear combinations of meta-Koopman operators

**KoopSTD (ICML 2025)**:
- Dynamical similarity measurement via Koopman spectrum
- Uses timescale decoupling and spectral residual control
- Maintains invariance under representation-space transformations

## 4. Eigenvalue Analysis for System Matching

Two dynamical systems can be compared by examining their **Koopman eigenvalue spectra**. Similar systems = similar eigenvalue distributions.

### Comparison Approaches
1. **Direct spectral distance**: Compare eigenvalue sets as point clouds in complex plane
2. **Optimal assignment**: Hungarian algorithm for best one-to-one matching
3. **Distribution-based**: Wasserstein distance between eigenvalue distributions

### Distance Properties
- Koopman operator distance satisfies triangle inequality even between matrices of different dimensions
- Better interpretability as linear operator driving dynamics in mapped space

## 5. Takens Delay Embedding

### The Theorem

Takens (1981): a smooth dynamical system's attractor can be reconstructed from scalar time series using delay coordinates:

```
z_t = [h(x_t), h(x_{t-tau}), h(x_{t-2*tau}), ..., h(x_{t-(d-1)*tau})]
```

The theorem guarantees that if `d >= 2n + 1`, the delay embedding is a diffeomorphism.

### Connection to EDMD

Time-delay coordinates serve as a natural dictionary for EDMD. The Hankel matrix from delay embeddings captures nonlinear dynamics without explicit nonlinear basis functions.

### Lag Selection

| Method | Description |
|--------|-------------|
| **ACF** | First zero-crossing or minimum of autocorrelation |
| **Mutual information** | First minimum of time-delayed MI (captures nonlinear dependencies) |
| **Persistent homology** | Topological methods based on point cloud homology |

### Embedding Dimension Selection

| Method | Description |
|--------|-------------|
| **False Nearest Neighbors (FNN)** | Increase d until false NN fraction < 1-2% |
| **Cao's method** | Refinement of FNN avoiding subjective thresholds |
| **Manhattan distance + RQA** | Designed specifically for financial time series |

For financial data: example values in literature are lag tau = 7, dimension d = 4.

## 6. Python Libraries

### PyKoopman (Recommended)
- Maintainer: dynamicslab (Brunton/Kutz group, UW)
- scikit-learn compatible API
- EDMD, NNDMD, continuous-time Koopman
- Observable composition: polynomials, time delays, RBFs, random Fourier
- `pip install pykoopman`
- [GitHub](https://github.com/dynamicslab/pykoopman) | [Docs](https://pykoopman.readthedocs.io/en/master/)

### PyDMD
- Comprehensive DMD toolkit
- Nearly every DMD variant: standard, Optimized, Compressed, Multi-Resolution, Higher-Order, Physics-Informed, Hankel DMD
- `pip install pydmd`
- [GitHub](https://github.com/PyDMD/PyDMD) | [Docs](https://pydmd.github.io/PyDMD/)

### datafold
- EDMD with flexible dictionaries, dictionary learning, streaming EDMD
- scikit-learn compatible
- `pip install datafold`
- [GitHub](https://github.com/datafold-dev/datafold)

### Comparison

| Library | Focus | EDMD | DMD Variants | scikit-learn API |
|---------|-------|------|--------------|-----------------|
| PyKoopman | Koopman | Yes | Limited | Yes |
| PyDMD | DMD methods | No | Comprehensive | Partial |
| datafold | EDMD + geometry | Yes | As backend | Yes |

## 7. Hungarian Algorithm for Eigenvalue Matching

### The Problem

Eigenvalues are unordered sets in the complex plane. The Hungarian algorithm finds the optimal assignment between two sets to compute a meaningful distance.

### Implementation

```python
from scipy.optimize import linear_sum_assignment
import numpy as np

def eigenvalue_distance(eigs_a, eigs_b):
    # Cost matrix: pairwise distances in complex plane
    cost = np.abs(eigs_a[:, None] - eigs_b[None, :])
    # Hungarian algorithm
    row_ind, col_ind = linear_sum_assignment(cost)
    return cost[row_ind, col_ind].sum()
```

- `scipy.optimize.linear_sum_assignment` implements modified Jonker-Volgenant algorithm
- Handles rectangular cost matrices (unequal set sizes)
- For unequal sizes: pad smaller set with zeros; unmatched eigenvalues penalized by modulus

## Pipeline for Financial Similarity via Koopman Spectra

1. **Takens delay embedding**: Embed scalar series using optimal lag (MI) and dimension (FNN)
2. **EDMD decomposition**: Fit Koopman approximation with time-delay dictionary
3. **Extract eigenvalue spectra**: Get Koopman eigenvalues (frequencies, growth rates)
4. **Eigenvalue matching**: Hungarian algorithm for optimal matching
5. **Similarity scoring**: Total matched distance -> similarity score

## References

- [Modern Koopman Theory (Brunton et al., SIAM Review)](https://epubs.siam.org/doi/10.1137/21M1401243)
- [ArXiv: Modern Koopman Theory](https://arxiv.org/abs/2102.12086)
- [EDMD Overview (EmergentMind)](https://www.emergentmind.com/topics/extended-dynamic-mode-decomposition)
- [DMD for Financial Trading (ArXiv)](https://arxiv.org/abs/1508.04487)
- [KoopSTD: Reliable Similarity Analysis (ICML 2025)](https://openreview.net/forum?id=29eZ8pWc8E)
- [KoopSTD GitHub](https://github.com/ZhangShimin1/KoopSTD)
- [Koopman Neural Forecaster (ArXiv)](https://arxiv.org/abs/2210.03675)
- [Koopa: Koopman Predictors (NeurIPS 2023)](https://ise.thss.tsinghua.edu.cn/~mlong/doc/Koopa-nips23.pdf)
- [Takens' Theorem (Wikipedia)](https://en.wikipedia.org/wiki/Takens's_theorem)
- [Manhattan Distance for Financial Embedding (PMC)](https://pmc.ncbi.nlm.nih.gov/articles/PMC9497821/)
- [PyKoopman (GitHub)](https://github.com/dynamicslab/pykoopman)
- [PyDMD (GitHub)](https://github.com/PyDMD/PyDMD)
- [scipy.optimize.linear_sum_assignment](https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.linear_sum_assignment.html)
- [Hungarian Algorithm (Wikipedia)](https://en.wikipedia.org/wiki/Hungarian_algorithm)
