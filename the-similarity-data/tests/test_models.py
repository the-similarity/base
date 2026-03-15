from pathlib import Path

from the_similarity_data.models import DatasetSpec, RefreshResult


def test_dataset_spec_relative_path():
    spec = DatasetSpec(
        asset_class="crypto",
        symbol="btc_usdt",
        timeframe="1d",
        source="ccxt",
        source_symbol="BTC/USDT",
    )
    assert spec.relative_path == Path("data/crypto/btc_usdt/1d.parquet")


def test_dataset_spec_defaults():
    spec = DatasetSpec(
        asset_class="stocks",
        symbol="spy",
        timeframe="1d",
        source="stooq",
        source_symbol="spy.us",
    )
    assert spec.exchange is None
    assert spec.lookback_days == 365
    assert spec.enabled is True


def test_dataset_spec_frozen():
    spec = DatasetSpec(
        asset_class="forex",
        symbol="eurusd",
        timeframe="1h",
        source="twelvedata",
        source_symbol="EUR/USD",
    )
    try:
        spec.symbol = "usdjpy"
        assert False, "Should have raised"
    except AttributeError:
        pass


def test_refresh_result_frozen():
    result = RefreshResult(
        asset_class="crypto",
        symbol="btc_usdt",
        timeframe="1d",
        source="ccxt",
        path=Path("data/crypto/btc_usdt/1d.parquet"),
        start_timestamp="2024-01-01T00:00:00+00:00",
        end_timestamp="2024-12-31T00:00:00+00:00",
        row_count=365,
        last_updated_at="2024-12-31T12:00:00+00:00",
    )
    assert result.row_count == 365
    try:
        result.row_count = 100
        assert False, "Should have raised"
    except AttributeError:
        pass
