import pandas as pd
import pytest

from the_similarity_data.normalize import CANONICAL_COLUMNS, canonicalize_ohlcv_frame


def _make_frame(**overrides) -> pd.DataFrame:
    data = {
        "timestamp": pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03"], utc=True),
        "open": [100.0, 101.0, 102.0],
        "high": [105.0, 106.0, 107.0],
        "low": [95.0, 96.0, 97.0],
        "close": [103.0, 104.0, 105.0],
        "volume": [1000.0, 1100.0, 1200.0],
    }
    data.update(overrides)
    return pd.DataFrame(data)


def test_canonical_columns_are_correct():
    assert CANONICAL_COLUMNS == ["timestamp", "open", "high", "low", "close", "volume"]


def test_basic_canonicalization():
    df = _make_frame()
    result = canonicalize_ohlcv_frame(df)
    assert list(result.columns) == CANONICAL_COLUMNS
    assert len(result) == 3


def test_lowercases_column_names():
    df = pd.DataFrame({
        "Timestamp": pd.to_datetime(["2024-01-01"], utc=True),
        "Open": [100.0],
        "HIGH": [105.0],
        "Low": [95.0],
        "CLOSE": [103.0],
    })
    result = canonicalize_ohlcv_frame(df)
    assert list(result.columns) == CANONICAL_COLUMNS


def test_adds_volume_if_missing():
    df = pd.DataFrame({
        "timestamp": pd.to_datetime(["2024-01-01"], utc=True),
        "open": [100.0],
        "high": [105.0],
        "low": [95.0],
        "close": [103.0],
    })
    result = canonicalize_ohlcv_frame(df)
    assert result["volume"].iloc[0] == 0.0


def test_drops_duplicate_timestamps():
    df = pd.DataFrame({
        "timestamp": pd.to_datetime(["2024-01-01", "2024-01-01", "2024-01-02"], utc=True),
        "open": [100.0, 101.0, 102.0],
        "high": [105.0, 106.0, 107.0],
        "low": [95.0, 96.0, 97.0],
        "close": [103.0, 104.0, 105.0],
        "volume": [1000.0, 1100.0, 1200.0],
    })
    result = canonicalize_ohlcv_frame(df)
    assert len(result) == 2
    # keep='last' — second row for 2024-01-01 should win
    assert result.iloc[0]["open"] == 101.0


def test_sorts_by_timestamp():
    df = pd.DataFrame({
        "timestamp": pd.to_datetime(["2024-01-03", "2024-01-01", "2024-01-02"], utc=True),
        "open": [102.0, 100.0, 101.0],
        "high": [107.0, 105.0, 106.0],
        "low": [97.0, 95.0, 96.0],
        "close": [105.0, 103.0, 104.0],
        "volume": [1200.0, 1000.0, 1100.0],
    })
    result = canonicalize_ohlcv_frame(df)
    assert result.iloc[0]["open"] == 100.0
    assert result.iloc[2]["open"] == 102.0


def test_drops_nan_in_ohlc():
    df = pd.DataFrame({
        "timestamp": pd.to_datetime(["2024-01-01", "2024-01-02"], utc=True),
        "open": [100.0, float("nan")],
        "high": [105.0, 106.0],
        "low": [95.0, 96.0],
        "close": [103.0, 104.0],
        "volume": [1000.0, 1100.0],
    })
    result = canonicalize_ohlcv_frame(df)
    assert len(result) == 1


def test_fills_nan_volume_with_zero():
    df = pd.DataFrame({
        "timestamp": pd.to_datetime(["2024-01-01"], utc=True),
        "open": [100.0],
        "high": [105.0],
        "low": [95.0],
        "close": [103.0],
        "volume": [float("nan")],
    })
    result = canonicalize_ohlcv_frame(df)
    assert result["volume"].iloc[0] == 0.0


def test_raises_without_timestamp():
    df = pd.DataFrame({"open": [1], "high": [2], "low": [0], "close": [1]})
    with pytest.raises(ValueError, match="timestamp"):
        canonicalize_ohlcv_frame(df)


def test_raises_without_ohlc_column():
    df = pd.DataFrame({
        "timestamp": pd.to_datetime(["2024-01-01"], utc=True),
        "open": [100.0],
        "high": [105.0],
        "low": [95.0],
        # missing close
    })
    with pytest.raises(ValueError, match="close"):
        canonicalize_ohlcv_frame(df)


def test_coerces_string_prices_to_float():
    df = pd.DataFrame({
        "timestamp": pd.to_datetime(["2024-01-01"], utc=True),
        "open": ["100.5"],
        "high": ["105.5"],
        "low": ["95.5"],
        "close": ["103.5"],
        "volume": ["1000"],
    })
    result = canonicalize_ohlcv_frame(df)
    assert result["close"].dtype == "float64"
    assert result["close"].iloc[0] == 103.5
