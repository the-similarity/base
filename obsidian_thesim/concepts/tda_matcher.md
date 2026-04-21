# tda_matcher

**Module:** `the_similarity/methods/tda_matcher.py`
**Related research:** [[Survey TDA EMD wavelets SAX]], [[04-tda-emd-wavelets-sax-matrix-profile]]

## What it does

Computes persistent homology (H0 connected components, H1 loops) on Takens delay-embedded time series and compares two series via Wasserstein distance on their persistence diagrams.

## Public API

| Function | Signature | Returns |
|---|---|---|
| `compute_persistence` | `(series, dim=4, lag=3)` | `{"H0": (n,2), "H1": (n,2)}` |
| `persistence_distance` | `(diag_a, diag_b)` | `float ≥ 0` |
| `tda_score` | `(distance: float)` | `float ∈ [0, 1]` |
| `compare` | `(query, candidate, dim=4, lag=3)` | `float ∈ [0, 1]` |

**Constant:** `TDA_MIN_WINDOW = 40` — minimum series length for meaningful TDA.

## Key invariants (verified by test_tda_matcher.py)

- **H0 infinite-death stripping**: `compute_persistence` removes the single infinite-death connected component from H0 before returning. All H0 death values are guaranteed finite.
- **Short-series guard**: series `< TDA_MIN_WINDOW` → empty diagrams from `compute_persistence`; `compare` returns `0.0`.
- **Constant-series guard**: `ptp < 1e-12` → trivial (empty) diagrams; `compare` returns `0.0` for both-constant inputs.
- **Wasserstein weighting**: `distance = 0.4 * d_H0 + 0.6 * d_H1` (H1 loop structure weighted higher).
- **Score formula**: `tda_score(d) = exp(-2d)` → monotone decreasing, `tda_score(0) = 1.0`.
- **Type coercion**: `compare` accepts Python lists, int arrays, float32 arrays, and 2D column vectors (all raveled to float64 internally).

## Optional dependencies

`ripser` and `persim` are optional. The module sets `HAS_TDA = False` when absent; `_require_tda()` raises `RuntimeError` on any call. Tests use `pytest.importorskip` to skip the entire test module gracefully.

**Testing pattern** (reuse for any optional-dep module):
```python
pytest.importorskip("ripser")
pytest.importorskip("persim")
from the_similarity.methods.tda_matcher import ...  # noqa: E402
```
The imports must come *after* `importorskip` because the module imports ripser/persim at import time.
