# The Similarity Architecture Principles

This document captures architectural principles and module-level design rules.

For the current repo layout and system map, see:

- [ARCHITECTURE_OVERVIEW.md](/Users/buyantogtokh/.codex/worktrees/b679/14/docs/architecture/ARCHITECTURE_OVERVIEW.md)

## Guiding Principles

### 1. Plan for Data Model Stability
Choose data models carefully early on. Changing schemas under load is one of the hardest scaling problems.

**Applied here:**
- `TimeSeries`, `MatchResult`, `ScoreBreakdown`, `Config` are frozen dataclass contracts.
- `MatchResult` carries all per-match metadata (scores, transforms, eigenvalues) so downstream consumers never need to re-derive.
- `FeatureStore` key design is locked in: `(dataset_hash, window_start, window_length, method, params_hash)`.
- New scoring methods add fields to `ScoreBreakdown`; they never remove or rename existing ones.

### 2. Clean Separation of Concerns
Each module has one clear responsibility. A monolith is fine to start, but structure it so extraction into services is possible when needed.

**Module responsibilities:**

| Module | Responsibility | Scales independently? |
|---|---|---|
| `io/loader.py` | Data ingestion (CSV, parquet, DataFrame, array) | Yes - swap for streaming loader later |
| `core/normalizer.py` | Per-window normalization transforms | Yes - stateless pure functions |
| `core/windower.py` | Sliding window generation, multi-scale indices | Yes - memory-bound, can chunk |
| `core/scorer.py` | Score aggregation and confidence computation | Yes - pure math |
| `core/matcher.py` | Pipeline orchestration (windowing -> scoring -> ranking) | Orchestrator, delegates to methods |
| `methods/` | Individual matching algorithms (DTW, Bempedelis, etc.) | Yes - each method is independent |
| `core/projector.py` | Forward projection from matches | Yes - stateless |
| `viz/plotter.py` | Visualization | Yes - presentation only |
| `config.py` | Configuration and hyperparameters | Shared, immutable per-search |
| `api.py` | Public API surface | Thin orchestration layer |

**Rules:**
- Methods in `methods/` never import each other. They only depend on `core/` and `config.py`.
- `matcher.py` orchestrates but does not implement scoring logic inline.
- `api.py` is a thin wrapper — business logic lives in `core/`.
- Each scoring method exposes a `score_candidate(query, candidate) -> float` interface.

### 3. Design for Statelessness
Stateless services are trivially horizontally scalable.

**Applied here:**
- All scoring functions are pure: `f(query, candidate, config) -> score`. No side effects.
- `Config` is never mutated after construction. `search()` copies config before applying overrides.
- No global state, no singletons, no module-level caches.
- `TimeSeries` is a value object — safe to share across threads.
- Future `FeatureStore` is the only stateful component, and it sits behind a clean interface.

## Core Engine Data Flow

```
load() -> TimeSeries
              |
              v
search(query, history, config)
  |
  +--> normalize(query)
  +--> sliding_windows(history) / multi_scale_indices(history)
  |
  +--> [Tier 1: fast pre-filters]
  |      SAX filter -> Matrix Profile -> Wavelet Leaders
  |      Ranked union -> top N candidates
  |
  +--> [Tier 2: quality scoring per candidate]
  |      normalize(candidate)
  |      dtw_score(query, candidate)
  |      pearson_score(query, candidate)
  |      bempedelis_score(query, candidate)
  |      koopman_score(query, candidate)
  |      ... each method independent, parallelizable
  |
  +--> compute_confidence(breakdown, config) -> composite score
  +--> rank and return top_k MatchResults
              |
              v
project(matches, history) -> Forecast
              |
              v
plot(results, forecast) -> visualization
```

## Scaling Path

1. **Now (monolith):** Single process, all methods run sequentially in `matcher.py`.
2. **Near-term:** `FeatureStore` caching eliminates redundant computation. Tier 2 methods parallelized via `multiprocessing`/`joblib`.
3. **Later:** Each method in `methods/` can become a worker behind a task queue. `matcher.py` dispatches and collects results. Data model stays the same.
