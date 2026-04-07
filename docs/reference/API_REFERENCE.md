# The Similarity — API Reference

## Quick Start

```python
from the_similarity import load, search, project, plot, Config

# Load data
history = load("data/stocks/SPY/1d.parquet")
query = history[-60:]  # last 60 bars

# Search for similar patterns
results = search(query, history, top_k=10)
results.summary()

# Project forward
forecast = project(results, history, forward_bars=50)

# Visualize
plot(results, forecast)
```

---

## Core Functions

### `load(source, column="close", date_column=None) -> TimeSeries`

Load time series data from various sources.

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `source` | `str \| DataFrame \| dict \| ndarray` | — | File path (CSV/parquet), pandas DataFrame, dict with `"values"` key, or numpy array |
| `column` | `str` | `"close"` | Column name to extract values from (for tabular sources) |
| `date_column` | `str \| None` | `None` | Column name for dates. Auto-detects `date`, `datetime`, `timestamp` if `None` |

**Returns:** `TimeSeries` — container with `.values` (float64 array), `.dates` (datetime64 array or None), `.name` (str)

**Examples:**

```python
# From parquet
ts = load("data/stocks/AAPL/1d.parquet")

# From CSV
ts = load("prices.csv", column="adj_close", date_column="Date")

# From DataFrame
ts = load(df, column="close")

# From numpy array
ts = load(np.array([100, 101, 99, 102, 103]))

# From dict
ts = load({"values": [100, 101, 99], "dates": ["2024-01-01", "2024-01-02", "2024-01-03"]})
```

**TimeSeries slicing:**

```python
ts = load("data/stocks/SPY/1d.parquet")

# Integer slicing
query = ts[-60:]          # last 60 bars

# Date slicing (requires dates)
segment = ts["2023-01-01":"2023-06-30"]
```

---

### `search(query, history, top_k=20, config=None, weights=None, exclude_self=True, feature_store=None, **kwargs) -> SearchResults`

Search history for patterns similar to query using the full 9-method tiered pipeline.

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `query` | `TimeSeries \| ndarray` | — | The pattern to search for |
| `history` | `TimeSeries \| ndarray` | — | Full historical data to search through |
| `top_k` | `int` | `20` | Number of top matches to return |
| `config` | `Config \| None` | `None` | Pipeline configuration. Uses defaults if `None` |
| `weights` | `dict[str, float] \| None` | `None` | Custom confidence score weights (overrides config) |
| `exclude_self` | `bool` | `True` | Exclude the query region from results (auto-detected) |
| `feature_store` | `FeatureStore \| None` | `None` | SQLite cache for expensive Tier 2 computations |
| `**kwargs` | — | — | Config overrides: `stride`, `normalization`, `tier1_candidates`, etc. |

**Returns:** `SearchResults`

**Pipeline:**

1. **Tier 1 prefilter** — SAX MINDIST + MASS + Pearson blend (0.4/0.4/0.2) → top `tier1_candidates` (default 1000)
2. **Cheap scoring** — DTW + Pearson on all Tier 1 survivors
3. **Tier 2 enrichment** — 7 methods (Bempedelis, Koopman, Wavelet, EMD, TDA, Transfer Entropy, Regime) on top `tier2_candidates` (default 20)
4. **Final rank** — weighted composite confidence score (0–100) → top_k returned

**Examples:**

```python
# Basic search
results = search(query, history)

# Custom config
cfg = Config(stride=3, tier2_candidates=50)
results = search(query, history, config=cfg)

# Override weights
results = search(query, history, weights={"dtw": 0.5, "koopman": 0.5})

# With caching
store = FeatureStore("/tmp/cache.db")
results = search(query, history, feature_store=store)

# Inline config overrides
results = search(query, history, stride=2, normalization="logreturn")
```

---

### `project(matches, history, forward_bars=50, percentiles=None, query=None, config=None) -> Forecast`

Generate a probabilistic forward projection from matched patterns.

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `matches` | `list[MatchResult] \| SearchResults` | — | Match results from `search()` |
| `history` | `TimeSeries \| ndarray` | — | Full historical data |
| `forward_bars` | `int` | `50` | How many bars to project forward |
| `percentiles` | `list[int] \| None` | `None` | Percentile levels (default: `[10, 25, 50, 75, 90]`) |
| `query` | `TimeSeries \| ndarray \| None` | `None` | Query for Koopman forward evolution. Auto-extracted from `SearchResults` |
| `config` | `Config \| None` | `None` | Config for confidence decay and Koopman blend |

**Returns:** `Forecast`

**Forecast object:**

| Field | Type | Description |
|-------|------|-------------|
| `.bars` | `int` | Number of forward bars |
| `.percentiles` | `list[int]` | Percentile levels |
| `.curves` | `dict[int, ndarray]` | Percentile → projected cumulative returns |
| `.all_paths` | `ndarray` | (n_matches, bars) raw projected paths |
| `.weights` | `ndarray` | Confidence weights used |
| `.koopman_forecast` | `KoopmanForecast \| None` | Koopman operator evolution (if query provided) |

**Examples:**

```python
# Basic projection
forecast = project(results, history)

# With Koopman blending
cfg = Config(koopman_blend_weight=0.3, confidence_decay_rate=0.02)
forecast = project(results, history, config=cfg)

# Access forecast data
p50 = forecast.curves[50]   # median projection
p10 = forecast.curves[10]   # 10th percentile (bearish)
p90 = forecast.curves[90]   # 90th percentile (bullish)
```

---

### `plot(results, forecast=None, top_n=5, show=True) -> None`

Visualize matches and optional forecast cone.

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `results` | `SearchResults` | — | Search results to visualize |
| `forecast` | `Forecast \| None` | `None` | Optional forecast to plot alongside |
| `top_n` | `int` | `5` | Number of top matches to show |
| `show` | `bool` | `True` | Whether to call `plt.show()` |

---

### `backtest(history, window_size, forward_bars=50, n_trials=100, config=None, seed=42, n_workers=None, progress_fn=None, top_k=10, feature_store=None) -> BacktestReport`

Run walk-forward backtest to validate the search pipeline.

Each trial picks a random query window, searches only the history before it (no look-ahead), generates a forecast, and compares to actual outcomes.

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `history` | `TimeSeries \| ndarray` | — | Full historical data |
| `window_size` | `int` | — | Length of query window per trial |
| `forward_bars` | `int` | `50` | Bars to project forward |
| `n_trials` | `int` | `100` | Number of random trials |
| `config` | `Config \| None` | `None` | Pipeline config |
| `seed` | `int \| None` | `42` | Random seed for reproducibility |
| `n_workers` | `int \| None` | `None` | Parallel workers (default: `min(4, cpu_count)`) |
| `progress_fn` | `Callable \| None` | `None` | Callback `(completed, total)` for progress |
| `top_k` | `int` | `10` | Matches per trial |
| `feature_store` | `FeatureStore \| None` | `None` | Cache for expensive computations |

**Returns:** `BacktestReport`

**BacktestReport:**

| Property | Type | Description |
|----------|------|-------------|
| `.hit_rate` | `float` | Fraction of trials where P50 predicted correct direction |
| `.mean_error` | `float` | Mean absolute error of P50 vs actual returns |
| `.calibration` | `dict[int, float]` | Actual coverage per percentile band |
| `.crps` | `float` | Continuous Ranked Probability Score (lower = better) |
| `.n_valid_trials` | `int` | Trials that produced results |
| `.n_skipped_trials` | `int` | Trials skipped (no matches, etc.) |
| `.summary()` | `str` | Print formatted report |

**Example:**

```python
report = backtest(history, window_size=60, n_trials=50, forward_bars=30)
report.summary()
# BacktestReport: 48 valid trials, 2 skipped
#   hit_rate=68.8%
#   mean_absolute_error=0.0234
#   crps=0.0156
#   calibration:
#     P10: 12.5% (expected 10%, delta +2.5%)
#     P25: 27.1% (expected 25%, delta +2.1%)
#     ...
```

---

### `cross_timeframe_search(query, history, timeframes, top_k=20, config=None, min_window=10, overlap_threshold=0.5, feature_store=None, **kwargs) -> SearchResults`

Search for patterns across multiple timeframes.

Resamples history to each target timeframe, runs `search()` on each, then merges and deduplicates results.

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `query` | `TimeSeries \| ndarray` | — | Query pattern |
| `history` | `TimeSeries` | — | Full history **with dates** (required for resampling) |
| `timeframes` | `list[str]` | — | Pandas frequency strings: `["1h", "4h", "1D"]` |
| `top_k` | `int` | `20` | Total matches after deduplication |
| `config` | `Config \| None` | `None` | Pipeline config |
| `min_window` | `int` | `10` | Skip timeframes where scaled query < this |
| `overlap_threshold` | `float` | `0.5` | Overlap fraction for deduplication |
| `feature_store` | `FeatureStore \| None` | `None` | Cache |

**Returns:** `SearchResults` with `.source_timeframe` set on each `MatchResult`

---

## Configuration

### `Config`

All hyperparameters in one place. Passed to `search()`, `project()`, `backtest()`.

```python
from the_similarity import Config

cfg = Config(
    # --- Scoring weights (sum to 1.0, renormalized across active_methods) ---
    weights={
        "bempedelis_r2": 0.20,          # power law fit quality
        "bempedelis_smoothness": 0.10,  # transform smoothness
        "koopman": 0.20,               # dynamical system eigenvalue match
        "wavelet_spectrum": 0.15,      # multifractal spectrum match
        "emd": 0.10,                   # multi-scale IMF shape match
        "tda": 0.08,                   # topological persistence match
        "dtw": 0.07,                   # DTW shape distance
        "pearson_warped": 0.05,        # correlation after alignment
        "transfer_entropy": 0.05,      # predictive information flow
    },

    # --- Active methods (controls which methods run) ---
    active_methods=["dtw", "pearson_warped", "koopman", ...],  # default: all 9

    # --- Pipeline tuning ---
    stride=1,                      # window slide step (higher = faster, coarser)
    normalization="logreturn_zscore",  # default normalization
    tier1_candidates=1000,         # survivors from prefilter
    tier2_candidates=20,           # candidates for expensive methods

    # --- SAX prefilter ---
    sax_n_segments=16,
    sax_alphabet_size=8,

    # --- Bempedelis ---
    bempedelis_n_subwindows=5,
    bempedelis_n_restarts=3,

    # --- DTW ---
    dtw_sakoe_chiba_radius=None,   # None = auto (10% of window)

    # --- Projection ---
    forward_bars=50,
    percentiles=[10, 25, 50, 75, 90],
    confidence_decay_rate=0.0,     # widens cone over time (0 = off)
    koopman_blend_weight=0.0,      # blend Koopman into P50 (0 = historical only)
)
```

**Running fewer methods** (faster, less accurate):

```python
# DTW + Pearson only (fastest — skips all Tier 2)
cfg = Config(active_methods=["dtw", "pearson_warped"], tier2_candidates=0)

# Shape methods only
cfg = Config(active_methods=["dtw", "pearson_warped", "koopman", "wavelet_spectrum"])
```

---

## Data Classes

### `SearchResults`

| Field/Method | Type | Description |
|-------------|------|-------------|
| `.matches` | `list[MatchResult]` | Ranked matches (best first) |
| `.query` | `ndarray` | The query array |
| `.best` | `MatchResult \| None` | Highest confidence match |
| `.summary()` | `str` | Print score breakdown table |

### `MatchResult`

| Field | Type | Description |
|-------|------|-------------|
| `.start_idx` | `int` | Start index in history |
| `.end_idx` | `int` | End index in history |
| `.start_date` | `str \| None` | Start date (if history has dates) |
| `.end_date` | `str \| None` | End date |
| `.confidence_score` | `float` | Composite score (0–100) |
| `.score_breakdown` | `ScoreBreakdown` | Per-method scores |
| `.matched_series` | `ndarray \| None` | The matched window values |
| `.transform_alpha` | `ndarray \| None` | Bempedelis alpha transform |
| `.transform_beta` | `ndarray \| None` | Bempedelis beta transform |
| `.transform_r2` | `float` | Bempedelis fit quality |
| `.koopman_eigenvalues` | `ndarray \| None` | Koopman spectrum |
| `.regime` | `str \| None` | Regime label (trending_up, mean_reverting, etc.) |
| `.forward_window` | `ndarray \| None` | What happened after this match |
| `.source_timeframe` | `str \| None` | Origin timeframe (cross-timeframe search) |

### `ScoreBreakdown`

All fields are floats in [0, 1]:

| Field | Method | What it measures |
|-------|--------|-----------------|
| `.dtw` | Dynamic Time Warping | Shape similarity with elastic alignment |
| `.pearson_warped` | Pearson correlation | Linear correlation after DTW alignment |
| `.bempedelis_r2` | Bempedelis transform | Power law self-similarity fit quality |
| `.bempedelis_smoothness` | Bempedelis transform | Transform parameter smoothness |
| `.koopman` | Koopman EDMD | Dynamical system eigenvalue spectrum match |
| `.wavelet_spectrum` | Wavelet Leaders | Multifractal spectrum similarity |
| `.emd` | EMD | Multi-scale IMF decomposition match |
| `.tda` | TDA Persistence | Topological feature similarity |
| `.transfer_entropy` | Transfer Entropy | Predictive information flow |

### `FeatureStore`

```python
from the_similarity import FeatureStore

store = FeatureStore("/tmp/similarity_cache.db")

# Use with search
results = search(query, history, feature_store=store)

# Use with backtest
report = backtest(history, window_size=60, feature_store=store)

# Inspect
print(store.size)   # number of cached entries
store.clear()       # drop all cached data
```

---

## Normalization Modes

| Mode | Transform | Used by |
|------|-----------|---------|
| `logreturn_zscore` | Log returns → per-window z-score | DTW, Pearson, SAX, Matrix Profile, TDA (default) |
| `logreturn` | Log returns only | Bempedelis, Koopman, Wavelet |
| `zscore` | Per-window z-score | — |
| `minmax` | Scale to [0, 1] | — |
| `raw` | No transform | EMD |

Each method uses its own normalization via `METHOD_NORM_DEFAULTS`. You don't need to configure this unless experimenting.
