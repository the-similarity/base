from unittest.mock import patch

import pandas as pd
import pytest

from the_similarity_data.fetchers.stooq_daily import StooqApiKeyMissing, StooqDailyFetcher
from the_similarity_data.models import DatasetSpec


def _make_spec(**overrides) -> DatasetSpec:
    defaults = dict(
        asset_class="stocks",
        symbol="spy",
        timeframe="1d",
        source="stooq",
        source_symbol="spy.us",
    )
    defaults.update(overrides)
    return DatasetSpec(**defaults)


class _Response:
    def __init__(self, text: str, status_code: int = 200) -> None:
        self.text = text
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"http {self.status_code}")


def test_fetch_parses_csv_payload():
    payload = "\n".join(
        [
            "Date,Open,High,Low,Close,Volume",
            "2026-04-10,500,505,495,503,1000",
            "2026-04-11,503,506,501,504,1100",
        ]
    )

    with patch("the_similarity_data.fetchers.stooq_daily.requests.get", return_value=_Response(payload)) as mock_get:
        frame = StooqDailyFetcher().fetch(_make_spec())

    assert list(frame.columns) == ["timestamp", "open", "high", "low", "close", "volume"]
    assert len(frame) == 2
    assert frame["close"].tolist() == [503.0, 504.0]
    assert frame["timestamp"].dtype == pd.Series(pd.to_datetime(["2026-04-10"], utc=True)).dtype
    assert mock_get.call_args.kwargs["params"] == {"s": "spy.us", "i": "d"}


def test_fetch_adds_apikey_from_environment(monkeypatch):
    payload = "\n".join(
        [
            "Date,Open,High,Low,Close,Volume",
            "2026-04-10,500,505,495,503,1000",
        ]
    )
    monkeypatch.setenv("STOOQ_APIKEY", "secret-key")

    with patch("the_similarity_data.fetchers.stooq_daily.requests.get", return_value=_Response(payload)) as mock_get:
        StooqDailyFetcher().fetch(_make_spec())

    assert mock_get.call_args.kwargs["params"] == {
        "s": "spy.us",
        "i": "d",
        "apikey": "secret-key",
    }


def test_fetch_raises_clear_error_for_apikey_prompt():
    payload = "\n".join(
        [
            "Get your apikey:",
            "",
            "1. Open https://stooq.com/q/d/?s=spy.us&get_apikey",
        ]
    )

    with patch("the_similarity_data.fetchers.stooq_daily.requests.get", return_value=_Response(payload)):
        with pytest.raises(StooqApiKeyMissing, match="requires an API key"):
            StooqDailyFetcher().fetch(_make_spec())


def test_fetch_rejects_non_csv_payload():
    payload = "<html><body>temporary upstream error</body></html>"

    with patch("the_similarity_data.fetchers.stooq_daily.requests.get", return_value=_Response(payload)):
        with pytest.raises(ValueError, match="Unexpected Stooq response format"):
            StooqDailyFetcher().fetch(_make_spec())
