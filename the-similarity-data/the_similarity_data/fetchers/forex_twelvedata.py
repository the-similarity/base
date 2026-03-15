from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta

import pandas as pd
import requests

from the_similarity_data.models import DatasetSpec
from the_similarity_data.normalize import canonicalize_ohlcv_frame

INTERVAL_MAP = {
    "15m": "15min",
    "1h": "1h",
    "4h": "4h",
    "1d": "1day",
}


class ForexTwelveDataFetcher:
    def fetch(self, spec: DatasetSpec) -> pd.DataFrame:
        interval = INTERVAL_MAP.get(spec.timeframe)
        if interval is None:
            raise ValueError(f"Unsupported Twelve Data timeframe: {spec.timeframe}")

        api_key = os.getenv("TWELVEDATA_API_KEY", "demo")
        end = datetime.now(UTC)
        start = end - timedelta(days=spec.lookback_days)
        rows: list[dict] = []
        end_cursor = end

        while True:
            response = requests.get(
                "https://api.twelvedata.com/time_series",
                params={
                    "symbol": spec.source_symbol,
                    "interval": interval,
                    "apikey": api_key,
                    "outputsize": 5000,
                    "timezone": "UTC",
                    "end_date": end_cursor.strftime("%Y-%m-%d %H:%M:%S"),
                    "order": "DESC",
                },
                timeout=30,
            )
            response.raise_for_status()
            payload = response.json()

            values = payload.get("values", [])
            if not values:
                break

            rows.extend(values)
            oldest = pd.to_datetime(values[-1]["datetime"], utc=True)
            if oldest <= start:
                break

            end_cursor = oldest - timedelta(seconds=1)

            if len(values) < 5000:
                break

        if not rows:
            raise ValueError(f"No OHLCV data returned for {spec.symbol} {spec.timeframe}")

        frame = pd.DataFrame(rows)
        frame = frame.rename(columns={"datetime": "timestamp"})
        frame["volume"] = 0.0
        return canonicalize_ohlcv_frame(frame)
