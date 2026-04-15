"""
The Similarity — Pattern matching and forecasting engine for time series.

This package implements a tiered similarity search pipeline that:
1. Accepts a query pattern and a history series
2. Finds the best historical analogs using multi-scale analysis
3. Scores matches with 9 complementary methods (DTW through TDA)
4. Projects forward based on what happened after similar patterns

Public API surface (all importable from `the_similarity` directly):
- `load(source)` → TimeSeries — Data ingestion
- `search(query, history)` → SearchResults — Pattern matching
- `project(matches, history)` → Forecast — Forward projection
- `ensemble_project(...)` → EnsembleForecast — Monte Carlo + conformal
- `plot(matches)` → Figure — Visualization
- `backtest(data, ...)` → BacktestReport — Walk-forward testing
- `cross_timeframe_search(...)` → Multi-scale pattern discovery

AI AGENT NOTES:
- This __init__.py re-exports the public API from submodules so consumers
  can write `import the_similarity; the_similarity.search(...)` without
  knowing the internal package structure.
- __all__ controls what `from the_similarity import *` exposes.
- When adding a new public function, it must be:
  1. Defined in the appropriate submodule (api.py, core/*, etc.)
  2. Imported here
  3. Added to __all__
"""

# --- Core API functions ---
from the_similarity.api import (
    load,
    search,
    project,
    ensemble_project,
    plot,
    backtest,
    cross_timeframe_search,
)

# --- Configuration ---
from the_similarity.config import Config

# --- Core infrastructure ---
from the_similarity.core.feature_store import FeatureStore
from the_similarity.core.matcher import ProgressCallback, ProgressEvent
from the_similarity.core.ensemble import EnsembleForecast

# --- Strategy builder ---
from the_similarity.core.strategy import (
    Signal,
    SignalType,
    Rule,
    Strategy,
    evaluate_strategy,
    validate_strategy_backtest,
    momentum_strategy,
    mean_reversion_strategy,
    breakout_strategy,
)

# --- Portfolio analysis ---
from the_similarity.core.portfolio import (
    cross_asset_scan,
    portfolio_regime_scan,
    divergence_scanner,
    information_flow_network,
)

# --- Explainability ---
from the_similarity.core.explainer import explain_match, explain_forecast, explain_full

# --- Method-specific exports ---
from the_similarity.methods.koopman import KoopmanForecast

__all__ = [
    # Core API
    "load",
    "search",
    "project",
    "ensemble_project",
    "plot",
    "backtest",
    "cross_timeframe_search",
    # Config and infrastructure
    "Config",
    "KoopmanForecast",
    "EnsembleForecast",
    "FeatureStore",
    "ProgressEvent",
    "ProgressCallback",
    # Strategy builder
    "Signal",
    "SignalType",
    "Rule",
    "Strategy",
    "evaluate_strategy",
    "validate_strategy_backtest",
    "momentum_strategy",
    "mean_reversion_strategy",
    "breakout_strategy",
    # Portfolio analysis
    "cross_asset_scan",
    "portfolio_regime_scan",
    "divergence_scanner",
    "information_flow_network",
    # Explainability
    "explain_match",
    "explain_forecast",
    "explain_full",
]

__version__ = "0.2.0"
