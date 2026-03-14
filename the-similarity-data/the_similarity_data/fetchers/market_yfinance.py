from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pandas as pd
import yfinance as yf

from the_similarity_data.models import DatasetSpec
from the_similarity_data.normalize import canonicalize_ohlcv_frame

INTERVAL_MAP = {
    "1h": "60m",
    "1d": "1d",
}


class MarketYFinanceFetcher:
    def fetch(self, spec: DatasetSpec) -> pd.DataFrame:
        interval = INTERVAL_MAP.get(spec.timeframe)
        if interval is None:
            raise ValueError(f"Unsupported yfinance timeframe: {spec.timeframe}")

        end = datetime.now(UTC)
        start = end - timedelta(days=spec.lookback_days)

        frame = yf.download(
            tickers=spec.source_symbol,
            start=start,
            end=end,
            interval=interval,
            auto_adjust=False,
            progress=False,
            threads=False,
            repair=True,
        )
        if frame.empty:
            raise ValueError(f"No OHLCV data returned for {spec.symbol} {spec.timeframe}")

        if isinstance(frame.columns, pd.MultiIndex):
            frame.columns = frame.columns.get_level_values(0)

        frame = frame.reset_index()
        timestamp_column = "Datetime" if "Datetime" in frame.columns else "Date"
        frame = frame.rename(
            columns={
                timestamp_column: "timestamp",
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
