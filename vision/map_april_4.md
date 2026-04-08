# The Similarity — Project Architecture Map
> Generated April 4, 2026 · Full codebase audit

## Overview

**The Similarity** is a self-similarity-based pattern matching and forecasting engine for financial time series. It identifies historical analogs of a query pattern, scores them with a multi-method pipeline, and produces probabilistic forward projections. A secondary module extends the core fractal/multifractal analysis into procedural 3D terrain generation.

---

## Repository Structure

```
14/
├── the_similarity/          ← Core Python engine (pip-installable library)
│   ├── __init__.py          ← Public API re-exports
│   ├── api.py               ← High-level orchestration (load, search, project, etc.)
│   ├── config.py            ← Global hyperparameters (Config dataclass)
│   ├── core/                ← Algorithmic backbone
│   │   ├── matcher.py       ← Tiered matching pipeline orchestrator
│   │   ├── scorer.py        ← Composite confidence scoring
│   │   ├── projector.py     ← Forward projection / forecast cones
│   │   ├── normalizer.py    ← z-score, minmax, log-return normalization
│   │   ├── windower.py      ← Sliding window + multi-scale index generation
│   │   ├── embedding.py     ← Takens delay embedding + auto-lag/dim
│   │   ├── ensemble.py      ← Monte Carlo / regime-conditional / conformal forecasting
│   │   ├── backtester.py    ← Walk-forward backtesting framework
│   │   ├── regime.py        ← Hurst / volatility / slope regime classification
│   │   ├── explainer.py     ← NLG-based match explanations
│   │   ├── strategy.py      ← Rule-based strategy builder
│   │   ├── portfolio.py     ← Cross-asset portfolio analysis
│   │   ├── feature_store.py ← SQLite-backed Tier 2 computation cache
│   │   ├── metrics.py       ← Hit rate, MAE, calibration, CRPS
│   │   ├── auth.py          ← Multi-tenant auth (JWT + API keys + rate limiting)
│   │   ├── alerts.py        ← Watchlist / alert persistence & dispatch
│   │   ├── terrain_generator.py  ← Multi-scale fBm terrain pipeline
│   │   ├── terrain_params.py     ← Terrain presets + heightmap analysis
│   │   ├── erosion.py            ← Hydraulic + thermal erosion simulation
│   │   └── feature_scatter.py    ← Poisson-disk biome-aware feature placement
│   ├── methods/             ← Independent scoring engines (Tier 1 & 2)
│   │   ├── sax_filter.py         ← SAX symbolic pre-filter (Tier 1)
│   │   ├── matrix_profile_filter.py ← MASS FFT distance profile (Tier 1)
│   │   ├── dtw_matcher.py        ← Dynamic Time Warping (Tier 1+2)
│   │   ├── koopman.py            ← Koopman EDMD eigenvalue matching (Tier 2)
│   │   ├── bempedelis.py         ← Self-similarity transform (Tier 2)
│   │   ├── wavelet_leaders.py    ← Multifractal spectrum analysis (Tier 2)
│   │   ├── emd_matcher.py        ← Empirical Mode Decomposition matching (Tier 2)
│   │   ├── tda_matcher.py        ← Topological Data Analysis (Tier 2)
│   │   ├── transfer_entropy.py   ← Information-theoretic predictive score (Tier 2)
│   │   ├── bempedelis_2d.py      ← 2D self-similarity for terrain
│   │   ├── emd_2d.py             ← 2D EMD for terrain scale analysis
│   │   └── wavelet_leaders_2d.py ← 2D Wavelet Leaders for terrain Hurst maps
│   ├── contracts/           ← Pydantic API boundary types
│   │   ├── __init__.py
│   │   └── api.py           ← SearchRequest/Response, Dashboard, Match contracts
│   ├── io/                  ← Data ingestion
│   │   └── loader.py        ← CSV/parquet/DataFrame/array → TimeSeries
│   └── viz/                 ← Visualization
│       └── plotter.py       ← Matplotlib match/forecast plotting
│
├── the-similarity-api/      ← FastAPI HTTP server
│   └── app/
│       ├── main.py          ← Route definitions (REST + WebSocket + terrain)
│       ├── services.py      ← Search execution + dashboard mock assembly
│       ├── streaming.py     ← WebSocket search progress + candle watching
│       ├── data_service.py  ← Parquet catalog loading + dead bar filtering
│       ├── auth_routes.py   ← /auth/* endpoints (register, login, refresh, keys)
│       ├── alert_routes.py  ← /alerts/* endpoints (watchlists, history)
│       ├── auth_deps.py     ← FastAPI DI for auth + rate limiting
│       ├── models.py        ← Catalog/OHLC response models
│       └── settings.py      ← Env-based configuration
│
├── the-similarity-app/      ← Next.js frontend dashboard
│   ├── app/                 ← Pages (layout, globals.css, search, portfolio, strategy)
│   ├── components/          ← React components (chart, dashboard, search, terminal, ui)
│   └── lib/                 ← Client utilities (api.ts, schemas.ts, types.ts, mock-data.ts)
│
├── the-similarity-fractal/  ← Standalone Three.js terrain visualizer
│   ├── index.html           ← UI shell + controls
│   └── src/
│       ├── app.js           ← Scene setup, controls, mode switching, render loop
│       ├── fractal.js       ← Local midpoint-displacement terrain generator
│       └── terrain-renderer.js ← API terrain → Three.js meshes (biome colors, features)
│
├── the-similarity-data/     ← Data warehouse package
│   └── the_similarity_data/
│       ├── warehouse.py     ← Coverage, quality, freshness, versioning
│       ├── config.py        ← Dataset spec loading
│       ├── models.py        ← Data models
│       ├── refresh.py       ← Data refresh orchestration
│       ├── manifest.py      ← Catalog manifest management
│       ├── normalize.py     ← Data normalization
│       ├── storage.py       ← Storage abstraction
│       ├── seed_gold.py     ← Gold dataset seeding
│       └── generate_specs.py ← Dataset specification generation
│
└── vision/                  ← Project roadmap & documentation
```

---

## Core Pipeline Architecture

```
                    ┌─────────────────┐
                    │   api.search()  │  ← Public entry point
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │  io/loader.py   │  CSV/parquet/array → TimeSeries
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │ normalizer.py   │  z-score / minmax / log-return
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │  windower.py    │  Sliding windows + multi-scale index
                    └────────┬────────┘
                             │
              ╔══════════════╧══════════════╗
              ║     TIER 1: PRE-FILTERS     ║
              ║  SAX MINDIST + MASS (FFT)   ║  O(n log n) per candidate
              ║  → prune to top ~100-500    ║
              ╚══════════════╤══════════════╝
                             │
              ╔══════════════╧══════════════╗
              ║  TIER 1b: CHEAP SCORING     ║
              ║  DTW distance + Pearson r   ║
              ║  → rank & keep top_k        ║
              ╚══════════════╤══════════════╝
                             │
              ╔══════════════╧══════════════╗
              ║     TIER 2: ENRICHMENT      ║
              ║  (parallel, cached in       ║
              ║   SQLite feature_store)     ║
              ╠═════════════════════════════╣
              ║ • Koopman EDMD eigenvalues  ║  weight 0.20
              ║ • Bempedelis self-sim R²    ║  weight 0.15
              ║ • Wavelet Leaders spectrum  ║  weight 0.10
              ║ • EMD multi-scale matching  ║  weight 0.10
              ║ • TDA persistence diagrams  ║  weight 0.05
              ║ • Transfer Entropy          ║  weight 0.05
              ╚══════════════╤══════════════╝
                             │
                    ┌────────▼────────┐
                    │   scorer.py     │  Weighted composite → 0-100 score
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │ projector.py    │  Percentile forecast cones
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │  ensemble.py    │  Monte Carlo + regime + conformal
                    └────────┘────────┘
```

---

## Module-by-Module Descriptions

### 1. `the_similarity/` — Core Engine

#### `api.py` — Public API Surface
- **`load(source)`** → `TimeSeries` — Unified data ingestion
- **`search(query, history)`** → `SearchResults` — Full pipeline
- **`project(matches, history)`** → `Forecast` — Forward projection
- **`ensemble_project()`** → `EnsembleForecast` — Monte Carlo + conformal
- **`plot(matches)`** → `Figure` — Matplotlib visualization
- **`backtest(data, query_fn)`** → `BacktestReport` — Walk-forward testing
- **`cross_timeframe_search()`** → Multi-timeframe analog discovery

#### `config.py` — Global Hyperparameters
- `Config` dataclass: window sizes, strides, method weights, tier thresholds
- Default weights: DTW 0.20, Pearson 0.15, Koopman 0.20, Bempedelis 0.15, etc.

#### `core/matcher.py` — Pipeline Orchestrator
- `find_matches()` — The main entry, implements the tiered pipeline
- `ProgressEvent` dataclass for streaming progress to WebSocket clients
- Handles `active_methods` filtering and `progress_fn` callbacks

#### `core/scorer.py` — Confidence Scoring
- `MatchResult` dataclass → all method sub-scores + composite 0-100 confidence
- `ScoreBreakdown` → per-method breakdown for explainability

#### `core/projector.py` — Forward Projection
- Extracts forward windows from each match's post-match history
- Computes weighted percentile curves (P10, P25, P50, P75, P90)
- `Forecast` dataclass with `bars`, `curves`, `all_paths`, `weights`

#### `core/normalizer.py` — Normalization
- Strategies: `zscore`, `minmax`, `log_return`, `pct_change`, `diff`
- Auto-selects strategy based on data characteristics

#### `core/windower.py` — Sliding Windows
- `sliding_windows()` → candidate array + start indices
- Multi-scale: generates windows at 1×, 1.5×, 2× query length
- Stride optimization for large histories

#### `core/embedding.py` — Delay Embedding
- Takens delay embedding for phase space reconstruction
- Auto-lag via first zero of autocorrelation
- Auto-dim via false nearest neighbors

#### `core/ensemble.py` — Ensemble Forecasting
- `ensemble_forecast()` → blends historical, Monte Carlo, regime-conditional
- Conformal prediction intervals using nonconformity scores
- `EnsembleForecast` with structured blended paths

#### `core/backtester.py` — Walk-Forward Backtesting
- Rolling window trials with configurable step size
- Reports hit rate, MAE, calibration, CRPS per trial
- `BacktestReport` with per-trial and aggregate metrics

#### `core/regime.py` — Market Regime Classification
- Hurst exponent estimation (R/S method)
- Volatility regime (low/normal/high)
- Slope regime (trending up/down/sideways)

#### `core/explainer.py` — NLG Explainability
- Generates natural language explanations for each match
- Method-specific narrative templates
- Confidence breakdown in human-readable form

#### `core/strategy.py` — Strategy Builder
- Rule engine for composing trading strategies from matches
- Signal generation, position sizing, stop-loss/take-profit
- Strategy backtesting integration

#### `core/portfolio.py` — Portfolio Analysis
- Cross-asset correlation and similarity
- Portfolio-level regime detection
- Diversification scoring

#### `core/feature_store.py` — Computation Cache
- SQLite-backed + process-safe locking
- Caches expensive Tier 2 computations (Koopman, Bempedelis, TDA)
- Key = hash(method + series_segment)

#### `core/metrics.py` — Evaluation Metrics
- `hit_rate()` — directional accuracy
- `mean_absolute_error()` — point forecast error
- `calibration_score()` — prediction interval reliability
- `crps()` — Continuous Ranked Probability Score

#### `core/auth.py` — Authentication & Authorization
- `AuthManager` — SQLite-backed user/API key/JWT management
- Tiered rate limiting (free/pro/enterprise)
- Password hashing with argon2/bcrypt fallback

#### `core/alerts.py` — Alert System
- `AlertManager` — SQLite-backed watchlist + alert history
- Cooldown-aware alert deduplication
- Multi-channel dispatch (log, webhook, future: email/SMS)

---

### 2. Terrain Generation Subsystem

#### `core/terrain_generator.py` — Generation Pipeline
Pipeline: fBm base → ridge overlay → detail injection → hydraulic erosion → thermal erosion → biome classification → feature scattering

#### `core/terrain_params.py` — Parameter System
- `TerrainParams` dataclass: Hurst, spectrum width, IMF energies
- 6 curated presets: alpine, rolling_hills, desert, coastal, volcanic, canyon
- `analyze_terrain()` — extract params from real heightmap data

#### `core/erosion.py` — Erosion Simulation
- `hydraulic_erosion()` — rainfall droplet simulation (50k iterations default)
- `thermal_erosion()` — talus angle material redistribution
- `flow_accumulation()` — D8 river network detection

#### `core/feature_scatter.py` — Feature Placement
- Poisson-disk sampling for natural spacing
- Biome-aware rules (trees in forest, rocks on slopes, etc.)
- Feature types: tree_pine, tree_oak, rock_small/large, boulder, bush, grass, flower

---

### 3. Analysis Methods (`methods/`)

| Method | Type | Weight | Purpose |
|--------|------|--------|---------|
| `sax_filter.py` | Tier 1 | — | SAX + MINDIST pre-filter (no false dismissals) |
| `matrix_profile_filter.py` | Tier 1 | — | MASS FFT distance profile O(n log n) |
| `dtw_matcher.py` | Tier 1+2 | 0.20 | Dynamic Time Warping with Sakoe-Chiba bands |
| `koopman.py` | Tier 2 | 0.20 | EDMD eigenvalue spectrum + Hungarian matching |
| `bempedelis.py` | Tier 2 | 0.15 | Self-similarity transform R² + smoothness |
| `wavelet_leaders.py` | Tier 2 | 0.10 | f(α) singularity spectrum distance |
| `emd_matcher.py` | Tier 2 | 0.10 | IMF energy-weighted multi-scale matching |
| `tda_matcher.py` | Tier 2 | 0.05 | Persistent homology Wasserstein distance |
| `transfer_entropy.py` | Tier 2 | 0.05 | Information-theoretic predictive scoring |

#### 2D Extensions (for terrain analysis)
- `bempedelis_2d.py` — Scale-invariance scoring for heightmaps
- `emd_2d.py` — Profile-based 2D EMD decomposition
- `wavelet_leaders_2d.py` — Local Hurst exponent maps + 2D singularity spectra

---

### 4. `the-similarity-api/` — FastAPI Server

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/health` | GET | Service status |
| `/dashboard` | GET | Pre-assembled dashboard payload |
| `/catalog` | GET | Available dataset catalog |
| `/datasets/{ac}/{sym}/{tf}/series` | GET | Time series data |
| `/datasets/{ac}/{sym}/{tf}/ohlc` | GET | OHLC candlestick data |
| `/search` | POST | Full search pipeline |
| `/ws/search` | WS | Streaming search progress |
| `/ws/watch` | WS | Live candle pattern watching |
| `/warehouse/coverage` | GET | Data warehouse statistics |
| `/warehouse/quality` | GET | Data quality audit |
| `/warehouse/freshness` | GET | Staleness report |
| `/warehouse/refresh` | POST | Trigger data refresh |
| `/warehouse/search` | GET | Catalog search |
| `/terrain/presets` | GET | Available terrain presets |
| `/terrain/presets/{name}` | GET | Specific preset params |
| `/terrain/generate` | POST | Generate terrain heightmap |
| `/auth/register` | POST | User registration |
| `/auth/login` | POST | Authentication |
| `/auth/refresh` | POST | Token refresh |
| `/auth/me` | GET | Current user profile |
| `/auth/api-keys` | GET/POST | API key management |
| `/auth/api-keys/{id}` | DELETE | Revoke API key |
| `/alerts/watchlists` | GET/POST | Watchlist CRUD |
| `/alerts/watchlists/{id}` | GET/PATCH/DELETE | Single watchlist ops |
| `/alerts/history` | GET | Alert history |
| `/alerts/count` | GET | Alert counts |
| `/alerts/{id}/ack` | POST | Acknowledge alert |

---

### 5. `the-similarity-fractal/` — 3D Terrain Viewer

| File | Role |
|------|------|
| `index.html` | UI shell: controls panel, mode toggle, sliders |
| `src/app.js` | Scene lifecycle, camera, controls, mode switching, render loop |
| `src/fractal.js` | Local midpoint-displacement fractal generator (PRNG, edge dedup, subdivision) |
| `src/terrain-renderer.js` | API terrain → Three.js meshes (biome coloring, instanced features) |

Two rendering modes:
- **Classic**: Pure browser-side fractal generation (no backend needed)
- **Engine**: Fetches terrain from `/terrain/generate` API, renders with biome semantics

---

### 6. `the-similarity-data/` — Data Warehouse

| File | Role |
|------|------|
| `warehouse.py` | Coverage stats, quality checks, freshness reports, dataset versioning |
| `config.py` | Dataset spec loading from YAML configs |
| `models.py` | Pydantic data models |
| `refresh.py` | Dataset refresh orchestration |
| `manifest.py` | Catalog manifest JSON management |
| `normalize.py` | Price data normalization utilities |
| `storage.py` | Storage path abstraction |
| `seed_gold.py` | Gold/reference dataset seeding |
| `generate_specs.py` | Auto-generation of dataset specifications |

---

### 7. `the-similarity-app/` — Next.js Dashboard

| Path | Purpose |
|------|---------|
| `app/page.tsx` | Dashboard landing page |
| `app/globals.css` | Full design system (52KB of custom CSS) |
| `lib/api.ts` | Fetch wrapper for backend API |
| `lib/types.ts` | TypeScript type definitions (mirrors Pydantic contracts) |
| `lib/schemas.ts` | Zod validation schemas |
| `lib/mock-data.ts` | Offline development mock data |
| `components/chart/` | Chart components |
| `components/dashboard/` | Dashboard panels |
| `components/search/` | Search UI |
| `components/terminal/` | Terminal/REPL interface |
| `components/portfolio/` | Portfolio analysis views |
| `components/strategy/` | Strategy builder UI |

---

## Key Architectural Decisions

1. **Tiered Matching**: Cheap methods (SAX, MASS) prune 95%+ of candidates before expensive methods (Koopman, TDA) run. This keeps search interactive.
2. **Feature Store**: SQLite cache prevents redundant Tier 2 computations across searches with overlapping candidates.
3. **Contract-first API**: Pydantic models in `contracts/api.py` are the canonical schema. Both Python API and TypeScript frontend mirror them.
4. **Streaming Progress**: WebSocket search endpoint streams `ProgressEvent` updates so the UI can show real-time progress bars.
5. **Fractal Terrain Bridge**: The same wavelet/EMD/Bempedelis methods used for time series analysis are extended to 2D for terrain generation, creating a conceptual bridge between financial pattern matching and procedural world building.

---

## External Dependencies

### Python
- `numpy`, `scipy` — Core numerics
- `pandas` — Data loading
- `dtaidistance` — C-optimized DTW
- `PyEMD` — Empirical Mode Decomposition
- `pywt` (PyWavelets) — Wavelet transforms
- `ripser`, `persim` — TDA (optional)
- `pydantic` — API contracts
- `fastapi`, `uvicorn` — HTTP server
- `bcrypt`/`argon2-cffi` — Password hashing
- `PyJWT` — Token generation

### JavaScript
- `three.js` (v0.160) — 3D rendering (CDN)
- `next.js` — React framework for dashboard
- `recharts` — Chart library
- `zod` — Schema validation
