# EMD Matcher

**File:** `the_similarity/methods/emd_matcher.py`
**Tests:** `the_similarity/tests/test_emd_matcher.py`

## What it does

Empirical Mode Decomposition (EMD) matcher decomposes two time series into Intrinsic Mode Functions (IMFs) via the PyEMD library, then computes an **energy-weighted L2 distance** across corresponding IMF pairs. Used as a Tier 2 enrichment method in [[matcher]].

## Key functions

| Function | Returns | Notes |
|---|---|---|
| `decompose_emd(series, max_imfs=6)` | `list[NDArray]` | Falls back to `[series]` on PyEMD failure |
| `imf_energy(imf)` | `float` | Sum of squared values |
| `emd_match(query, candidate, max_imfs=6)` | `(score, distance)` | Returns `(0.0, inf)` on guard failures |
| `emd_score(query, candidate, max_imfs=6)` | `float` | Convenience wrapper for `emd_match()[0]` |

## Score formula

```
score = exp(-total_distance)
total_distance = Σ_i  weight_i × L2(q_imf_i[:min_len] − c_imf_i[:min_len]) / min_len
weight_i = energy(q_imf_i) / Σ energy(q_imf_j)
```

Score is always in `[0, 1]`; identical series give `score = 1.0` exactly.

## Guard conditions → (0.0, inf)

- Either series has fewer than 10 samples
- Either series has `std == 0` (constant)
- Any unhandled exception during decomposition

## IMF alignment

Query and candidate may produce different numbers of IMFs. The shorter list is zero-padded to `max(n_q, n_c)` before computing distances, so energy weights are derived solely from the query IMFs.

## Testing insights

- `score = exp(-distance)` holds exactly (tested in `test_emd_match_score_equals_exp_neg_distance`)
- Identical inputs always produce `distance ≈ 0` because PyEMD is deterministic for the same input
- Integer arrays are accepted — `decompose_emd` casts to `float64` internally
- Score range `[0, 1]` is guaranteed by the exponential mapping, not clamped

## Related

- [[emd_2d]] — 2D variant using the same decomposition strategy
- [[matcher]] — calls `emd_score` as Tier 2 enrichment
