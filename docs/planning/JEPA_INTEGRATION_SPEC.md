# JEPA Integration Spec — Production Surface Design

> **Status**: Design spec (no production code changes)
> **Date**: 2026-04-12
> **Scope**: Where JEPA slots into the existing 9-method tiered pipeline

---

## 1. Config surface (`the_similarity/config.py`)

Three new fields on the `Config` dataclass:

```python
# -------------------------------------------------------------------------
# JEPA (Joint Embedding Predictive Architecture)
# -------------------------------------------------------------------------
# jepa_enabled: Master toggle. When False, JEPA is completely skipped —
#   no imports, no embedding computation, no weight entry. This ensures
#   backward-compatible behavior with zero overhead when JEPA is off.
# jepa_weight: Relative importance in the composite confidence score.
#   Suggested initial value 0.15, between Koopman (0.20) and wavelet (0.15),
#   reflecting that JEPA captures learned latent-space similarity which is
#   complementary to but less interpretable than dynamical methods.
# jepa_embedding_path: Filesystem path to the pretrained JEPA encoder
#   checkpoint (.pt file). The matcher lazy-loads this once per process
#   lifetime and caches the model in a module-level singleton.
jepa_enabled: bool = False
jepa_weight: float = 0.15
jepa_embedding_path: str | None = None
```

**Weights dict update** (only when `jepa_enabled=True`):

```python
weights: dict[str, float] = field(default_factory=lambda: {
    # ... existing 9 entries unchanged ...
    "jepa_similarity": 0.15,   # JEPA latent-space cosine similarity
})
```

The weight is present in the dict but JEPA will only be included in
`active_methods` when `jepa_enabled=True`. Because the scorer renormalizes
across active methods, adding the key to `weights` with a nonzero value has
no effect unless it also appears in `active_methods`.

**`active_methods` conditional inclusion**: The engine already filters
`active_methods` at runtime. JEPA gets appended to the list only when
`jepa_enabled` is True:

```python
active_methods: list[str] = field(default_factory=lambda: [
    # ... existing 9 entries ...
    # "jepa_similarity" is NOT here by default — added at runtime
    # when jepa_enabled=True via Config post-init or search() logic
])
```

---

## 2. ScoreBreakdown surface (`the_similarity/core/scorer.py`)

One new field:

```python
# --- JEPA latent-space similarity ---
# Cosine similarity between the query and candidate embeddings produced
# by a pretrained JEPA encoder. Range [0, 1] where 1 = identical latent
# representations. Default 0.0 means "not computed" (JEPA disabled).
jepa_similarity: float = 0.0
```

Update `_SCORE_FIELDS` to include `"jepa_similarity"` at the end.

**Range**: [0, 1]. Cosine similarity of L2-normalized embeddings is
naturally in [-1, 1]; we map it to [0, 1] via `(cos_sim + 1) / 2`, same
as the Pearson mapping already used for `pearson_warped`.

**Default**: 0.0. When JEPA is disabled, this field stays at its default
and is excluded from `active_methods`, so it contributes nothing to the
composite score.

---

## 3. Matcher integration point (`the_similarity/core/matcher.py`)

**JEPA belongs in Tier 2 enrichment**, not pre-filter and not a separate
reranking step. Rationale:

| Option | Pros | Cons |
|--------|------|------|
| Tier 0 pre-filter | Could replace SAX+MASS | Requires embedding ALL windows upfront (O(N) GPU forward passes) — too expensive for interactive search |
| Tier 1 cheap scoring | Runs on ~1000 candidates | Still too many GPU calls; DTW+Pearson are CPU-only and fast |
| **Tier 2 enrichment** | Runs on ~20 candidates only | Acceptable GPU budget (20 forward passes); natural home for expensive methods |
| Separate reranker | Conceptual clarity | Adds pipeline complexity for no practical benefit vs. Tier 2 |

### Integration mechanics

1. Add `"jepa_similarity"` to `TIER2_SCORE_FIELDS` set:
   ```python
   TIER2_SCORE_FIELDS = {
       "koopman", "wavelet_spectrum", "emd", "tda", "transfer_entropy",
       "jepa_similarity",  # <-- new
   }
   ```

2. In `_enrich_tier2()`, add a JEPA block after the existing methods,
   guarded by the lazy import pattern (see Section 7):
   ```python
   if "jepa_similarity" in active_fields:
       from the_similarity.methods.jepa_matcher import jepa_score
       cand_norm = normalize(raw, "logreturn_zscore")
       try:
           candidate.breakdown.jepa_similarity = jepa_score(
               query_shape, cand_norm, config.jepa_embedding_path
           )
       except Exception:
           pass
   ```

3. The JEPA method module (`the_similarity/methods/jepa_matcher.py`) will
   handle model loading, embedding, and cosine similarity computation.

### Embedding flow

```
query (1D array)          candidate (1D array)
      |                          |
  normalize                  normalize
      |                          |
  jepa_encode()              jepa_encode()
      |                          |
  embedding_q (d-dim)       embedding_c (d-dim)
      |                          |
      +---- cosine_similarity ---+
                  |
          jepa_similarity [0, 1]
```

The encoder is a pretrained PyTorch model that maps a 1D window of
arbitrary length to a fixed-dimensional latent vector. The model is loaded
once (singleton) and reused across all candidates in a search call.

---

## 4. Caching via FeatureStore

JEPA embeddings are expensive (GPU forward pass) and deterministic for a
given window + model checkpoint. They are ideal candidates for the existing
`FeatureStore` cache.

### Cache key structure

```python
params_hash("jepa_similarity", checkpoint_hash=<sha256_of_checkpoint_path>)
```

The `checkpoint_hash` ensures cache invalidation when the model is
retrained. We hash the file path (not the file contents, which would be
too slow for multi-GB checkpoints). Users who retrain must use a new path
or clear the cache.

### Cache integration in `_enrich_tier2()`

```python
if feature_store is not None:
    p_hash = params_hash("jepa_similarity", checkpoint_hash=_ckpt_hash)
    candidate.breakdown.jepa_similarity = feature_store.get_or_compute(
        dataset_hash=ds_hash,
        window_start=candidate.start_idx,
        window_length=_wlen,
        method="jepa_similarity",
        params_hash=p_hash,
        compute_fn=lambda q=query_shape, c=cand_norm: jepa_score(q, c, ...),
    )
```

### Embedding-level caching (future optimization)

For even better performance, we could cache individual window embeddings
(not just pairwise scores). This would allow reusing the candidate
embedding across different queries. The key would be:

```
(dataset_hash, window_start, window_length, "jepa_embedding", checkpoint_hash)
```

This is a Tier 2 optimization that can be added after the basic
integration is validated.

---

## 5. API surface (`the_similarity/api.py`)

**No new public functions needed.** JEPA integrates entirely through the
existing `search()` function via Config:

```python
cfg = Config(jepa_enabled=True, jepa_embedding_path="/path/to/model.pt")
results = search(query, history, config=cfg)
```

The `SearchResults.summary()` method will need a minor update to include
the JEPA score in its output formatting:

```python
f"jepa={b.jepa_similarity:.2f}"
```

### WebSocket / frontend

The existing `active_methods` override mechanism works unchanged. The
frontend can toggle JEPA on/off per request by including or excluding
`"jepa_similarity"` in the `active_methods` list sent over WebSocket.

---

## 6. Backward compatibility

**Invariant**: `jepa_enabled=False` (default) produces byte-identical
results to the current engine.

Guarantees:

1. **No import cost**: `torch` is never imported when `jepa_enabled=False`.
   The `jepa_matcher` module uses lazy imports guarded by the active
   methods check in `_enrich_tier2()`.

2. **No score pollution**: `jepa_similarity` defaults to 0.0 in
   `ScoreBreakdown`. Since it is not in `active_methods` by default, the
   scorer's renormalization ignores it entirely.

3. **No weight distortion**: The `weights` dict may include the
   `jepa_similarity` key, but because the scorer only sums weights for
   methods in `active_methods`, the existing 9 methods produce the exact
   same composite score.

4. **No serialization breakage**: Adding a new field with a default to a
   dataclass is backward compatible for pickle, JSON, and dataclass
   construction.

5. **Test suite**: All 347 existing tests pass unchanged because they
   never set `jepa_enabled=True`.

---

## 7. Dependencies

### PyTorch as optional dependency

PyTorch is a ~2GB dependency. It MUST remain optional:

```toml
# pyproject.toml
[project.optional-dependencies]
jepa = ["torch>=2.0"]
```

Installation: `pip install the-similarity[jepa]`

### Lazy import pattern

The method module (`jepa_matcher.py`) uses a lazy import guard:

```python
# the_similarity/methods/jepa_matcher.py

_torch = None
_model_cache: dict[str, object] = {}   # path -> loaded model singleton

def _ensure_torch():
    """Lazy-import torch. Raises ImportError with install hint if missing."""
    global _torch
    if _torch is None:
        try:
            import torch
            _torch = torch
        except ImportError:
            raise ImportError(
                "JEPA requires PyTorch. Install with: "
                "pip install the-similarity[jepa]"
            )
    return _torch
```

This pattern mirrors how `HAS_STUMPY` works in `matrix_profile_filter.py`
for the optional stumpy dependency.

### Model loading singleton

```python
def _load_model(path: str) -> object:
    """Load JEPA encoder, caching across calls within the same process."""
    if path not in _model_cache:
        torch = _ensure_torch()
        _model_cache[path] = torch.jit.load(path, map_location="cpu")
        _model_cache[path].eval()
    return _model_cache[path]
```

This avoids reloading the model for every candidate. The cache is
process-global and never evicted (models are typically <100MB).

---

## 8. Migration path: research to production

### Phase A: Research validation (current — `research/autoresearch/`)

- Train JEPA encoder on financial time series windows
- Evaluate embedding quality: nearest-neighbor retrieval, cluster purity
- Benchmark inference latency per window (target: <5ms on CPU)
- Produce a `.pt` checkpoint via `torch.jit.save()`

### Phase B: Method module stub

1. Create `the_similarity/methods/jepa_matcher.py` with:
   - `jepa_score(query, candidate, model_path) -> float`
   - `jepa_encode(series, model_path) -> np.ndarray`
   - Lazy torch import, model singleton cache
2. Add unit tests with a tiny mock model (no real weights)
3. All existing tests still pass (JEPA disabled by default)

### Phase C: Config + scorer wiring

1. Add `jepa_enabled`, `jepa_weight`, `jepa_embedding_path` to `Config`
2. Add `jepa_similarity` field to `ScoreBreakdown` and `_SCORE_FIELDS`
3. Add `"jepa_similarity"` to `TIER2_SCORE_FIELDS` in `matcher.py`
4. Wire the JEPA block in `_enrich_tier2()`
5. Update `contracts/api.py` -> `ScoreBreakdownResponse` with the new field
6. Update `SearchResults.summary()` formatting
7. Tests: add JEPA-specific tests, verify backward compat with JEPA off

### Phase D: FeatureStore integration

1. Add JEPA caching in `_enrich_tier2()` (same pattern as Koopman etc.)
2. Optionally add embedding-level caching for cross-query reuse

### Phase E: Backtester validation

1. Run `backtest()` with JEPA enabled vs disabled
2. Compare hit_rate, CRPS, calibration metrics
3. Tune `jepa_weight` based on backtester results

### Phase F: Frontend + WebSocket

1. Add JEPA toggle to the frontend method selector
2. Display `jepa_similarity` in the score breakdown UI
3. Ship a default model checkpoint with the package or as a download

---

## 9. Open questions

1. **Embedding dimensionality**: 64? 128? 256? Depends on research results.
   Higher dims give more expressiveness but slower cosine similarity (though
   this is negligible compared to the forward pass).

2. **Normalization**: Should JEPA use `logreturn_zscore` (like most methods)
   or `raw`? The encoder may have its own learned normalization.

3. **GPU vs CPU inference**: For Tier 2 with ~20 candidates, CPU inference
   may be fast enough (<100ms total). GPU adds complexity (device
   management, VRAM). Start with CPU-only.

4. **Model versioning**: How to handle model updates? The checkpoint path
   approach means users explicitly opt into new models. Consider a
   `jepa_model_version` config field for reproducibility.

5. **Multi-scale windows**: The matcher resamples candidates to query
   length for SAX comparison. JEPA may need its own resampling strategy
   or a model that accepts variable-length inputs.

---

## 10. File manifest (what gets created/modified)

| File | Action | Phase |
|------|--------|-------|
| `the_similarity/methods/jepa_matcher.py` | **Create** | B |
| `the_similarity/config.py` | Add 3 fields | C |
| `the_similarity/core/scorer.py` | Add 1 field + update `_SCORE_FIELDS` | C |
| `the_similarity/core/matcher.py` | Add to `TIER2_SCORE_FIELDS` + `_enrich_tier2` block | C |
| `the_similarity/contracts/api.py` | Add field to `ScoreBreakdownResponse` | C |
| `the_similarity/api.py` | Update `summary()` format string | C |
| `the_similarity/tests/test_jepa_matcher.py` | **Create** | B |
| `the_similarity/tests/test_config.py` | Add JEPA config tests | C |
| `the_similarity/tests/test_scorer.py` | Add JEPA score tests | C |
| `pyproject.toml` | Add `[jepa]` optional dep | B |
