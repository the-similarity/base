"""Personalized cross-instrument scanner — v1.

Scope
-----
Given a user-defined :class:`~the_similarity.platform.contracts.Setup`,
sweep the engine's :func:`the_similarity.core.matcher.find_matches` over
a fixed universe of liquid instruments (top crypto + FX majors + gold)
and return:

- per-instrument top-K analogs and a forecast cone, and
- a ranked top-N flat list across the entire universe.

The scanner orchestrates three pieces of existing engine code — it does
NOT reimplement them:

1. :func:`the_similarity.core.matcher.find_matches` — full tiered
   pipeline (SAX+MASS prefilter → DTW+Pearson → Tier-2 enrichment).
2. :func:`the_similarity.core.projector.project` — forward cone over
   weighted match continuations.
3. :class:`the_similarity.platform.registry.RunRegistry` — persistence
   under :attr:`RunKind.SETUP_SCAN`.

Lifecycle and concurrency
-------------------------
A single :func:`scan` call is a unit of work. The per-instrument loop
runs on a :class:`concurrent.futures.ThreadPoolExecutor` (default 6
workers) because the matcher releases the GIL on its dominant numpy /
scipy / dtaidistance kernels. Network calls into the data loader are
bounded by a 10-second timeout per fetch — when a fetch raises or times
out, that instrument's :class:`InstrumentScanResult` carries an
``error`` string and the scan continues for the rest of the universe
(partial-but-shipped beats blocked).

Mock-friendly
-------------
The default :func:`default_data_loader` hits Binance public REST for
crypto and degrades to a stub for FX/gold (Yahoo Finance via ``yfinance``
is not pinned in ``pyproject.toml`` at v1 — adding the dep is left to a
follow-up). Tests inject a deterministic loader via the ``data_loader``
parameter. Loaders are functions of signature::

    (instrument: str, timeframe: str, n_bars: int) -> np.ndarray

returning a 1D ``float64`` array of close prices. Loaders raise on
fetch failure and the scanner records the error per-instrument.

Persistence shape
-----------------
The full :class:`ScanResult` is JSON-serialized into the
:class:`RunRecord.summary` dict so the registry stays a single source of
truth without a side-channel artifact. ``user_id`` and ``setup_id`` go
into ``RunRecord.config`` so listing scans for one user or one setup is
a SQL filter on JSON-encoded TEXT — fine for the v1 corpus size, and
the indexes can be added later if scan volume grows.
"""

from __future__ import annotations

import concurrent.futures
import json
import logging
import time
import urllib.error
import urllib.request
from typing import Callable, Optional, Sequence

import numpy as np
from numpy.typing import NDArray

from the_similarity.config import Config
from the_similarity.core.matcher import find_matches
from the_similarity.core.projector import Forecast, project
from the_similarity.core.scorer import MatchResult
from the_similarity.platform.artifacts import RunKind, iso_now, new_run_id
from the_similarity.platform.contracts import (
    InstrumentScanResult,
    RunRecord,
    RunStatus,
    ScanResult,
    Setup,
)
from the_similarity.platform.registry import RunRegistry


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Universe — the v1 36-instrument set per ``vision/personalized_setup_scanner.md``.
#
# Crypto: top ~30 USDT-quoted Binance pairs by volume. We hardcode rather
# than hitting ``/api/v3/exchangeInfo`` at scan time because:
#   - the rank-by-volume call adds an extra HTTP hop per scan;
#   - the top-30 set is stable enough (months) that staleness isn't a
#     correctness problem;
#   - ``ssl`` / network egress in CI is unreliable.
# When a discovery refresh is needed, run
# ``python -m the_similarity.core.scanner --refresh-universe`` (TODO; not
# in v1).
#
# FX + gold: 6 majors + XAUUSD. Yahoo Finance via ``yfinance`` is the
# intended source but the dep is not in pyproject at ship time — the
# default data loader stubs FX/gold to a "not yet wired" error per the
# scanner's partial-success contract. The Setup contract is unaffected.
# ---------------------------------------------------------------------------

UNIVERSE_CRYPTO: tuple[str, ...] = (
    "BTCUSDT",
    "ETHUSDT",
    "BNBUSDT",
    "SOLUSDT",
    "XRPUSDT",
    "ADAUSDT",
    "DOGEUSDT",
    "AVAXUSDT",
    "TRXUSDT",
    "DOTUSDT",
    "LINKUSDT",
    "MATICUSDT",
    "TONUSDT",
    "SHIBUSDT",
    "LTCUSDT",
    "BCHUSDT",
    "ATOMUSDT",
    "UNIUSDT",
    "XLMUSDT",
    "ETCUSDT",
    "FILUSDT",
    "APTUSDT",
    "ARBUSDT",
    "OPUSDT",
    "NEARUSDT",
    "INJUSDT",
    "RNDRUSDT",
    "SUIUSDT",
    "PEPEUSDT",
    "SEIUSDT",
)

UNIVERSE_FX_GOLD: tuple[str, ...] = (
    "EURUSD",
    "GBPUSD",
    "USDJPY",
    "USDCHF",
    "AUDUSD",
    "USDCAD",
    "XAUUSD",
)

UNIVERSE_DEFAULT: tuple[str, ...] = UNIVERSE_CRYPTO + UNIVERSE_FX_GOLD
"""The full 37-symbol v1 universe (30 crypto + 7 FX/gold).

The vision doc rounds to ~36; the literal count is 37 because we kept
``XAUUSD`` plus the 6 FX majors plus 30 crypto. Per the partial-success
contract, missing data on any one symbol does not fail the scan.
"""


# ---------------------------------------------------------------------------
# Default data loader — public Binance REST + FX stub.
#
# The Binance v3 klines endpoint is documented at
# https://binance-docs.github.io/apidocs/spot/en/#kline-candlestick-data
# and is rate-limited by IP. We use stdlib ``urllib`` rather than the
# ``requests`` package because ``requests`` is not in pyproject.toml.
# A 10s socket timeout bounds the call.
# ---------------------------------------------------------------------------

# Maps the scanner's timeframe string to Binance's ``interval`` query
# param. We accept the most common retail timeframes; new ones are an
# additive change.
_BINANCE_INTERVAL_MAP: dict[str, str] = {
    "1m": "1m",
    "5m": "5m",
    "15m": "15m",
    "30m": "30m",
    "1h": "1h",
    "2h": "2h",
    "4h": "4h",
    "6h": "6h",
    "12h": "12h",
    "1d": "1d",
    "3d": "3d",
    "1w": "1w",
    "1M": "1M",
}

DEFAULT_HTTP_TIMEOUT_SECONDS = 10.0
"""Hard bound on each network fetch. Tuned to keep a 36-instrument scan
under a minute even in the worst case where every endpoint is slow."""


def default_data_loader(
    instrument: str,
    timeframe: str,
    n_bars: int,
) -> NDArray[np.float64]:
    """Fetch ``n_bars`` recent close prices for ``instrument`` at ``timeframe``.

    Crypto symbols (``BTCUSDT``, ``ETHUSDT``, ...) hit Binance v3 klines.
    FX / gold symbols raise :class:`NotImplementedError` — the v1 plan
    documents this gap; tests inject a custom loader for FX coverage and
    the API surface degrades gracefully via ``InstrumentScanResult.error``.

    Returns
    -------
    ``np.ndarray`` of shape ``(n_bars,)`` with ``float64`` close prices,
    chronologically ordered (oldest first).

    Raises
    ------
    ValueError:
        Unknown timeframe.
    urllib.error.URLError:
        Network failure (caller should catch and record per-instrument).
    NotImplementedError:
        FX/gold symbols at v1 (loader is a stub; inject a custom loader
        for tests + future Yahoo-Finance integration).
    """
    if timeframe not in _BINANCE_INTERVAL_MAP:
        raise ValueError(
            f"Unsupported timeframe {timeframe!r}; "
            f"expected one of {sorted(_BINANCE_INTERVAL_MAP)}"
        )

    if instrument in UNIVERSE_FX_GOLD:
        # FX + gold via Yahoo Finance is intended but the ``yfinance``
        # dep is not pinned at v1 ship time. Test loaders inject their
        # own coverage; production deployments either add yfinance or
        # accept the partial-success error message in the UI.
        raise NotImplementedError(
            f"FX/gold loader not wired in v1 default loader (instrument={instrument!r}). "
            "Inject a custom data_loader callable or upgrade pyproject.toml to "
            "include yfinance and extend default_data_loader to dispatch on it."
        )

    interval = _BINANCE_INTERVAL_MAP[timeframe]
    # Binance caps ``limit`` at 1000 per call. v1 setups expect well
    # under that — we clamp for safety and log a warning.
    limit = max(1, min(int(n_bars), 1000))
    url = (
        "https://api.binance.com/api/v3/klines"
        f"?symbol={instrument}&interval={interval}&limit={limit}"
    )
    # Use ``urllib`` (stdlib) rather than ``requests`` to keep the engine
    # dep-free. Klines responses are an array of arrays; index 4 is the
    # close price (string-encoded float).
    with urllib.request.urlopen(url, timeout=DEFAULT_HTTP_TIMEOUT_SECONDS) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    if not isinstance(payload, list) or len(payload) == 0:
        raise ValueError(
            f"Binance klines returned empty/invalid payload for {instrument} {timeframe}"
        )
    closes = np.array([float(row[4]) for row in payload], dtype=np.float64)
    return closes


# Type alias for the data loader callable. Tests inject deterministic
# fixtures via this signature without subclassing anything.
DataLoader = Callable[[str, str, int], NDArray[np.float64]]


# ---------------------------------------------------------------------------
# Per-instrument scan
# ---------------------------------------------------------------------------


def _serialize_match(match: MatchResult) -> dict:
    """Convert a :class:`MatchResult` to a JSON-safe dict.

    We deliberately drop the heavy diagnostic numpy arrays (Koopman
    eigenvalues, persistence diagram, alpha/beta transforms) — the API
    surface only needs the location, score, and breakdown for the v1
    UI. If the explainability surface needs them later, add a
    serialization toggle.

    ``forward_window`` is a small array (≤ ``forward_bars`` floats)
    and is preserved so the frontend can draw the analog's continuation.
    """
    bd = match.score_breakdown
    forward = match.forward_window
    return {
        "start_idx": int(match.start_idx),
        "end_idx": int(match.end_idx),
        "start_date": match.start_date,
        "end_date": match.end_date,
        "confidence_score": float(match.confidence_score),
        "score_breakdown": {
            "bempedelis_r2": float(bd.bempedelis_r2),
            "bempedelis_smoothness": float(bd.bempedelis_smoothness),
            "koopman": float(bd.koopman),
            "wavelet_spectrum": float(bd.wavelet_spectrum),
            "emd": float(bd.emd),
            "tda": float(bd.tda),
            "dtw": float(bd.dtw),
            "pearson_warped": float(bd.pearson_warped),
            "transfer_entropy": float(bd.transfer_entropy),
        },
        "regime": match.regime,
        "forward_window": forward.tolist() if forward is not None else None,
        "matched_series": (
            match.matched_series.tolist() if match.matched_series is not None else None
        ),
    }


def _serialize_forecast(forecast: Forecast) -> dict:
    """Convert a :class:`Forecast` to a JSON-safe dict.

    Drops ``all_paths`` (one path per match — quadratic on the wire)
    and ``koopman_forecast`` (engine-internal diagnostic). The cone's
    percentile curves are the headline output.
    """
    return {
        "bars": int(forecast.bars),
        "percentiles": list(forecast.percentiles),
        "curves": {
            str(p): forecast.curves[p].tolist()
            for p in forecast.percentiles
            if p in forecast.curves
        },
    }


def _scan_one_instrument(
    instrument: str,
    setup: Setup,
    config: Config,
    data_loader: DataLoader,
    history_bars: int,
    top_k: int,
    forward_bars: int,
) -> InstrumentScanResult:
    """Scan a single instrument; never raises — wraps errors into the result.

    The scanner's contract is "partial-but-shipped beats blocked". Any
    exception here (network timeout, bad data, engine failure) is caught
    and recorded as the per-instrument ``error`` field; the rest of the
    universe still gets scanned.
    """
    try:
        history = data_loader(instrument, setup.timeframe, history_bars)
        if history is None or len(history) < len(setup.region_series) + forward_bars:
            return InstrumentScanResult(
                instrument=instrument,
                error=(
                    f"insufficient history: got {0 if history is None else len(history)} bars, "
                    f"need >= {len(setup.region_series) + forward_bars}"
                ),
            )
        query = np.asarray(setup.region_series, dtype=np.float64)
        if query.size < 2:
            return InstrumentScanResult(
                instrument=instrument,
                error=f"setup region has fewer than 2 bars (got {query.size})",
            )
        matches = find_matches(
            query=query,
            history=np.asarray(history, dtype=np.float64),
            top_k=top_k,
            config=config,
        )
        if not matches:
            return InstrumentScanResult(
                instrument=instrument, analogs=[], forecast=None
            )

        forecast = project(
            matches=matches,
            history=np.asarray(history, dtype=np.float64),
            forward_bars=forward_bars,
            config=config,
        )
        return InstrumentScanResult(
            instrument=instrument,
            analogs=[_serialize_match(m) for m in matches],
            forecast=_serialize_forecast(forecast),
        )
    except Exception as exc:
        # Log at warning so the orchestrator sees the failure, but don't
        # propagate — the scan must continue across the rest of the
        # universe per the partial-success contract.
        logger.warning(
            "scanner: instrument=%s setup=%s failed: %s",
            instrument,
            setup.id,
            exc,
        )
        return InstrumentScanResult(instrument=instrument, error=str(exc))


# ---------------------------------------------------------------------------
# Top-level scan
# ---------------------------------------------------------------------------


def scan(
    setup: Setup,
    *,
    universe: Optional[Sequence[str]] = None,
    config: Optional[Config] = None,
    data_loader: Optional[DataLoader] = None,
    history_bars: int = 720,
    top_k: int = 5,
    top_n: int = 20,
    forward_bars: int = 50,
    max_workers: int = 6,
    registry: Optional[RunRegistry] = None,
) -> ScanResult:
    """Run a personalized cross-instrument scan.

    Parameters
    ----------
    setup:
        The user-defined query window. ``setup.region_series`` IS the
        query the matcher receives; ``setup.timeframe`` is forwarded to
        the data loader for each instrument.
    universe:
        Iterable of instrument symbols. Defaults to
        :data:`UNIVERSE_DEFAULT`.
    config:
        Engine config. Defaults to :class:`Config()` (all 9 methods
        active). For interactive UI dispatch, pass a config with
        ``stride`` and ``tier1_candidates`` tuned down — the default
        prioritizes recall over speed.
    data_loader:
        Callable ``(instrument, timeframe, n_bars) -> np.ndarray``.
        Defaults to :func:`default_data_loader` (Binance for crypto, FX
        unwired). Tests inject deterministic fixtures via this slot.
    history_bars:
        How many recent bars to pull per instrument. The matcher needs
        more history than the query window — defaults to 720 which is
        ~30 days of 1h bars or 24 hours of 1m bars.
    top_k:
        Top-K analogs per instrument. v1 product spec says 5 by default
        with a "show 15 more" reveal — the scanner returns top_k and
        the UI reveals.
    top_n:
        Top-N flat ranked across instruments (the cross-instrument
        leaderboard).
    forward_bars:
        Forecast horizon for the cone.
    max_workers:
        Thread pool size for parallel per-instrument scans. Default 6
        balances Binance rate-limits (~1200 req/min) against scan
        latency.
    registry:
        Optional :class:`RunRegistry`. When supplied, a
        :class:`RunRecord` of kind :attr:`RunKind.SETUP_SCAN` is
        registered with the full :class:`ScanResult` serialized into
        ``summary``.

    Returns
    -------
    :class:`ScanResult` with ``per_instrument`` and ``top_n`` filled.

    Notes
    -----
    The matcher releases the GIL on most heavy kernels, so the
    ThreadPoolExecutor parallelizes well even on CPython. We do NOT use
    ProcessPoolExecutor — pickling the engine config + numpy arrays adds
    measurable overhead on tiny windows and the GIL release is enough
    for v1 throughput.
    """
    if config is None:
        config = Config()
    if data_loader is None:
        data_loader = default_data_loader
    if universe is None:
        universe = UNIVERSE_DEFAULT
    universe_list = list(universe)
    if not universe_list:
        raise ValueError("universe must be non-empty")

    started_at = time.monotonic()
    created_at = iso_now()

    per_instrument: list[InstrumentScanResult] = []
    # ThreadPoolExecutor.submit + as_completed: faster wall-clock than
    # map() because slow instruments don't block the queue. We bound
    # ``max_workers`` to keep us under Binance's per-IP rate limit.
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(
                _scan_one_instrument,
                instrument,
                setup,
                config,
                data_loader,
                history_bars,
                top_k,
                forward_bars,
            ): instrument
            for instrument in universe_list
        }
        for fut in concurrent.futures.as_completed(futures):
            per_instrument.append(fut.result())

    # Re-order results to follow ``universe_list`` so callers see a
    # deterministic per-instrument array regardless of which thread
    # finished first. The completion order is arbitrary; the wire
    # contract is universe-order.
    by_symbol = {r.instrument: r for r in per_instrument}
    per_instrument_ordered = [
        by_symbol[sym] for sym in universe_list if sym in by_symbol
    ]

    # Build the flat top-N: extract every analog from every instrument,
    # tag it with its source symbol, and sort by confidence descending.
    flat: list[dict] = []
    for inst_result in per_instrument_ordered:
        for analog in inst_result.analogs:
            flat.append({**analog, "instrument": inst_result.instrument})
    flat.sort(key=lambda a: a.get("confidence_score", 0.0), reverse=True)
    top_n_list = flat[: max(0, int(top_n))]

    elapsed = time.monotonic() - started_at
    logger.info(
        "scanner: setup=%s universe=%d scanned in %.2fs (%d errors)",
        setup.id,
        len(universe_list),
        elapsed,
        sum(1 for r in per_instrument_ordered if r.error is not None),
    )

    result = ScanResult(
        setup_id=setup.id,
        user_id=setup.user_id,
        created_at=created_at,
        per_instrument=per_instrument_ordered,
        top_n=top_n_list,
        universe=universe_list,
    )

    # Optional registry persistence. The scanner is callable without a
    # registry (tests, ad-hoc CLI) — only when one is supplied do we
    # write a RunRecord.
    if registry is not None:
        run_id = new_run_id()
        record = RunRecord(
            run_id=run_id,
            kind=RunKind.SETUP_SCAN,
            config={
                "user_id": setup.user_id,
                "setup_id": setup.id,
                "instrument": setup.instrument,
                "timeframe": setup.timeframe,
                "history_bars": history_bars,
                "top_k": top_k,
                "top_n": top_n,
                "forward_bars": forward_bars,
                "universe": universe_list,
            },
            seed=None,
            summary=result.to_dict(),
            created_at=created_at,
            status=RunStatus.SUCCEEDED,
            pillar="finance",
            artifact_paths={},
            provenance={
                "generator_name": "the_similarity.core.scanner",
                "generator_version": "0.1.0",
                "created_at": created_at,
                "params": {
                    "max_workers": max_workers,
                    "elapsed_seconds": round(elapsed, 3),
                },
            },
        )
        registry.register_run(record)
        result.run_id = run_id

    return result


__all__ = [
    "DataLoader",
    "DEFAULT_HTTP_TIMEOUT_SECONDS",
    "UNIVERSE_CRYPTO",
    "UNIVERSE_DEFAULT",
    "UNIVERSE_FX_GOLD",
    "default_data_loader",
    "scan",
]
