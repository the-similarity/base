"""Tests for the dataset spec generator."""
from __future__ import annotations

from the_similarity_data.generate_specs import (
    generate_all_specs,
    summary,
    CRYPTO_SYMBOLS,
    STOCK_SYMBOLS_STOOQ,
    FOREX_SYMBOLS,
    COMMODITIES_TWELVEDATA,
    INDEX_SYMBOLS,
    RATES_SYMBOLS,
)


class TestGenerateSpecs:
    def test_total_spec_count_above_500(self):
        specs = generate_all_specs()
        assert len(specs) >= 500, f"expected >=500 specs, got {len(specs)}"

    def test_unique_symbols_above_200(self):
        specs = generate_all_specs()
        stats = summary(specs)
        assert stats["unique_symbols"] >= 200

    def test_all_asset_classes_present(self):
        specs = generate_all_specs()
        classes = {s["asset_class"] for s in specs}
        assert "crypto" in classes
        assert "stocks" in classes
        assert "forex" in classes
        assert "commodities" in classes
        assert "indices" in classes
        assert "rates" in classes

    def test_all_sources_present(self):
        specs = generate_all_specs()
        sources = {s["source"] for s in specs}
        assert "ccxt" in sources
        assert "stooq" in sources
        assert "twelvedata" in sources

    def test_spec_schema(self):
        specs = generate_all_specs()
        required_keys = {"asset_class", "symbol", "timeframe", "source",
                         "source_symbol", "lookback_days", "enabled"}
        for spec in specs:
            assert required_keys <= set(spec.keys()), f"missing keys in {spec}"
            assert spec["enabled"] is True
            assert spec["lookback_days"] > 0

    def test_crypto_has_all_timeframes(self):
        specs = generate_all_specs()
        btc_specs = [s for s in specs if s["symbol"] == "btc_usdt"]
        btc_tfs = {s["timeframe"] for s in btc_specs}
        assert btc_tfs == {"1m", "5m", "15m", "1h", "4h", "1d"}

    def test_stocks_daily_only(self):
        specs = generate_all_specs()
        stock_tfs = {s["timeframe"] for s in specs if s["asset_class"] == "stocks"}
        assert stock_tfs == {"1d"}, "stocks should only have daily data via stooq"

    def test_no_duplicate_specs(self):
        specs = generate_all_specs()
        keys = [(s["asset_class"], s["symbol"], s["timeframe"], s["source"]) for s in specs]
        assert len(keys) == len(set(keys)), "duplicate specs found"

    def test_lookback_scales_with_timeframe(self):
        specs = generate_all_specs()
        for spec in specs:
            tf = spec["timeframe"]
            lb = spec["lookback_days"]
            if tf == "1m":
                assert lb <= 60, f"1m should have short lookback, got {lb}"
            elif tf == "1d":
                assert lb >= 365, f"1d should have long lookback, got {lb}"

    def test_summary_format(self):
        specs = generate_all_specs()
        stats = summary(specs)
        assert "total_specs" in stats
        assert "unique_symbols" in stats
        assert "by_asset_class" in stats
        assert "by_source" in stats
