from __future__ import annotations

from io import StringIO

import pandas as pd
import requests

from the_similarity_data.models import DatasetSpec
from the_similarity_data.normalize import canonicalize_ohlcv_frame


class StooqDailyFetcher:
    def fetch(self, spec: DatasetSpec) -> pd.DataFrame:
        if spec.timeframe != "1d":
            raise ValueError("StooqDailyFetcher only supports 1d datasets")

        response = requests.get(
            "https://stooq.com/q/d/l/",
            params={"s": spec.source_symbol, "i": "d"},
            timeout=30,
        )
        response.raise_for_status()

        frame = pd.read_csv(StringIO(response.text))
        if frame.empty or "No data" in response.text:
            raise ValueError(f"No OHLCV data returned for {spec.symbol} {spec.timeframe}")

        frame = frame.rename(
            columns={
                "Date": "timestamp",
                "Open": "open",
                "High": "high",
                "Low": "low",
                "Close": "close",
                "Volume": "volume",
            }
        )
        if "volume" not in frame.columns:
            frame["volume"] = 0.0

        return canonicalize_ohlcv_frame(frame)
