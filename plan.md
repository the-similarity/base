# The Similarity Implementation Plan

## Current State

Phase 1 complete + Phases 2a–2e done + Phase 3 done. Working tiered pipeline with 115 tests passing (all 9 methods active):
- Loader (CSV, parquet, DataFrame, dict, numpy)
- Normalizer (zscore, minmax, logreturn, logreturn_zscore, raw) with per-method defaults
- Windower (sliding windows, multi-scale indices)
- DTW matcher with Sakoe-Chiba band
- Bempedelis self-similarity transform (multi-start L-BFGS-B) — **integrated into pipeline**
- Scorer with `active_methods` + dynamic weight renormalization (0-100 scale)
- Projector with interpolated weighted quantiles and 5-band forecast cone (p10/25/50/75/90)
- Tiered matcher: SAX+MASS+Pearson prefilter → DTW+Pearson cheap scoring → Tier 2 enrichment (7 methods) on top-N → final rank
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
- `Config.active_methods` controls which methods run (default: all 9 methods)
- `compute_confidence()` renormalizes weights across only active methods
- Adding a method to `active_methods` immediately gives it proper weight
- All 9 weight slots defined upfront; inactive methods don't drag score to zero

### Tier Architecture (Live)
- **Tier 1 prefilter**: `_score_prefilter()` — SAX MINDIST + MASS + Pearson blend (0.4/0.4/0.2)
- **Tier 1 cap**: `config.tier1_candidates` (default 1000) — top candidates by prefilter score
- **Cheap scoring**: DTW + Pearson on all Tier 1 survivors
- **Tier 2 enrichment**: 7 methods (Bempedelis, Koopman, Wavelet, EMD, TDA, TE, Regime) on top `config.tier2_candidates` (default 20)
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
- Phase 5: SQLite with params_hash in key (no explicit invalidation needed). Same interface.
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

### 2e. ~~Wavelet Leaders multifractal spectrum~~ → DONE
**File**: `the_similarity/methods/wavelet_leaders.py` (190 lines)
- [x] Fractal spectrum analysis via wavelet modulus maxima
- [x] Multi-scale Hurst exponent estimation
- [x] Wired into `_enrich_tier2()` → `score_breakdown.wavelet_spectrum`
- [x] Tests in `test_wavelet_leaders.py` (5 tests passing)

### 2f. Tier 1 merger → DEFERRED
**Status**: Current 3-signal blend (0.4×SAX + 0.4×MP + 0.2×Pearson) works well. SAX provides no-false-dismissal guarantees. Nomination scoring deferred until backtester (4c) proves Tier 1 quality is the bottleneck. See TODOS.md.

### 2g. ~~Full confidence score~~ → DONE
- [x] Default `active_methods` = all 9 methods (bempedelis_r2, bempedelis_smoothness, koopman, wavelet_spectrum, emd, tda, dtw, pearson_warped, transfer_entropy)
- [x] Weights sum to 1.0 with dynamic renormalization across active methods
- [x] `compute_confidence()` produces 0-100 composite scores

---

## Phase 3 — Research Grade → DONE

All 9 methods implemented, wired into `_enrich_tier2()`, and tested (115 tests passing).

### 3a. ~~Takens delay embedding~~ → DONE
- [x] `core/embedding.py` — `delay_embed()`, `auto_lag()`, `auto_dim()`
- [x] Shared by Koopman and TDA
- [x] Tests in `test_embedding.py` (5 tests)

### 3b. ~~Koopman EDMD~~ → DONE
- [x] `methods/koopman.py` (208 lines) — pure numpy DMD, Hungarian eigenvalue matching
- [x] Wired into `_enrich_tier2()` → `score_breakdown.koopman`
- [x] Tests in `test_koopman.py` (10 tests)

### 3c. ~~EMD multi-scale~~ → DONE
- [x] `methods/emd_matcher.py` (98 lines) — IMF decomposition + energy-weighted DTW
- [x] Wired into `_enrich_tier2()` → `score_breakdown.emd`
- [x] Tests in `test_emd.py` (5 tests)

### 3d. ~~TDA persistence~~ → DONE
- [x] `methods/tda_matcher.py` (137 lines) — Rips persistence diagrams
- [x] Wired into `_enrich_tier2()` → `score_breakdown.tda`
- [x] Tests in `test_tda.py` (5 tests)

### 3e. ~~Transfer entropy~~ → DONE
- [x] `methods/transfer_entropy.py` (164 lines) — histogram-based TE, no external deps
- [x] Wired into `_enrich_tier2()` → `score_breakdown.transfer_entropy`
- [x] Tests in `test_transfer_entropy.py` (5 tests)

### 3f. ~~Regime tagger~~ → DONE
- [x] `core/regime.py` — `tag_regime()` with slope/Hurst/vol logic
- [x] Wired into `_enrich_tier2()` → `candidate.regime`
- [x] Tests in `test_regime.py` (5 tests)

### 3g. ~~Phase 3 integration~~ → DONE
- [x] All 9 methods active by default
- [x] `_enrich_tier2()` runs all 7 Tier 2 methods
- [x] Weights sum to 1.0 with dynamic renormalization

---

## Phase 4 — Prediction Engine

### 4a. ~~Koopman forward evolution~~ → DONE
- [x] `koopman_evolve()` in `methods/koopman.py` — fits Koopman operator, evolves query forward
- [x] `clamp_eigenvalues()` — projects eigenvalues to unit disk, preserves phase
- [x] Uncertainty from reconstruction residuals (σ × √t)
- [x] Returns `KoopmanForecast` with trajectory + uncertainty
- [x] `Forecast.koopman_forecast` field populated in `api.py:project()`

### 4b. ~~Enhanced forecast cone~~ → DONE
- [x] Percentile bands: 10th, 25th, 50th, 75th, 90th
- [x] Confidence decay: `Config.confidence_decay_rate` scales cone width over forward bars (default 0.0 = no decay)
- [x] Combine Koopman forecast + weighted historical projection: `Config.koopman_blend_weight` blends Koopman trajectory into P50 (default 0.0 = historical only)
- [ ] Per-match trajectory overlay in visualization (frontend concern)

### 4c. ~~Backtester / validation framework~~ → DONE
- [x] `the_similarity.backtest(history, window_size, forward_bars, n_trials)`
- [x] Data leakage guard: `history[:query_start]` enforced
- [x] Parallel trials: `ProcessPoolExecutor` with `n_workers` param, fallback to sequential
- [x] Walk-forward trials with random query positions, min lookback = 3×window_size
- [x] Output: `BacktestReport` with hit_rate, mean_error, calibration, CRPS
- [x] Deterministic tests with synthetic data + integration tests
- [x] `TrialResult` per trial with skip handling and error reporting
- [x] 26 tests (23 unit + 3 slow integration)

---

## Phase 5 — Production Ready

### 5a. ~~FeatureStore caching~~ → DONE
- [x] `FeatureStore` class in `core/feature_store.py` — SQLite WAL-mode backend
- [x] Key: `(dataset_hash, window_start, window_length, method, params_hash)`
- [x] `dataset_hash()` — sparse O(n/100) SHA-256 hash
- [x] `params_hash()` — method+config parameter hashing
- [x] Wired into `_enrich_tier2()` for 5 cached methods: Bempedelis, Koopman, Wavelet, EMD, TDA
- [x] Opt-in via `search(feature_store=store)` and `backtest(feature_store=store)`
- [x] Graceful degradation: corrupt DB warns and falls through to compute
- [x] 14 tests (13 unit + 1 integration)

### 5b. ~~Performance~~ → DONE
- [x] Batch DTW via `dtaidistance.distance_matrix_fast` with `block` parameter — eliminates per-candidate Python loop in Tier 1
- [x] ThreadPoolExecutor for Tier 2 enrichment — parallel candidate processing (numpy/scipy release GIL)
- [x] Regression tests verifying batch == sequential to 1e-10
- [x] Benchmark: DTW+Pearson 0.32s, all 9 methods 1.03s (2000-bar history, stride=3)

### 5c. ~~Cross-timeframe search~~ → DONE
- [x] `cross_timeframe_search()` in `api.py` — standalone function searching across multiple timeframes
- [x] `_resample_timeseries()` — resamples TimeSeries to coarser frequencies via pandas `.resample().last()`
- [x] Query window scaled proportionally (linear interpolation in [0,1] space)
- [x] `_deduplicate_matches()` — temporal overlap detection with configurable threshold, keeps highest-scoring
- [x] `MatchResult.source_timeframe` field tracks origin timeframe per match
- [x] `min_window` guard skips timeframes where scaled query < 10 bars
- [x] 10 tests (unit + slow integration) in `test_cross_timeframe.py`

### 5d. ~~Documentation & release~~ → DONE
- [x] Full API reference — `docs/API_REFERENCE.md` (all functions, params, examples, data classes)
- [x] Theory document with paper references — `docs/THEORY.md` (9 methods, scoring, forecasting, backtesting, 16 references)
- [x] Tutorial notebooks — `docs/tutorials/` (01_quickstart, 02_configuration, 03_backtesting)
- [x] PyPI package — `pyproject.toml` with classifiers, keywords, extras, test exclusion, MIT LICENSE

---

## Phase 6 — Live Product

### 6a. ~~Real-time streaming pipeline~~ → DONE
- [x] `ProgressEvent` + `ProgressCallback` in core matcher — events at prefilter, tier1, tier2, done stages
- [x] `progress_fn` parameter wired through `search()` API (backward compatible)
- [x] `/ws/search` WebSocket endpoint — streams progress + results in real time via thread pool
- [x] `/ws/watch` WebSocket endpoint — candle watcher with threshold alerts, configurable recheck interval
- [x] Protocol: init → candle stream → automatic re-scan → alert when confidence > threshold
- [x] Query updates, forced rescans, and ack messages supported
- [x] 8 tests for progress callback infrastructure (188 total tests passing)
- [ ] Incremental SAX+MASS update (optimization — full recompute works, incremental deferred)
- [ ] Backpressure handling for multiple concurrent subscriptions

### 6b. Alert system
- [ ] User-defined watchlists: "notify me when a pattern similar to X appears on Y"
- [ ] Confidence threshold triggers (e.g., fire when composite > 80)
- [ ] Notification channels: webhook, email, push
- [ ] Alert persistence + deduplication (don't fire same pattern repeatedly)
- [ ] Depends on: 6a (streaming pipeline)

### 6c. Auth & multi-tenancy
- [ ] JWT authentication with refresh tokens
- [ ] User accounts in Postgres (watchlists, saved searches, alert configs)
- [ ] API key management for programmatic access
- [ ] Rate limiting per tier (free/pro/enterprise)
- [ ] FeatureStore isolation per user for custom datasets

### 6d. Hosted data pipeline
- [ ] Ingestion service pulling from market data providers (Polygon, Tiingo, Binance)
- [ ] Normalize to parquet schema, append-only updates on schedule
- [ ] Asset coverage target: 500+ assets × 5 timeframes × 10yr history
- [ ] Data catalog API: available assets, date ranges, freshness metadata
- [ ] Replace in-repo parquet files with cloud storage (S3/GCS)

---

## Phase 7 — Intelligence Layer

### 7a. Strategy builder
- [ ] Rule engine: chain pattern match + forecast cone into entry/exit signals
- [ ] Expose backtester as strategy validation: user-defined rules → walk-forward metrics
- [ ] Strategy templates (momentum, mean-reversion, breakout) as starting points
- [ ] No-code strategy editor in frontend

### 7b. Ensemble forecasting
- [ ] Monte Carlo simulation from match distribution
- [ ] Regime-conditional projections (trending vs. mean-reverting matches weighted differently)
- [ ] Conformal prediction intervals for calibrated coverage guarantees
- [ ] Forecast combination: Koopman + historical quantiles + Monte Carlo → blended cone

### 7c. Portfolio-level analysis
- [ ] Cross-asset pattern correlation: "last time BTC looked like this, what did ETH do?"
- [ ] Portfolio regime detection: which assets are in similar regimes right now?
- [ ] Divergence scanner: find assets whose patterns are decoupling from historical correlations
- [ ] Leverage existing transfer entropy for cross-asset information flow

### 7d. Explainability layer
- [ ] Natural language match explanations: which methods drove the score, why this match matters
- [ ] Per-method contribution breakdown in human-readable form
- [ ] Historical context: what happened after previous occurrences of this pattern
- [ ] Confidence calibration commentary: "this confidence level has been accurate X% of the time"

---

## Phase 8 — Platform

### 8a. API-as-a-service
- [ ] Tiered pricing: free (limited searches, delayed data), pro (real-time, alerts, full methods), enterprise (dedicated compute, SLA)
- [ ] Usage metering and billing integration
- [ ] Developer portal with API docs, SDKs (Python, JS), and playground
- [ ] Compute isolation for enterprise tenants

### 8b. Custom datasets
- [ ] User-uploaded time series (CSV, API push)
- [ ] Domain-agnostic: IoT sensors, medical, climate, web traffic — not just financial
- [ ] Private dataset storage with access controls
- [ ] Auto-detection of appropriate normalization and method weights per domain

### 8c. Method marketplace
- [ ] Public method interface specification for community contributions
- [ ] Plugin registry: researchers submit new Tier 2 scoring methods
- [ ] Review + benchmarking pipeline: new methods tested against backtester before approval
- [ ] Revenue share for method contributors

### 8d. Embeddable widget
- [ ] `<script>` tag drops pattern search + forecast chart into any website
- [ ] Configurable: asset selector, timeframe picker, chart theme
- [ ] Partnership integrations with charting platforms (TradingView, etc.)
- [ ] White-label option for enterprise
