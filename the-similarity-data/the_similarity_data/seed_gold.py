"""Seed gold parquet files.

Creates gold 1d, 4h, and 1h parquet files.
Strategy: try external APIs (Stooq daily, Twelve Data intraday) first;
fall back to generating realistic synthetic data from a GBM model
calibrated to gold's historical parameters.

Usage:
    python -m the_similarity_data.seed_gold
"""
from __future__ import annotations

import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from the_similarity_data.config import default_manifest_path, repo_root
from the_similarity_data.manifest import update_manifest
from the_similarity_data.models import DatasetSpec
from the_similarity_data.normalize import canonicalize_ohlcv_frame
from the_similarity_data.storage import upsert_parquet


# Gold calibration parameters (annualized, from 2015-2025 XAU/USD)
_GOLD_MU = 0.08        # ~8% annual drift
_GOLD_SIGMA = 0.15     # ~15% annual volatility
_GOLD_START = 1200.0   # Start price (2015 level)


def _generate_gold_ohlcv(
    n_bars: int,
    interval_hours: float,
    start_date: datetime,
    seed: int = 2024,
) -> pd.DataFrame:
    """Generate realistic gold OHLCV data using Geometric Brownian Motion.

    Calibrated to XAU/USD historical parameters with intraday volatility
    clustering and mean-reverting high/low spreads.
    """
    rng = np.random.default_rng(seed)

    # Annualized params → per-bar params
    bars_per_year = (365.25 * 24) / interval_hours
    dt = 1.0 / bars_per_year
    mu_bar = _GOLD_MU * dt
    sigma_bar = _GOLD_SIGMA * np.sqrt(dt)

    # Generate log-return path with volatility clustering (GARCH-like)
    vol = np.full(n_bars, sigma_bar)
    for i in range(1, n_bars):
        # Simple vol clustering: vol reverts to sigma_bar with persistence
        shock = abs(rng.standard_normal())
        vol[i] = 0.9 * vol[i - 1] + 0.1 * sigma_bar * (0.5 + shock)

    returns = mu_bar + vol * rng.standard_normal(n_bars)
    log_prices = np.log(_GOLD_START) + np.cumsum(returns)
    closes = np.exp(log_prices)

    # Generate OHLC from close prices
    rows = []
    for i in range(n_bars):
        c = closes[i]
        bar_vol = vol[i] * c  # absolute volatility for this bar

        # Open: close of previous bar (or start price)
        o = closes[i - 1] if i > 0 else _GOLD_START

        # High/Low: spread around the open-close range
        oc_high = max(o, c)
        oc_low = min(o, c)
        h = oc_high + abs(rng.standard_normal()) * bar_vol * 0.5
        l = oc_low - abs(rng.standard_normal()) * bar_vol * 0.5
        l = max(l, oc_low * 0.995)  # floor

        ts = start_date + timedelta(hours=interval_hours * i)

        rows.append({
            "timestamp": ts,
            "open": round(o, 2),
            "high": round(h, 2),
            "low": round(l, 2),
            "close": round(c, 2),
            "volume": round(rng.exponential(1000) * 100, 0),
        })

    return pd.DataFrame(rows)


def _try_stooq_daily() -> pd.DataFrame | None:
    """Try fetching daily gold from Stooq (free)."""
    try:
        from the_similarity_data.fetchers.stooq_daily import StooqDailyFetcher
        spec = DatasetSpec(
            asset_class="commodities", symbol="gold", timeframe="1d",
            source="stooq", source_symbol="XAUUSD", lookback_days=3650,
        )
        df = StooqDailyFetcher().fetch(spec)
        if len(df) > 100:
            return df
    except Exception as e:
        print(f"  Stooq unavailable: {e}")
    return None


def _try_twelvedata(spec: DatasetSpec) -> pd.DataFrame | None:
    """Try fetching from Twelve Data if API key is set."""
    api_key = os.getenv("TWELVEDATA_API_KEY", "")
    if not api_key or api_key == "demo":
        return None
    try:
        from the_similarity_data.fetchers.forex_twelvedata import ForexTwelveDataFetcher
        return ForexTwelveDataFetcher().fetch(spec)
    except Exception as e:
        print(f"  Twelve Data failed: {e}")
    return None


def seed_gold() -> None:
    """Seed all gold timeframes."""
    data_root = repo_root()
    manifest_path = default_manifest_path()
    now = datetime.now(UTC)

    # --- 1. Gold Daily ---
    print("Seeding gold 1d...")
    daily_spec = DatasetSpec(
        asset_class="commodities", symbol="gold", timeframe="1d",
        source="stooq", source_symbol="XAUUSD", lookback_days=3650,
    )
    daily_df = _try_stooq_daily()
    if daily_df is None:
        print("  Generating synthetic daily (GBM, 10yr)...")
        start = now - timedelta(days=3650)
        daily_df = _generate_gold_ohlcv(3650, interval_hours=24, start_date=start, seed=2024)
        daily_df = canonicalize_ohlcv_frame(daily_df)
    else:
        cutoff = now - timedelta(days=3650)
        daily_df = daily_df[daily_df["timestamp"] >= cutoff].reset_index(drop=True)

    print(f"  1d: {len(daily_df)} rows")
    merged = upsert_parquet(data_root / daily_spec.relative_path, daily_df)
    update_manifest(manifest_path, daily_spec, merged)

    # --- 2. Gold 4h ---
    print("Seeding gold 4h...")
    h4_spec = DatasetSpec(
        asset_class="commodities", symbol="gold", timeframe="4h",
        source="twelvedata", source_symbol="XAU/USD", lookback_days=3650,
    )
    h4_df = _try_twelvedata(h4_spec)
    if h4_df is None:
        print("  Generating synthetic 4h (GBM, 6yr)...")
        start = now - timedelta(days=2190)
        n_bars = int(2190 * 24 / 4)
        h4_df = _generate_gold_ohlcv(n_bars, interval_hours=4, start_date=start, seed=2025)
        h4_df = canonicalize_ohlcv_frame(h4_df)

    print(f"  4h: {len(h4_df)} rows")
    merged = upsert_parquet(data_root / h4_spec.relative_path, h4_df)
    update_manifest(manifest_path, h4_spec, merged)

    # --- 3. Gold 1h ---
    print("Seeding gold 1h...")
    h1_spec = DatasetSpec(
        asset_class="commodities", symbol="gold", timeframe="1h",
        source="twelvedata", source_symbol="XAU/USD", lookback_days=730,
    )
    h1_df = _try_twelvedata(h1_spec)
    if h1_df is None:
        print("  Generating synthetic 1h (GBM, 2yr)...")
        start = now - timedelta(days=730)
        n_bars = 730 * 24
        h1_df = _generate_gold_ohlcv(n_bars, interval_hours=1, start_date=start, seed=2026)
        h1_df = canonicalize_ohlcv_frame(h1_df)

    print(f"  1h: {len(h1_df)} rows")
    merged = upsert_parquet(data_root / h1_spec.relative_path, h1_df)
    update_manifest(manifest_path, h1_spec, merged)

    print("Done! Gold data seeded across all timeframes.")


if __name__ == "__main__":
    seed_gold()
