"""Stooq daily OHLCV fetcher.

This module wraps the public Stooq CSV endpoint (https://stooq.com/q/d/l/) and
normalizes its payload into the project's canonical OHLCV frame. Two real-world
quirks justify the extra exception surface in this file:

1. Stooq silently gates heavy users behind an API key. When the limit is hit the
   endpoint stops returning CSV data and instead returns a human-readable
   "Get your apikey:" instructions page with a 200 status code. Raising a
   dedicated :class:`StooqApiKeyMissing` lets the refresh pipeline surface a
   clear, actionable error instead of an opaque CSV parse failure.
2. Stooq occasionally returns an HTML error page (e.g. during upstream
   outages) with a 200 status. We detect that and raise ``ValueError`` so the
   pipeline retries/reports correctly rather than storing garbage rows.

Invariants
----------
* :class:`StooqDailyFetcher` is stateless — instances are safe to reuse and to
  share across threads. The only mutable state lives on the ``requests``
  ``Response`` we create per call.
* ``STOOQ_APIKEY`` is read from the environment on every call (not cached) so
  credential rotation takes effect immediately without process restarts.
* The ``apikey`` query parameter is only attached when the env var is set and
  non-empty; sending an empty apikey to Stooq is treated by the upstream as an
  invalid key.
"""

from __future__ import annotations

import os
from io import StringIO

import pandas as pd
import requests

from the_similarity_data.models import DatasetSpec
from the_similarity_data.normalize import canonicalize_ohlcv_frame


# Sentinel substring that Stooq embeds in its "please authenticate" HTML/text
# response. Stooq returns HTTP 200 in this case so we cannot rely on the status
# code — we have to sniff the body. The check is case-sensitive because the
# upstream string is stable ("Get your apikey:" exactly).
_APIKEY_PROMPT_MARKER = "Get your apikey"


class StooqApiKeyMissing(RuntimeError):
    """Raised when Stooq returns its "Get your apikey" prompt instead of data.

    This typically means the caller hit the anonymous rate limit and Stooq is
    asking for a (free) API key. The refresh pipeline catches this separately
    from generic ``ValueError`` so it can log an actionable message pointing
    operators at ``STOOQ_APIKEY``.
    """


class StooqDailyFetcher:
    """Fetch daily OHLCV bars from Stooq and normalize them.

    Lifecycle
    ---------
    Stateless. Construct once, call :meth:`fetch` many times. Safe to call from
    multiple threads because no instance attributes are mutated.
    """

    def fetch(self, spec: DatasetSpec) -> pd.DataFrame:
        if spec.timeframe != "1d":
            raise ValueError("StooqDailyFetcher only supports 1d datasets")

        # Build the query params. We always send the symbol + interval, and we
        # conditionally append ``apikey`` so unauthenticated callers keep the
        # original (keyless) request shape. The env lookup happens per-call so
        # credential rotation propagates immediately.
        params: dict[str, str] = {"s": spec.source_symbol, "i": "d"}
        apikey = os.getenv("STOOQ_APIKEY")
        if apikey:
            params["apikey"] = apikey

        response = requests.get(
            "https://stooq.com/q/d/l/",
            params=params,
            timeout=30,
        )
        response.raise_for_status()

        text = response.text

        # Stooq returns HTTP 200 with a "Get your apikey:" instruction page
        # when the anonymous rate limit has been exceeded. Detect that *before*
        # trying to parse as CSV so operators get a clear, actionable error
        # instead of an opaque pandas parse failure.
        if _APIKEY_PROMPT_MARKER in text:
            raise StooqApiKeyMissing(
                f"Stooq requires an API key for {spec.source_symbol}; "
                "set STOOQ_APIKEY in the environment"
            )

        # A well-formed Stooq CSV response always starts with the "Date,"
        # header row. Anything else (typically an HTML error page returned
        # with a 200 status during upstream incidents) should surface as a
        # structured error rather than silently producing an empty frame.
        stripped = text.lstrip()
        if not stripped.startswith("Date,"):
            # Preserve the legacy "No data" sentinel — Stooq sometimes echoes
            # literal "No data" text for unknown symbols and we still want that
            # to read as "no rows returned" rather than a transport failure.
            if "No data" in text:
                raise ValueError(f"No OHLCV data returned for {spec.symbol} {spec.timeframe}")
            raise ValueError(
                f"Unexpected Stooq response format for {spec.source_symbol}: "
                f"expected CSV header, got {stripped[:40]!r}"
            )

        frame = pd.read_csv(StringIO(text))
        if frame.empty:
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
