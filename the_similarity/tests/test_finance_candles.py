"""Tests for engine-built OHLCV candles."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from the_similarity.finance.candles import build_candles, infer_source_timeframe


def _ohlcv(periods: int, freq: str, start: str = "2024-01-01T00:00:00Z") -> pd.DataFrame:
    """Create deterministic OHLCV rows where aggregation is easy to audit."""

    base = np.arange(periods, dtype=float)
    return pd.DataFrame(
        {
            "timestamp": pd.date_range(start, periods=periods, freq=freq),
            "open": 100.0 + base,
            "high": 101.0 + base,
            "low": 99.0 + base,
            "close": 100.5 + base,
            "volume": 10.0 + base,
        }
    )


def test_twelve_5m_candles_make_one_1h_candle() -> None:
    source = _ohlcv(12, "5min")

    candles = build_candles(source, "1h", source_timeframe="5m")

    assert len(candles) == 1
    candle = candles.iloc[0]
    assert candle["open"] == source["open"].iloc[0]
    assert candle["high"] == source["high"].max()
    assert candle["low"] == source["low"].min()
    assert candle["close"] == source["close"].iloc[-1]
    assert candle["volume"] == source["volume"].sum()
    assert bool(candle["is_complete"]) is True


def test_six_4h_candles_make_one_crypto_1d_candle() -> None:
    source = _ohlcv(6, "4h")

    candles = build_candles(source, "1d", source_timeframe="4h", market="24/7")

    assert len(candles) == 1
    assert candles["open"].tolist() == [100.0]
    assert candles["close"].tolist() == [105.5]
    assert candles["volume"].tolist() == [75.0]


def test_incomplete_candles_are_dropped_by_default() -> None:
    source = _ohlcv(19, "5min")

    dropped = build_candles(source, "1h", source_timeframe="5m")
    kept = build_candles(source, "1h", source_timeframe="5m", include_incomplete=True)

    assert len(dropped) == 1
    assert len(kept) == 2
    assert kept["is_complete"].tolist() == [True, False]


def test_return_stats_explains_expected_source_rows_and_drops() -> None:
    source = _ohlcv(19, "5min")

    result = build_candles(source, "1h", source_timeframe="5m", return_stats=True)

    assert result.stats.source_timeframe == "5m"
    assert result.stats.target_timeframe == "1h"
    assert result.stats.expected_source_rows == 12
    assert result.stats.incomplete_rows == 1
    assert result.stats.output_rows == 1


def test_rejects_finer_target_timeframe() -> None:
    source = _ohlcv(10, "1h")

    with pytest.raises(ValueError, match="Cannot build finer candles"):
        build_candles(source, "5m", source_timeframe="1h")


def test_rejects_target_that_is_not_even_multiple() -> None:
    source = _ohlcv(10, "7min")

    with pytest.raises(ValueError, match="not an even multiple"):
        build_candles(source, "1h", source_timeframe="7m")


def test_session_market_anchors_intraday_buckets_to_session_start() -> None:
    source = _ohlcv(8, "30min", start="2024-01-02T14:30:00Z")

    candles = build_candles(
        source,
        "1h",
        source_timeframe="30m",
        market="session",
        session_start="14:30",
    )

    assert len(candles) == 4
    assert candles["timestamp"].dt.minute.tolist() == [30, 30, 30, 30]
    assert candles["open"].tolist() == [100.0, 102.0, 104.0, 106.0]
    assert candles["close"].tolist() == [101.5, 103.5, 105.5, 107.5]


def test_infers_source_timeframe_from_timestamps() -> None:
    source = _ohlcv(4, "15min")

    inferred = infer_source_timeframe(source)

    assert inferred.code == "15m"
