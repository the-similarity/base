import json
from pathlib import Path

import pytest

from the_similarity_data.config import load_dataset_specs, repo_root


def test_repo_root_points_to_data_package():
    root = repo_root()
    assert root.name == "the-similarity-data"
    assert (root / "config" / "datasets.json").exists()


def test_load_dataset_specs_returns_list():
    specs = load_dataset_specs()
    assert isinstance(specs, list)
    assert len(specs) > 0


def test_load_dataset_specs_all_have_required_fields():
    specs = load_dataset_specs()
    for spec in specs:
        assert spec.asset_class in ("crypto", "stocks", "forex", "commodities")
        assert len(spec.symbol) > 0
        assert spec.timeframe in ("1m", "15m", "1h", "4h", "1d")
        assert spec.source in ("ccxt", "stooq", "twelvedata", "yfinance")
        assert len(spec.source_symbol) > 0


def test_load_dataset_specs_from_custom_path(tmp_path):
    config = [
        {
            "asset_class": "test",
            "symbol": "foo",
            "timeframe": "1d",
            "source": "stooq",
            "source_symbol": "foo.us",
        }
    ]
    config_path = tmp_path / "test.json"
    config_path.write_text(json.dumps(config))
    specs = load_dataset_specs(config_path)
    assert len(specs) == 1
    assert specs[0].symbol == "foo"


def test_load_dataset_specs_invalid_path():
    with pytest.raises(FileNotFoundError):
        load_dataset_specs(Path("/nonexistent/path.json"))
