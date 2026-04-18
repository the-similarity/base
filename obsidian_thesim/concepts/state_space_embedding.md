# State-Space Embedding

**Code**: `the_similarity/core/state_space.py`
**Tests**: `the_similarity/tests/test_state_space.py`

## What it does

Normalizes each pillar's run summary metrics into a fixed-length vector in [0, 1]^d, enabling cross-pillar nearest-neighbor search and visualization.

## Key components

- **StateVector** — dataclass holding a normalized `np.ndarray`, source metadata, and a human-readable label.
- **Pillar extractors** — `extract_finance_state`, `extract_copies_state`, `extract_worlds_state`. Each maps pillar-specific metric keys to dimensions via min-max normalization with documented ranges. Missing keys default to 0.5 (neutral).
- **StateIndex** — brute-force cosine-distance index backed by numpy. Supports `query_nearest(k)` and `query_radius(r)`. Lazy matrix cache invalidated on mutation.
- **build_index_from_registry** — bridges [[RunRegistry]] -> StateIndex by iterating pillar-tagged runs and dispatching to the correct extractor.
- **reduce_to_3d / reduce_to_2d** — PCA or t-SNE projection for visualization.

## Design decisions

| Decision | Why |
|----------|-----|
| Brute-force cosine, no faiss | Registry holds hundreds of runs, not millions. Zero external deps. |
| Pad shorter pillars to MAX_DIM with 0.5 | Cosine distance is direction-sensitive; neutral padding contributes proportionally less than active dimensions. |
| Min-max ranges hardcoded | Avoids needing a warm-up pass over the registry. Ranges are documented and based on observed outputs. |
| Missing fields -> 0.5 | Neutral midpoint does not bias cosine distance toward or away from any axis. |

## Normalization ranges

| Pillar | Metrics | Dim |
|--------|---------|-----|
| Finance | hit_rate, crps, coverage, trust_score, calibration_grade_numeric | 5 |
| Copies | fidelity_score, privacy_score, utility_gap | 3 (padded to 5) |
| Worlds | alive, dead, mean_energy, food_count, population_density | 5 |

## Related

- [[RunRegistry]] — data source for `build_index_from_registry`
- [[embedding]] — Takens delay embedding for 1D time series (different purpose)
