from the_similarity.api import load, search, project, ensemble_project, plot, backtest, cross_timeframe_search
from the_similarity.config import Config
from the_similarity.core.feature_store import FeatureStore
from the_similarity.core.matcher import ProgressCallback, ProgressEvent
from the_similarity.core.ensemble import EnsembleForecast
from the_similarity.core.strategy import (
    Signal, SignalType, Rule, Strategy,
    evaluate_strategy, validate_strategy_backtest,
    momentum_strategy, mean_reversion_strategy, breakout_strategy,
)
from the_similarity.core.portfolio import (
    cross_asset_scan, portfolio_regime_scan, divergence_scanner, information_flow_network,
)
from the_similarity.core.explainer import explain_match, explain_forecast, explain_full
from the_similarity.methods.koopman import KoopmanForecast

__all__ = [
    "load", "search", "project", "ensemble_project", "plot", "backtest", "cross_timeframe_search",
    "Config", "KoopmanForecast", "EnsembleForecast", "FeatureStore",
    "ProgressEvent", "ProgressCallback",
    # Phase 7a: Strategy
    "Signal", "SignalType", "Rule", "Strategy",
    "evaluate_strategy", "validate_strategy_backtest",
    "momentum_strategy", "mean_reversion_strategy", "breakout_strategy",
    # Phase 7c: Portfolio
    "cross_asset_scan", "portfolio_regime_scan", "divergence_scanner", "information_flow_network",
    # Phase 7d: Explainability
    "explain_match", "explain_forecast", "explain_full",
]
__version__ = "0.2.0"
