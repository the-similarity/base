# The Similarity

Research-grade pattern matching, forecasting, and terrain/simulation experimentation built around one central Python engine.

This repository is a monorepo, not just a single package.

## Top-Level Components

- `the_similarity/`: core Python engine
- `the-similarity-api/`: FastAPI backend service
- `the-similarity-data/`: ETL + parquet + DuckDB warehouse
- `the-similarity-app/`: main Next.js frontend
- `the-similarity-fractal/`: Three.js terrain / 3D surface
- `the-similarity-playground/`: research workbench
- `the-similarity-landing/`: placeholder

For the current architecture map, see:

- [docs/architecture/ARCHITECTURE_OVERVIEW.md](/Users/buyantogtokh/.codex/worktrees/b679/14/docs/architecture/ARCHITECTURE_OVERVIEW.md)

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
history = ts.load("gold_5m.csv", column="close")
query = history[-60:]

# Find similar patterns
results = ts.search(query, history, top_k=10)

# Forecast from the match set
forecast = ts.project(results, history, forward_bars=30)

# Plot results
ts.plot(results, forecast)
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

SAX + MASS prefilter → DTW + Pearson core → Tier 2 enrichment → final rank → projection / forecasting

## License

MIT
