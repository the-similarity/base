import pandas as pd
import pytest

from the_similarity_data.storage import upsert_parquet


def _make_frame(dates, closes):
    return pd.DataFrame({
        "timestamp": pd.to_datetime(dates, utc=True),
        "open": closes,
        "high": [c + 5 for c in closes],
        "low": [c - 5 for c in closes],
        "close": closes,
        "volume": [1000.0] * len(closes),
    })


def test_upsert_creates_new_file(tmp_path):
    path = tmp_path / "data" / "test.parquet"
    df = _make_frame(["2024-01-01", "2024-01-02"], [100.0, 101.0])
    result = upsert_parquet(path, df)
    assert path.exists()
    assert len(result) == 2


def test_upsert_appends_new_data(tmp_path):
    path = tmp_path / "test.parquet"
    df1 = _make_frame(["2024-01-01", "2024-01-02"], [100.0, 101.0])
    upsert_parquet(path, df1)

    df2 = _make_frame(["2024-01-03", "2024-01-04"], [102.0, 103.0])
    result = upsert_parquet(path, df2)
    assert len(result) == 4


def test_upsert_deduplicates_by_timestamp(tmp_path):
    path = tmp_path / "test.parquet"
    df1 = _make_frame(["2024-01-01", "2024-01-02"], [100.0, 101.0])
    upsert_parquet(path, df1)

    # Overlapping timestamp — should replace, not duplicate
    df2 = _make_frame(["2024-01-02", "2024-01-03"], [999.0, 103.0])
    result = upsert_parquet(path, df2)
    assert len(result) == 3
    # Last write wins for 2024-01-02
    row = result[result["close"] == 999.0]
    assert len(row) == 1


def test_upsert_creates_parent_dirs(tmp_path):
    path = tmp_path / "deep" / "nested" / "dir" / "test.parquet"
    df = _make_frame(["2024-01-01"], [100.0])
    upsert_parquet(path, df)
    assert path.exists()


def test_upsert_result_is_sorted(tmp_path):
    path = tmp_path / "test.parquet"
    df = _make_frame(["2024-01-03", "2024-01-01", "2024-01-02"], [103.0, 100.0, 101.0])
    result = upsert_parquet(path, df)
    assert result["close"].tolist() == [100.0, 101.0, 103.0]


def test_roundtrip_parquet_preserves_data(tmp_path):
    path = tmp_path / "test.parquet"
    df = _make_frame(["2024-01-01", "2024-01-02"], [100.5, 101.5])
    upsert_parquet(path, df)

    loaded = pd.read_parquet(path)
    assert loaded["close"].tolist() == [100.5, 101.5]
    assert loaded["volume"].tolist() == [1000.0, 1000.0]
