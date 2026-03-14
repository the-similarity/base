# The Similarity Implementation Plan

## Current State

Phase 1 complete + Phase 2a/2b done. Working tiered pipeline with 58 tests passing:
- Loader (CSV, parquet, DataFrame, dict, numpy)
- Normalizer (zscore, minmax, logreturn, logreturn_zscore, raw) with per-method defaults
- Windower (sliding windows, multi-scale indices)
- DTW matcher with Sakoe-Chiba band
- Bempedelis self-similarity transform (multi-start L-BFGS-B) — **integrated into pipeline**
- Scorer with `active_methods` + dynamic weight renormalization (0-100 scale)
- Projector with interpolated weighted quantiles and 5-band forecast cone (p10/25/50/75/90)
- Tiered matcher: prefilter → cheap scoring → Bempedelis enrichment on top-N → final rank
- `CandidateWindow` intermediate dataclass for pipeline state
- `SearchResults` container with `.best`, `.summary()`, `.matches`
- Full API contracts (Pydantic) with `SearchRequest`/`SearchResponse`
- FastAPI backend with live `/search` endpoint
- Playground with `run_local_search()` against real parquet data
- Data bank: stocks, crypto, forex, commodities (parquet, manifest catalog)

## Architecture Decisions (Locked In)

### Normalization Strategy
- Default: `logreturn_zscore` (log-returns → per-window z-score)
- Per-method defaults in `METHOD_NORM_DEFAULTS`:
  - Shape methods (DTW, Pearson, SAX, Matrix Profile, TDA): logreturn_zscore
  - Fractal/dynamical methods (Bempedelis, Koopman, Wavelet): logreturn
  - EMD: raw (needs untransformed data for decomposition)
- Each method normalizes independently per-window, never globally

### Data Alignment
- All matching done in bar-space (60 bars = 60 bars regardless of timeframe)
- Cross-timeframe is explicit opt-in: `search(..., cross_timeframes=["1h", "4h", "1d"])`
- Fractal methods are inherently scale-invariant, so this works naturally

### Active Methods + Weight Renormalization
- `Config.active_methods` controls which methods run (default: `["dtw", "pearson_warped"]`)
- `compute_confidence()` renormalizes weights across only active methods
- Adding a method to `active_methods` immediately gives it proper weight
- All 9 weight slots defined upfront; inactive methods don't drag score to zero

### Tier Architecture (Live)
- **Tier 1 prefilter**: `_score_prefilter()` — Euclidean + Pearson blend (placeholder for SAX/MP/Wavelet)
- **Tier 1 cap**: `config.tier1_candidates` (default 1000) — top candidates by prefilter score
- **Cheap scoring**: DTW + Pearson on all Tier 1 survivors
- **Tier 2 enrichment**: Bempedelis on top `config.tier2_candidates` (default 20) — expensive structural methods
- **Final rank**: `compute_confidence()` across all active methods → top_k returned

### Koopman Eigenvalue Distance
- Euclidean distance in complex plane: |λ₁ - λ₂| in ℂ (preserves phase info)
- Hungarian algorithm for optimal assignment between eigenvalue sets
- Unequal set sizes: pad smaller set with zeros. Unmatched eigenvalues penalized by modulus
- Pre-processing: sort by modulus descending, truncate to top-k above |λ| > 0.05

### Caching (FeatureStore)
```python
class FeatureStore:
    def get_or_compute(self, window_id: str, method: str,
                        compute_fn: Callable) -> MethodResult:
        ...
```
- Key: (dataset_hash, window_start, window_length, method_name, method_params_hash)
- Phase 1-3: dict or shelve. Phase 5: Redis or SQLite. Same interface.
- Precompute Tier 1 features on dataset load → search is O(N×lookup + K×compute)

### Stationarity / Regime Handling
- Lightweight regime tagger on each window (not a full solution, just a label):
  {trending_up, trending_down, mean_reverting, high_vol, low_vol}
- Based on: linear regression slope, Hurst exponent estimate, realized vol percentile
- Koopman matcher can optionally filter by regime (soft constraint, not hard)
- Phase 3+: replace with HMM or regime-switching model

---

## Phase 2 — Core Differentiators

### 2a. ~~MethodResult refactor~~ → DONE (via CandidateWindow)
- [x] `CandidateWindow` dataclass carries intermediate state through the pipeline
- [x] DTW and Bempedelis populate `ScoreBreakdown` fields directly
- [x] `MatchResult` stores transform_alpha, transform_beta, transform_r2 from Bempedelis
- [x] Matcher collects per-method scores and computes composite confidence

### 2b. ~~Bempedelis integration~~ → DONE
- [x] `bempedelis_match()` wired into `matcher.py` via `_enrich_with_bempedelis()`
- [x] Runs only on top `tier2_candidates` (expensive method, Tier 2 only)
- [x] Uses `METHOD_NORM_DEFAULTS["bempedelis"]` (logreturn) for Bempedelis normalization
- [x] Populates `score_breakdown.bempedelis_r2` and `bempedelis_smoothness`
- [x] Populates `MatchResult.transform_alpha`, `transform_beta`, `transform_r2`
- [x] Test: `test_bempedelis_reranking_populates_transform_details` passing

### 2c. ~~SAX pre-filter~~ → DONE
**Goal**: Replace the `_score_prefilter()` placeholder with SAX MINDIST — a distance that lower-bounds Euclidean, guaranteeing no false dismissals while eliminating ~80% of candidates.

**File**: `the_similarity/methods/sax_filter.py`

**Implementation**:
- [x] `sax_transform(series, n_segments, alphabet_size) -> NDArray[int8]`
  - Z-normalize input (already logreturn_zscore from pipeline)
  - PAA: divide into `n_segments` equal segments, replace each with its mean
  - Map each PAA value to an integer using breakpoints from `scipy.stats.norm.ppf`
  - Default: `n_segments=16`, `alphabet_size=8`
- [x] `sax_mindist(sax_a, sax_b, original_length, alphabet_size) -> float`
  - Build breakpoint lookup table for `dist(a, b)` between symbols (cached)
  - `MINDIST = sqrt(n/w) * sqrt(sum(dist(a_i, b_i)^2))`
  - This is a lower bound on Euclidean distance — no false dismissals
- [x] `sax_score(mindist, window_size) -> float`
  - Convert MINDIST to [0, 1] similarity: `exp(-mindist / window_size)`
- [x] Config additions to `Config`:
  - `sax_n_segments: int = 16`
  - `sax_alphabet_size: int = 8`
- [x] Wire into `_collect_candidates()` in matcher.py:
  - Compute SAX for query once
  - Compute SAX for each candidate window
  - `_score_prefilter` now uses 0.6 * sax_score + 0.4 * pearson (replacing Euclidean+Pearson)
- [x] `"sax"` in `METHOD_NORM_DEFAULTS` (already existed: `logreturn_zscore`)
- [x] **No pyts dependency** — implemented from scratch (~120 lines)

**Tests** (`test_sax.py`): 5 tests passing
- [x] `test_sax_identical_series` — same input → SAX distance 0
- [x] `test_sax_mindist_lower_bounds_euclidean` — for random pairs, MINDIST ≤ Euclidean distance
- [x] `test_sax_embedded_pattern_survives_filter` — embed pattern in noise, SAX prefilter retains it
- [x] `test_sax_transform_output_shape` — correct shape and value range
- [x] `test_sax_score_range` — output always in [0, 1]

### 2d. ~~Matrix Profile pre-filter~~ → DONE
**Goal**: Add MASS-based motif ranking as a second Tier 1 signal. MASS computes z-normalized Euclidean distance profile in O(n log n) via FFT.

**File**: `the_similarity/methods/matrix_profile_filter.py`

**Implementation**:
- [x] `query_profile(history, query) -> distances`
  - Pure-numpy MASS implementation (FFT-based sliding dot product)
  - No stumpy dependency — avoids numba JIT segfault issues
  - O(n log n) via FFT — computes all distances in one call
- [x] `mp_score(distance, window_size) -> float`
  - Convert to [0, 1]: `exp(-distance / sqrt(window_size))`
- [x] `mp_score_profile(distances, window_size) -> NDArray`
  - Vectorized score conversion for full distance profile
- [x] Wired into `_collect_candidates()` in matcher.py:
  - MASS computed once on normalized history (O(n log n))
  - Scores looked up by position for each candidate
  - Three-signal prefilter: `0.4 * sax + 0.4 * mp + 0.2 * pearson`
  - Graceful fallback to SAX + Pearson when MP unavailable

**Tests** (`test_matrix_profile.py`): 5 tests passing
- [x] `test_embedded_pattern_top_ranked` — embed pattern, MP ranks it #1
- [x] `test_mp_score_identical` — identical subsequence → distance ≈ 0, score ≈ 1
- [x] `test_mass_returns_correct_length` — output length = len(history) - len(query) + 1
- [x] `test_mp_score_profile_range` — all scores in [0, 1]
- [x] `test_mp_score_decreases_with_distance` — monotonic relationship

### 2e. Wavelet Leaders multifractal spectrum
**Goal**: Compute the f(α) singularity spectrum for each window and use spectrum distance as both a Tier 1 fast signal and a Tier 2 `wavelet_spectrum` score.

**File**: `the_similarity/methods/wavelet_leaders.py`

**Implementation**:
- [ ] `compute_wavelet_leaders(series, wavelet, max_level) -> leaders`
  - Use `pywt.wavedec(series, wavelet, level=max_level)` for DWT
  - Compute wavelet leaders: supremum of |coefficients| in local neighborhood at each scale
  - `wavelet='db4'`, `max_level=None` (auto from series length)
- [ ] `multifractal_spectrum(leaders, q_range) -> (alpha, f_alpha)`
  - Moment orders: `q = np.arange(-5, 5.5, 0.5)` (21 values)
  - Structure function: `S(q, j) = mean(|leaders_j|^q)` at each scale j
  - Generalized Hurst: `h(q)` from log-log regression of S(q, j) vs scale
  - Renyi exponent: `tau(q) = q * h(q) - 1`
  - Legendre transform: `alpha = d(tau)/dq`, `f(alpha) = q * alpha - tau(q)`
  - Return (alpha, f_alpha) arrays
- [ ] `spectrum_distance(spec_a, spec_b) -> float`
  - Interpolate both spectra onto common alpha grid
  - L2 distance: `sqrt(mean((f_a - f_b)^2))`
  - Alternative: `scipy.stats.wasserstein_distance(alpha_a, f_a, alpha_b, f_b)` if shapes differ significantly
- [ ] `wavelet_score(distance) -> float`
  - Map to [0, 1]: `exp(-distance * 5)` (tunable scaling factor)
- [ ] Config:
  - `wavelet_name: str = "db4"`
  - `wavelet_q_range: tuple[float, float, float] = (-5, 5.5, 0.5)`
- [ ] Wire into matcher.py:
  - **Tier 1**: Coarse spectrum distance (fewer q values, e.g., q = [-2, 0, 2]) as prefilter component
  - **Tier 2**: Full spectrum comparison → `score_breakdown.wavelet_spectrum`
  - Add to `_enrich_with_bempedelis` pattern (rename to `_enrich_tier2` and add wavelet)
- [ ] Minimum window size: ~64 bars for reliable spectrum (fewer scales at shorter windows)
- [ ] Add `pywavelets` to dependencies (already listed in pyproject.toml as `PyWavelets`)

**Tests** (`test_wavelet_leaders.py`):
- [ ] `test_spectrum_self_distance_zero` — same series → distance ≈ 0
- [ ] `test_known_hurst` — fBm with H=0.7 → h(2) ≈ 0.7
- [ ] `test_white_noise_vs_trending` — different spectra → large distance
- [ ] `test_short_series_graceful` — series < 16 bars → returns fallback score (0.5)

### 2f. Tier 1 merger
**Goal**: Replace single prefilter with multi-method nomination scoring. SAX runs on all candidates → survivors → Matrix Profile + Wavelet Leaders on survivors → ranked union → Tier 2.

**File**: Changes in `the_similarity/core/matcher.py`

**Implementation**:
- [ ] Refactor `_collect_candidates()`:
  - Phase 1: Generate all raw windows (no scoring yet)
  - Phase 2: SAX prefilter on all windows → keep top `tier1_candidates * 2` (generous cut)
  - Phase 3: Matrix Profile ranking on SAX survivors
  - Phase 4: Coarse wavelet spectrum distance on SAX survivors
  - Phase 5: Nomination scoring to produce final Tier 1 pool
- [ ] `_compute_nomination_score(sax_rank, mp_rank, wavelet_rank) -> float`
  - `nomination_count` = number of methods that ranked this candidate in their top N
  - `rank_credit` = Σ(1 / rank_in_method) for each method that nominated
  - `score = nomination_count + rank_credit`
  - Candidates nominated by all 3 methods rank highest
- [ ] Top `tier1_candidates` by nomination score → proceed to Tier 2 (DTW, Pearson, Bempedelis, Wavelet full)
- [ ] Config:
  - `sax_prefilter_keep_ratio: float = 0.3` — fraction of candidates SAX keeps for MP/Wavelet
- [ ] Graceful degradation: if a Tier 1 method is not available (missing dependency), skip it — the merger still works with 1 or 2 methods

**Tests**:
- [ ] `test_multi_nominated_ranks_higher` — candidate in all 3 methods' top-N beats single-method nominee
- [ ] `test_graceful_without_stumpy` — if stumpy not installed, merger uses SAX + Wavelet only
- [ ] `test_tier1_preserves_obvious_match` — embedded pattern survives merger

### 2g. Full confidence score (Phase 2 methods)
**Goal**: With SAX, Matrix Profile, and Wavelet Leaders implemented, the system should produce meaningful composite scores from 4+ active methods.

- [ ] Default `active_methods` expanded to: `["dtw", "pearson_warped", "bempedelis_r2", "bempedelis_smoothness", "wavelet_spectrum"]`
- [ ] Integration test: synthetic self-similar match scores > 60, noise match scores < 30
- [ ] Integration test: adding `wavelet_spectrum` to active_methods changes ranking (not just score magnitude)
- [ ] Playground validation: `run_local_search()` on BTC daily with all Phase 2 methods → inspect `top_matches_frame()` output

---

## Phase 3 — Research Grade

### 3a. Takens delay embedding (shared utility)
**Goal**: Both Koopman and TDA need delay embedding. Build once, share.

**File**: `the_similarity/core/embedding.py`

**Implementation**:
- [ ] `delay_embed(series, dim, lag) -> NDArray` (shape: (n - (dim-1)*lag, dim))
  - Construct Hankel-like matrix from scalar time series
  - Each row is `[x(t), x(t-lag), x(t-2*lag), ..., x(t-(dim-1)*lag)]`
- [ ] `auto_lag(series) -> int`
  - First minimum of time-delayed mutual information
  - Use histogram-based MI estimation (fast, ~20 lines)
  - Fallback: first zero-crossing of autocorrelation
- [ ] `auto_dim(series, lag, max_dim=15) -> int`
  - False Nearest Neighbors (FNN) method
  - Increase dim until FNN fraction < 2%
  - Cao's method as alternative (avoids threshold)
  - Fallback: `min(10, len(series) // (3 * lag))`
- [ ] For typical financial daily data: expect lag ≈ 3-7, dim ≈ 4-8

**Tests** (`test_embedding.py`):
- [ ] `test_delay_embed_shape` — output shape matches (n - (d-1)*tau, d)
- [ ] `test_auto_lag_sine` — sine wave → lag ≈ period/4
- [ ] `test_auto_dim_lorenz` — Lorenz attractor → dim ≈ 3

### 3b. Koopman EDMD + eigenvalue matching
**Goal**: Fit Koopman operator via EDMD on delay-embedded windows, extract eigenvalue spectra, match via Hungarian algorithm. Weight: 0.20 (highest single method).

**File**: `the_similarity/methods/koopman.py`

**Implementation**:
- [ ] `fit_koopman(series, dim, lag, n_modes) -> KoopmanResult`
  - Delay-embed using `embedding.delay_embed()`
  - Build snapshot pairs: X = embedded[:-1], Y = embedded[1:]
  - SVD: `U, S, Vt = np.linalg.svd(X, full_matrices=False)`
  - Truncate to `n_modes` (default: `min(10, dim)`)
  - Project: `A_tilde = U[:, :r].T @ Y @ Vt[:r].T @ np.diag(1/S[:r])`
  - Eigendecompose: `eigenvalues, eigenvectors = np.linalg.eig(A_tilde)`
  - Return `KoopmanResult(eigenvalues, eigenvectors, A_tilde)`
  - **No external dependency** — pure numpy DMD. PyKoopman/PyDMD are for validation, not runtime.
- [ ] `koopman_eigenvalue_distance(eigs_a, eigs_b, top_k=8) -> float`
  - Sort both by `|λ|` descending
  - Truncate to top-k with `|λ| > 0.05`
  - Pad smaller set with zeros
  - Cost matrix: `C[i,j] = |λ_i - μ_j|` in complex plane
  - `scipy.optimize.linear_sum_assignment(C)` → optimal matching
  - Total cost = sum of matched distances
  - Return total_cost
- [ ] `koopman_score(distance, n_modes) -> float`
  - Map to [0, 1]: `exp(-distance / n_modes)`
- [ ] Config:
  - `koopman_n_modes: int = 8`
  - `koopman_min_window: int = 50` (need enough data for reliable embedding)
- [ ] Wire into matcher.py `_enrich_tier2()`:
  - Normalize with `METHOD_NORM_DEFAULTS["koopman"]` (logreturn)
  - Fit Koopman on query (once) and each Tier 2 candidate
  - Compute eigenvalue distance → `score_breakdown.koopman`
  - Store eigenvalues in `MatchResult.koopman_eigenvalues`
- [ ] Add `"koopman"` to `Config.active_methods` default list

**Tests** (`test_koopman.py`):
- [ ] `test_same_system_low_distance` — two windows from `sin(t) + 0.5*sin(2t)` → distance < 0.5
- [ ] `test_different_systems_high_distance` — sine vs random walk → distance > 2.0
- [ ] `test_eigenvalue_count` — n_modes eigenvalues returned
- [ ] `test_hungarian_matching_symmetric` — distance(A, B) == distance(B, A)
- [ ] `test_short_window_graceful` — window < koopman_min_window → score = 0.0

### 3c. EMD multi-scale matching
**Goal**: Decompose both windows into IMFs, match corresponding IMF pairs via DTW, weighted by IMF energy. Weight: 0.10.

**File**: `the_similarity/methods/emd_matcher.py`

**Implementation**:
- [ ] `decompose_emd(series, max_imfs=6) -> list[NDArray]`
  - `from PyEMD import EMD; emd = EMD(); IMFs = emd(series)`
  - Truncate to `max_imfs` (discard residual if more)
  - Returns list of IMF arrays
- [ ] `imf_energy(imf) -> float`
  - `np.sum(imf ** 2)`
- [ ] `emd_match(query, candidate, max_imfs=6) -> (float, float)`
  - Decompose both into IMFs
  - Align IMF count: pad shorter list with zeros
  - For each corresponding pair: `dtw_distance(imf_q, imf_c)` → normalized by IMF length
  - Weight each pair by energy: `w_i = energy_i / total_energy`
  - Weighted sum of per-IMF distances → total distance
  - Score = `exp(-total_distance)` → [0, 1]
  - Returns (score, distance)
- [ ] Config:
  - `emd_max_imfs: int = 6`
- [ ] Wire into `_enrich_tier2()`:
  - Normalize with `METHOD_NORM_DEFAULTS["emd"]` (raw)
  - `score_breakdown.emd = emd_score`
- [ ] Add `EMD-signal` to dependencies

**Tests** (`test_emd.py`):
- [ ] `test_emd_identical` — same signal → score ≈ 1.0
- [ ] `test_emd_different_frequency` — 5Hz vs 20Hz → score < 0.5
- [ ] `test_imf_count` — series decomposes into 2-6 IMFs
- [ ] `test_emd_short_series` — series < 20 bars → graceful fallback

### 3d. TDA persistence diagrams
**Goal**: Delay-embed, compute persistent homology, compare via Wasserstein distance. Weight: 0.08.

**File**: `the_similarity/methods/tda_matcher.py`

**Implementation**:
- [ ] `compute_persistence(series, dim, lag) -> dict`
  - Delay-embed using shared `embedding.delay_embed()`
  - `from ripser import ripser; result = ripser(embedded, maxdim=1)`
  - Extract H0 and H1 diagrams
  - Return `{"H0": diagram_0, "H1": diagram_1}`
- [ ] `persistence_distance(diag_a, diag_b) -> float`
  - `from persim import wasserstein; d = wasserstein(diag_a, diag_b)`
  - Combine H0 and H1: `total = 0.4 * d_H0 + 0.6 * d_H1`
  - H1 weighted higher — loops/cycles carry more structural information than components
- [ ] `tda_score(distance) -> float`
  - Map to [0, 1]: `exp(-distance * 2)`
- [ ] Config:
  - `tda_max_homology_dim: int = 1` (H0 + H1)
  - `tda_min_window: int = 40` (need enough points for meaningful topology)
- [ ] Wire into `_enrich_tier2()`:
  - Normalize with `METHOD_NORM_DEFAULTS["tda"]` (logreturn_zscore)
  - `score_breakdown.tda = tda_score`
  - Store diagram in `MatchResult.persistence_diagram`
- [ ] Add `ripser`, `persim` to dependencies

**Tests** (`test_tda.py`):
- [ ] `test_tda_identical` — same series → distance ≈ 0
- [ ] `test_tda_circle_vs_line` — circular trajectory vs line → large H1 difference
- [ ] `test_tda_short_window` — window < tda_min_window → score = 0.0

### 3e. Transfer entropy
**Goal**: Measure information transfer from a match window to its forward window. High TE = the match is genuinely predictive, not just similar. Weight: 0.05.

**File**: `the_similarity/methods/transfer_entropy.py`

**Implementation**:
- [ ] `compute_transfer_entropy(source, target, lag=1, bins=8) -> float`
  - Discretize via histogram binning (fast, no external dependency)
  - Compute joint and conditional entropies using bin counts
  - `TE = H(target_future | target_past) - H(target_future | target_past, source_past)`
  - Normalize: `TE_normalized = TE / H(target_future)` → [0, 1]
- [ ] `te_score(match_window, forward_window) -> float`
  - `source = match_window`, `target = forward_window`
  - Returns normalized TE in [0, 1]
  - High score = match period contains information that predicts the forward window
- [ ] Config:
  - `te_lag: int = 1`
  - `te_bins: int = 8`
- [ ] Wire into `_enrich_tier2()`:
  - Requires forward window data (available in `MatchResult.forward_window`)
  - Run TE after forward window extraction in projector
  - Actually: compute TE in `find_matches()` by extracting forward window from history
  - `score_breakdown.transfer_entropy = te_score`
- [ ] **No external dependency** — histogram-based TE is ~30 lines

**Tests** (`test_transfer_entropy.py`):
- [ ] `test_te_deterministic` — `target = source[1:]` (shifted copy) → TE > 0.5
- [ ] `test_te_independent` — two independent random series → TE ≈ 0
- [ ] `test_te_normalized_range` — output always in [0, 1]

### 3f. Regime tagger
**Goal**: Label each window with a regime tag for filtering and display.

**File**: `the_similarity/core/regime.py`

**Implementation**:
- [ ] `tag_regime(series) -> str`
  - Returns one of: `"trending_up"`, `"trending_down"`, `"mean_reverting"`, `"high_vol"`, `"low_vol"`
  - **Slope**: OLS linear regression slope on normalized series
    - slope > +threshold → trending_up candidate
    - slope < -threshold → trending_down candidate
  - **Hurst**: DFA estimate on log-returns
    - H > 0.6 → confirms trending (use slope direction)
    - H < 0.4 → mean_reverting (overrides slope)
  - **Volatility**: realized vol = std(log-returns) × sqrt(252)
    - Compare to historical percentile (pass as parameter or use fixed thresholds)
    - Top 25% → high_vol, bottom 25% → low_vol (overrides trend label)
  - Priority: vol override > Hurst override > slope direction
- [ ] `hurst_dfa(series, min_box=4, max_box=None) -> float`
  - Detrended Fluctuation Analysis (~30 lines)
  - Integrate series → segment into boxes → detrend each → compute F(n) → log-log slope
- [ ] Attach regime label to `MatchResult` (new field: `regime: str | None = None`)
- [ ] Attach to `CandidateWindow` during `_collect_candidates()`
- [ ] Optional: Koopman matcher can filter by regime (soft — penalize mismatch, don't exclude)

**Tests** (`test_regime.py`):
- [ ] `test_trending_up` — monotonically increasing series → "trending_up"
- [ ] `test_mean_reverting` — sine wave → "mean_reverting"
- [ ] `test_high_vol` — series with large std → "high_vol"
- [ ] `test_hurst_random_walk` — random walk → H ≈ 0.5

### 3g. Phase 3 integration
**Goal**: All 9 methods active and producing real scores.

- [ ] Default `active_methods` = all 9 fields
- [ ] `_enrich_tier2()` runs: Bempedelis, Wavelet (full), Koopman, EMD, TDA, Transfer Entropy
- [ ] Ordering within Tier 2: cheapest first (Wavelet, TE, EMD, TDA, Koopman, Bempedelis)
- [ ] Integration test: `run_local_search()` on BTC 1d with all methods → all 9 breakdown fields > 0
- [ ] Integration test: confidence scores distribute meaningfully (not all clustered near 50)
- [ ] Playground: compare rankings with all methods vs DTW-only — do structural methods change the top-5?
- [ ] Update API contracts: `SearchRequest.active_methods` default matches new config

---

## Phase 4 — Prediction Engine

### 4a. Koopman forward evolution
- [ ] Use matched Koopman operator K to evolve query forward: x(t+dt) = K·x(t)
- [ ] Uncertainty from eigenvalue matching residuals
- [ ] Return as separate forecast alongside weighted projection
- [ ] `forecast.koopman_forecast` field

### 4b. Enhanced forecast cone
- [x] Percentile bands: 10th, 25th, 50th, 75th, 90th (DONE)
- [ ] Confidence decay: confidence_score × decay_factor(forward_bars)
- [ ] Per-match trajectory overlay in visualization
- [ ] Combine Koopman forecast + weighted historical projection

### 4c. Backtester / validation framework
- [ ] Implement `the_similarity.backtest(history, window_size, forward_bars, n_trials)`
- [ ] For each trial:
  - Pick random query window
  - Run search() on everything *before* the query
  - Get top-k matches and forward windows
  - Compute forecast cone
  - Compare to actual outcome
- [ ] Output: hit_rate, mean_error, calibration_curve, CRPS
- [ ] Calibration = P90 band contains actual 90% of the time (if not, overconfident)
- [ ] This is the ground truth for tuning weights and validating the system

---

## Phase 5 — Production Ready

### 5a. FeatureStore caching
- [ ] Implement `FeatureStore` class
- [ ] Key: (dataset_hash, window_start, window_length, method, params_hash)
- [ ] Backend: shelve for local, interface ready for Redis/SQLite swap
- [ ] Precompute Tier 1 features on dataset load
- [ ] search() becomes O(N×lookup + K×compute)

### 5b. Performance
- [ ] Profile bottlenecks (DTW loop, Bempedelis optimization)
- [ ] Parallelize Tier 2 methods across candidates (multiprocessing or joblib)
- [ ] Vectorize where possible (batch DTW via dtaidistance)
- [ ] Consider numba for inner loops if needed

### 5c. Cross-timeframe search
- [ ] Implement `cross_timeframes` parameter in search()
- [ ] Resample history to each target timeframe
- [ ] Search each independently, merge results
- [ ] Deduplicate overlapping matches across timeframes

### 5d. Documentation & release
- [ ] Full API reference
- [ ] Theory document with paper references
- [ ] Tutorial notebooks
- [ ] PyPI package
