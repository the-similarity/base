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

### 6a. Real-time streaming pipeline
- [ ] WebSocket feed ingesting candles from exchanges/brokers (Binance, Polygon, etc.)
- [ ] Incremental SAX+MASS update as new bars arrive (avoid full recomputation)
- [ ] Streaming search: re-score top candidates on each new bar, emit events on confidence change
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

### 7a. ~~Strategy builder~~ → DONE
- [x] `Signal` / `SignalType` / `Rule` / `Strategy` dataclasses for composable trading rules
- [x] `evaluate_strategy()` — filters matches by confidence, evaluates rules in priority order
- [x] `validate_strategy_backtest()` — walk-forward strategy validation with win_rate, avg_return, Sharpe
- [x] 3 built-in templates: `momentum_strategy()`, `mean_reversion_strategy()`, `breakout_strategy()`
- [x] Stop-loss at P10/P90, take-profit at P75/P25 from forecast cone
- [x] 11 tests across 3 classes (signal generation, evaluation, backtest)
- [ ] No-code strategy editor in frontend (deferred to frontend phase)

### 7b. ~~Ensemble forecasting~~ → DONE
- [x] `monte_carlo_forecast()` — samples from match distribution with confidence-weighted path selection + volatility-scaled noise
- [x] `regime_conditional_forecast()` — detects query regime via DFA/slope/vol, soft-weights incompatible matches (configurable 0-1)
- [x] `conformal_prediction_intervals()` — split conformal prediction with finite-sample coverage guarantee, per-bar adaptive scaling
- [x] `ensemble_forecast()` — blends historical + Monte Carlo + regime-conditional with configurable weights, applies conformal intervals
- [x] Public API: `ensemble_project()` in `api.py`, exported from `__init__.py`
- [x] `EnsembleForecast` dataclass with component results (MonteCarloResult, RegimeConditionalResult, ConformalResult)
- [x] 30 tests across 4 test classes (Monte Carlo, Regime, Conformal, Ensemble) — all passing

### 7c. ~~Portfolio-level analysis~~ → DONE
- [x] `cross_asset_scan()` — "last time BTC looked like this, what did ETH do?" with correlation + TE + optimal lag
- [x] `portfolio_regime_scan()` — detect regimes across all assets (Hurst, vol, slope)
- [x] `divergence_scanner()` — find decorrelating/recorrelating asset pairs
- [x] `information_flow_network()` — pairwise transfer entropy with net flow direction
- [x] 15 tests across 4 classes (cross-asset, regime, divergence, information flow)

### 7d. ~~Explainability layer~~ → DONE
- [x] `explain_match()` — per-method contribution breakdown, natural language summary, strengths/weaknesses
- [x] `explain_forecast()` — direction/magnitude/confidence narrative, risk factors
- [x] `calibration_commentary()` — maps confidence scores to historical accuracy context
- [x] `explain_full()` — convenience wrapper combining match + forecast + calibration
- [x] `MethodContribution` with verdict ("strong"/"moderate"/"weak"/"negligible")
- [x] 18 tests across 4 classes (match explanation, forecast, calibration, full)
- [ ] Historical context overlay (deferred — needs persistent match history DB)

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

---

## GSTACK REVIEW REPORT

| Review | Trigger | Why | Runs | Status | Findings |
|--------|---------|-----|------|--------|----------|
| CEO Review | `/plan-ceo-review` | Scope & strategy | 1 | clean | 1 critical gap (no user validation), 10 auto-decisions |
| Eng Review | `/plan-eng-review` | Architecture & tests | 1 | clean | 7 edge case test gaps, DRY violation noted |
| Codex Review | `/codex review` | Independent 2nd opinion | 0 | skipped | No OPENAI_API_KEY |
| Design Review | `/plan-design-review` | UI/UX gaps | 0 | skipped | "Ship what exists" = no new UI |

**VERDICT:** APPROVED via `/autoplan` — 16 auto-decisions, 1 taste decision (edge case tests, approved). Design doc: "Ship What You Have" at `~/.gstack/projects/the-similarity-base/`. Next: `/ship` when ready.

<!-- AUTONOMOUS DECISION LOG -->
## Decision Audit Trail

| # | Phase | Decision | Principle | Rationale | Rejected |
|---|-------|----------|-----------|-----------|----------|
| 1 | CEO | Mode: SELECTIVE EXPANSION | P1+P2 | Complete review with cherry-picked expansions | SCOPE EXPANSION, HOLD SCOPE |
| 2 | CEO | Plan sequencing wrong — ship first | P6 | No users means infrastructure is premature | Following Phase 6→8 as-is |
| 3 | CEO | Accept 9 methods | P3 | Methods exist, work, tested. Ablation validates later | Reducing methods |
| 4 | CEO | Phase 6-8 gated behind validation | P6 | Pre-product startup needs user feedback | Building Phase 6 immediately |
| 5 | CEO | Expand: Dockerfile + docker-compose | P2 | In blast radius, <1 day CC, required for shipping | Deferring deployment |
| 6 | CEO | Expand: Method ablation framework | P2 | In blast radius, validates core premise | Deferring validation |
| 7 | CEO | Expand: Plan hygiene (stale numbers) | P5 | Plan says 115 tests, actual 315+ | Leaving stale data |
| 8 | CEO | Add backtester results to plan | P1 | Core premise needs empirical evidence | Leaving unvalidated |
| 9 | CEO | Add financial disclaimers note | P5 | Regulatory risk for prediction tools | Ignoring compliance |
| 10 | CEO | Add success criteria to plan | P1 | No metrics = no way to know if product works | Shipping without metrics |
| 11 | CEO | Skip Design Review phase | P3 | "Ship what exists" = no new UI | Running full design review |
| 12 | Eng | Architecture: coupling is clean | P5 | Phase 7 modules import from primitives, no circular deps | N/A |
| 13 | Eng | _enrich_tier2() DRY stays in TODOS | P4 | 7 repetitive blocks, working and tested. Refactor after ship | Refactoring now |
| 14 | Eng | Bare except:pass needs logging for prod | P5 | Silent failures lose observability | Ignoring silent failures |
| 15 | Eng | 7 edge case tests identified | P1 | Coverage gaps in strategy/ensemble/portfolio/explainer | Skipping edge case tests |
| 16 | Eng | Performance: PASS for batch mode | P3 | 1.03s all 9 methods is fast enough | Optimizing before validation |
