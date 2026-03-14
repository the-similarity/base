from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta

import ccxt
import pandas as pd

from the_similarity_data.models import DatasetSpec
from the_similarity_data.normalize import canonicalize_ohlcv_frame

TIMEFRAME_MS = {
    "1m": 60_000,
    "15m": 900_000,
    "1h": 3_600_000,
    "4h": 14_400_000,
    "1d": 86_400_000,
}


class CryptoCcxtFetcher:
    def fetch(self, spec: DatasetSpec) -> pd.DataFrame:
        exchange_name = spec.exchange or "binance"
        exchange_class = getattr(ccxt, exchange_name)
        exchange = exchange_class({"enableRateLimit": True})

        timeframe = spec.timeframe
        if timeframe not in TIMEFRAME_MS:
            raise ValueError(f"Unsupported crypto timeframe: {timeframe}")

        now = datetime.now(UTC)
        since = int((now - timedelta(days=spec.lookback_days)).timestamp() * 1000)
        end_time = int(now.timestamp() * 1000)
        step_ms = TIMEFRAME_MS[timeframe]
        rows: list[list[float]] = []
        cursor = since

        while cursor < end_time:
            batch = exchange.fetch_ohlcv(
                symbol=spec.source_symbol,
                timeframe=timeframe,
                since=cursor,
                limit=1000,
            )
            if not batch:
                break

            rows.extend(batch)
            last_timestamp = int(batch[-1][0])
            next_cursor = last_timestamp + step_ms
            if next_cursor <= cursor:
                break
            cursor = next_cursor

            if len(batch) < 1000:
                break

            time.sleep(exchange.rateLimit / 1000)

        if not rows:
            raise ValueError(f"No OHLCV data returned for {spec.symbol} {spec.timeframe}")

        frame = pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close", "volume"])
        frame["timestamp"] = pd.to_datetime(frame["timestamp"], unit="ms", utc=True)
        return canonicalize_ohlcv_frame(frame)
