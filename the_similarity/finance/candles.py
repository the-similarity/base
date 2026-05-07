"""OHLCV candle construction utilities.

The similarity engine consumes one-dimensional series for most searches, but
the product also needs faithful candles for charting, backtesting, and future
multi-column pattern features. This module is the single place that turns a
finer OHLCV feed into coarser candles.

AI AGENT NOTES:
- Do not replace this with close-only resampling. A candle has financial
  semantics: open=first, high=max, low=min, close=last, volume=sum.
- Only build coarser candles from finer candles. Upsampling (for example
  1h -> 5m) invents intrabar structure and must stay outside this path unless
  a caller explicitly labels it synthetic elsewhere.
- Incomplete candles are dangerous for similarity search because a partial
  1h bar built from seven 5m bars can look like a valid low-volatility setup.
  The default therefore drops incomplete buckets whenever source coverage can
  be estimated.
- Calendar-aware exchange sessions are intentionally lightweight here. Crypto
  and other 24/7 markets can use UTC wall-clock buckets. Equities can pass a
  session start such as "09:30" so intraday bars align to the regular session
  open. Full holiday/early-close calendars belong in ingestion, not this pure
  aggregation helper.
"""

from __future__ import annotations

from dataclasses import dataclass
import re

import pandas as pd


_TIMEFRAME_RE = re.compile(r"^\s*(?P<count>\d+)?\s*(?P<unit>[mhdwMHDW])\s*$")
_UNIT_TO_SECONDS = {
    "m": 60,
    "h": 60 * 60,
    "d": 24 * 60 * 60,
    "w": 7 * 24 * 60 * 60,
}


@dataclass(frozen=True)
class Timeframe:
    """Parsed fixed-duration timeframe.

    ``code`` preserves a normalized display form (``5m``, ``1h``, ``1d``).
    ``pandas_freq`` is what pandas uses for ``resample``. The duration is
    stored in seconds so the builder can compare source and target frequency
    without relying on pandas internals.
    """

    code: str
    pandas_freq: str
    seconds: int


@dataclass(frozen=True)
class CandleBuildStats:
    """Summary of what happened during candle construction.

    The API layer does not expose this yet, but tests and future diagnostics can
    use it to explain why a request produced fewer bars than the raw resample.
    """

    source_timeframe: str
    target_timeframe: str
    input_rows: int
    output_rows: int
    incomplete_rows: int
    expected_source_rows: int | None


@dataclass(frozen=True)
class CandleBuildResult:
    """Candles plus construction metadata."""

    candles: pd.DataFrame
    stats: CandleBuildStats


def parse_timeframe(value: str) -> Timeframe:
    """Parse a fixed market timeframe such as ``5m``, ``1h``, ``4h`` or ``1d``.

    The project catalog uses short timeframe codes. Pandas accepts many aliases,
    but accepting every offset string here would make coverage checks ambiguous
    (for example calendar months do not have a fixed number of source bars).
    This function intentionally supports only fixed minute/hour/day/week units.
    """

    match = _TIMEFRAME_RE.match(value)
    if not match:
        raise ValueError(
            f"Unsupported timeframe '{value}'. Use fixed codes like 5m, 1h, 4h, 1d."
        )

    count = int(match.group("count") or "1")
    if count <= 0:
        raise ValueError(f"Timeframe count must be positive, got '{value}'")

    unit = match.group("unit").lower()
    seconds = count * _UNIT_TO_SECONDS[unit]
    code = f"{count}{unit}"
    return Timeframe(code=code, pandas_freq=code, seconds=seconds)


def infer_source_timeframe(
    df: pd.DataFrame, timestamp_col: str = "timestamp"
) -> Timeframe:
    """Infer source frequency from the median timestamp spacing.

    This is a fallback for ad-hoc DataFrames. Catalog/API callers should pass
    the known source timeframe from the dataset ID because it is more reliable
    than inference on feeds with gaps, holidays, or missing bars.
    """

    if timestamp_col not in df.columns:
        raise ValueError(
            "Cannot infer source timeframe without a timestamp column; pass source_timeframe."
        )

    timestamps = pd.to_datetime(df[timestamp_col], utc=True).sort_values()
    deltas = timestamps.diff().dropna()
    if deltas.empty:
        raise ValueError("Cannot infer source timeframe from fewer than two timestamps")

    seconds = int(deltas.median().total_seconds())
    if seconds <= 0:
        raise ValueError("Cannot infer source timeframe from non-increasing timestamps")

    # Prefer compact catalog-style codes when the median lands on a normal unit.
    if seconds % _UNIT_TO_SECONDS["w"] == 0:
        return parse_timeframe(f"{seconds // _UNIT_TO_SECONDS['w']}w")
    if seconds % _UNIT_TO_SECONDS["d"] == 0:
        return parse_timeframe(f"{seconds // _UNIT_TO_SECONDS['d']}d")
    if seconds % _UNIT_TO_SECONDS["h"] == 0:
        return parse_timeframe(f"{seconds // _UNIT_TO_SECONDS['h']}h")
    if seconds % _UNIT_TO_SECONDS["m"] == 0:
        return parse_timeframe(f"{seconds // _UNIT_TO_SECONDS['m']}m")

    raise ValueError(
        "Inferred source spacing is not an even minute/hour/day/week timeframe"
    )


def build_candles(
    df: pd.DataFrame,
    target_timeframe: str,
    *,
    source_timeframe: str | None = None,
    timestamp_col: str = "timestamp",
    market: str = "24/7",
    session_start: str | None = None,
    include_incomplete: bool = False,
    return_stats: bool = False,
) -> pd.DataFrame | CandleBuildResult:
    """Build coarser OHLCV candles from finer OHLCV rows.

    Args:
        df: Source rows with ``timestamp``, ``open``, ``high``, ``low``,
            ``close`` and optional ``volume`` columns.
        target_timeframe: Desired coarser timeframe (for example ``1h``,
            ``45m``, ``4h``, ``1d``).
        source_timeframe: Known source timeframe. Pass this from catalog IDs
            whenever possible; when omitted it is inferred from timestamp gaps.
        timestamp_col: Name of the timestamp column.
        market: ``"24/7"`` for UTC wall-clock buckets, or ``"session"`` for
            intraday buckets anchored to a regular-session open.
        session_start: Clock time like ``"09:30"`` used only when
            ``market="session"``. It shifts pandas bucket boundaries so
            30m/1h/4h bars start from the exchange open instead of midnight.
        include_incomplete: Keep the final/partial buckets when True. The
            default False is safer for search and backtests.
        return_stats: Return ``CandleBuildResult`` instead of just the DataFrame.

    Returns:
        A DataFrame with ``timestamp``, OHLC, optional ``volume``, and an
        ``is_complete`` boolean. If ``return_stats`` is True, returns a wrapper
        containing the DataFrame and construction stats.
    """

    required = {"open", "high", "low", "close", timestamp_col}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing required candle columns: {sorted(missing)}")

    source = (
        parse_timeframe(source_timeframe)
        if source_timeframe
        else infer_source_timeframe(df, timestamp_col)
    )
    target = parse_timeframe(target_timeframe)
    if target.seconds < source.seconds:
        raise ValueError(
            f"Cannot build finer candles: source={source.code}, target={target.code}"
        )
    if target.seconds == source.seconds:
        result = _normalize_passthrough(df, timestamp_col)
        if "is_complete" not in result.columns:
            result["is_complete"] = True
        stats = CandleBuildStats(
            source_timeframe=source.code,
            target_timeframe=target.code,
            input_rows=len(df),
            output_rows=len(result),
            incomplete_rows=0,
            expected_source_rows=1,
        )
        return CandleBuildResult(result, stats) if return_stats else result

    if target.seconds % source.seconds != 0:
        raise ValueError(
            f"Target timeframe {target.code} is not an even multiple of source {source.code}"
        )

    working = _normalize_passthrough(df, timestamp_col)
    working = working.set_index("timestamp")

    aggregation: dict[str, str] = {
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
    }
    if "volume" in working.columns:
        aggregation["volume"] = "sum"

    # ``count`` is the source-row coverage for each output bucket. We compute it
    # from close because close is required and non-null rows are the only rows
    # that can form a meaningful candle.
    aggregation["_source_rows"] = "count"
    working["_source_rows"] = working["close"]

    origin, offset = _bucket_anchor(market=market, session_start=session_start)
    resampled = (
        working.resample(
            target.pandas_freq,
            label="left",
            closed="left",
            origin=origin,
            offset=offset,
        )
        .agg(aggregation)
        .dropna(subset=["open", "high", "low", "close"])
    )

    expected_rows = target.seconds // source.seconds
    resampled["is_complete"] = resampled["_source_rows"] >= expected_rows
    incomplete_rows = int((~resampled["is_complete"]).sum())
    if not include_incomplete:
        resampled = resampled[resampled["is_complete"]]

    result = resampled.drop(columns=["_source_rows"]).reset_index()
    stats = CandleBuildStats(
        source_timeframe=source.code,
        target_timeframe=target.code,
        input_rows=len(df),
        output_rows=len(result),
        incomplete_rows=incomplete_rows,
        expected_source_rows=expected_rows,
    )
    return CandleBuildResult(result, stats) if return_stats else result


def _normalize_passthrough(df: pd.DataFrame, timestamp_col: str) -> pd.DataFrame:
    """Return a sorted copy with UTC timestamps and canonical column order."""

    columns = [timestamp_col, "open", "high", "low", "close"]
    if "volume" in df.columns:
        columns.append("volume")

    result = df.loc[:, columns].copy()
    result[timestamp_col] = pd.to_datetime(result[timestamp_col], utc=True)
    result = result.sort_values(timestamp_col).dropna(
        subset=["open", "high", "low", "close"]
    )
    if timestamp_col != "timestamp":
        result = result.rename(columns={timestamp_col: "timestamp"})
    return result.reset_index(drop=True)


def _bucket_anchor(
    *, market: str, session_start: str | None
) -> tuple[str, pd.Timedelta | None]:
    """Translate market alignment options into pandas resample arguments."""

    normalized = market.lower()
    if normalized in {"24/7", "utc", "crypto"}:
        return "start_day", None
    if normalized != "session":
        raise ValueError("market must be '24/7' or 'session'")
    if not session_start:
        raise ValueError("session_start is required when market='session'")

    try:
        hour_text, minute_text = session_start.split(":", maxsplit=1)
        offset = pd.Timedelta(hours=int(hour_text), minutes=int(minute_text))
    except (TypeError, ValueError) as exc:
        raise ValueError("session_start must use HH:MM format, e.g. '09:30'") from exc

    return "start_day", offset
