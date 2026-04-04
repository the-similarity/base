# The Similarity

Research-grade time series pattern matching and prediction using 9 mathematical methods.

## Install

```bash
# Requires Python 3.11+
pip install git+https://github.com/the-similarity/base.git

# With TDA support (ripser + persim)
pip install "the-similarity[tda] @ git+https://github.com/the-similarity/base.git"

# With API server (FastAPI + Uvicorn)
pip install "the-similarity[api] @ git+https://github.com/the-similarity/base.git"
```

## Quick Start

```python
import the_similarity as ts

# Load data
ref, query = ts.load("gold_5m.csv", query_window=60, reference_window=500)

# Find similar patterns
matches = ts.search(ref, query)

# Forecast from best match
cone = ts.project(ref, matches[0])

# Plot results
ts.plot(ref, query, matches, cone)
```

## Methods

| # | Method | Type |
|---|--------|------|
| 1 | DTW (Dynamic Time Warping) | Core |
| 2 | Pearson Correlation | Core |
| 3 | SAX + MASS | Prefilter |
| 4 | Matrix Profile | Prefilter |
| 5 | Bempedelis Spectral | Tier 2 |
| 6 | Koopman Operator | Tier 2 |
| 7 | Wavelet Leaders | Tier 2 |
| 8 | EMD (Empirical Mode Decomposition) | Tier 2 |
| 9 | TDA (Topological Data Analysis) | Tier 2 |
| 10 | Transfer Entropy | Tier 2 |

## Pipeline

SAX + MASS prefilter → DTW + Pearson core → Tier 2 enrichment (7 methods) → final rank

## License

MIT
