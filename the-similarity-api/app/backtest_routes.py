"""Backtest trigger API route — ``POST /platform/backtests``.

Purpose
-------
Allow triggering a walk-forward backtest directly from the API, rather
than requiring offline CLI usage. The endpoint:

1. Validates the requested symbol exists in the data catalog.
2. Creates the run synchronously (fast enough for MVP — typical backtest
   with 20 trials completes in <10 seconds).
3. Registers the result in the platform registry via the finance adapter.
4. Returns the run_id and status so the caller can fetch details later.

Design invariants
-----------------
- **Synchronous for MVP.** Async/queue execution can be layered later
  by swapping the inline call for a task submission. The contract (request
  body + response shape) does not change.
- **Data resolution.** The endpoint accepts a ``symbol`` string (e.g.
  ``"spy"``) and resolves it to the first matching catalog entry. If no
  match is found, 404 is returned before any compute starts.
- **n_trials is deliberately low (20).** API-triggered backtests target
  quick validation, not exhaustive sweeps. CLI users wanting 500 trials
  should use ``the_similarity.api.backtest()`` directly.
- **Error containment.** Backtest failures are caught and surfaced as a
  200 with ``status="failed"`` + error detail, not a 500. The run is
  still registered (as failed) so the registry tracks the attempt.
"""

from __future__ import annotations

import logging
import traceback
from typing import Optional

import numpy as np
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.data_service import load_catalog, load_series
from app.platform_routes import get_registry
from the_similarity.platform.registry import RunRegistry

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Router — mounted at /platform prefix in main.py
# ---------------------------------------------------------------------------

router = APIRouter(prefix="/platform", tags=["backtests"])


# ---------------------------------------------------------------------------
# Pydantic wire models
# ---------------------------------------------------------------------------


class BacktestRequest(BaseModel):
    """POST body for triggering a backtest.

    Fields mirror the key parameters of ``the_similarity.api.backtest()``.
    Only ``symbol``, ``window_size``, and ``forward_bars`` are required.
    """

    symbol: str = Field(
        ...,
        description=(
            "Symbol to backtest (e.g. 'spy', 'AAPL'). Case-insensitive. "
            "Must exist in the data catalog."
        ),
    )
    window_size: int = Field(
        ...,
        gt=5,
        le=500,
        description="Query window length in bars for each trial.",
    )
    forward_bars: int = Field(
        ...,
        gt=1,
        le=200,
        description="Number of bars to project forward after each match.",
    )
    seed: int = Field(
        42,
        description="Random seed for reproducibility.",
    )
    k_analogs: int = Field(
        6,
        gt=0,
        le=50,
        description="Number of analog matches per trial (top_k).",
    )
    n_trials: int = Field(
        20,
        gt=1,
        le=200,
        description=(
            "Number of random walk-forward trials. Kept low for API use; "
            "CLI users wanting exhaustive sweeps should use the engine directly."
        ),
    )


class BacktestResponse(BaseModel):
    """Response from a backtest trigger."""

    run_id: str = Field(..., description="Registry run_id for the backtest.")
    status: str = Field(
        ...,
        description="Run status: 'succeeded' or 'failed'.",
    )
    error: Optional[str] = Field(
        None,
        description="Error message if the backtest failed.",
    )
    summary: Optional[dict] = Field(
        None,
        description=(
            "Headline metrics (hit_rate, crps, coverage, etc.) "
            "when status='succeeded'."
        ),
    )


# ---------------------------------------------------------------------------
# Symbol resolution helper
# ---------------------------------------------------------------------------


def _resolve_symbol(symbol: str) -> str:
    """Resolve a symbol name to a dataset_id (``asset_class/symbol/timeframe``).

    Performs a case-insensitive match against the data catalog. Returns
    the first matching dataset_id, preferring daily (``1d``) timeframes.

    Raises:
        HTTPException 404 if the symbol is not in the catalog.
    """
    catalog = load_catalog()
    symbol_lower = symbol.lower()

    # Collect all matching entries, prefer 1d timeframe
    matches = [
        d for d in catalog if d["symbol"].lower() == symbol_lower
    ]
    if not matches:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Symbol '{symbol}' not found in data catalog.",
        )

    # Prefer daily timeframe if available
    daily = [d for d in matches if d["timeframe"] == "1d"]
    chosen = daily[0] if daily else matches[0]
    return f"{chosen['asset_class']}/{chosen['symbol']}/{chosen['timeframe']}"


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@router.post(
    "/backtests",
    response_model=BacktestResponse,
    status_code=status.HTTP_200_OK,
    responses={
        404: {"description": "Symbol not found in data catalog."},
        422: {"description": "Invalid parameters."},
    },
)
def trigger_backtest(
    body: BacktestRequest,
    registry: RunRegistry = Depends(get_registry),
) -> BacktestResponse:
    """Trigger a walk-forward backtest for a symbol.

    Runs synchronously — the backtest with default ``n_trials=20`` completes
    in seconds. The result is registered in the platform registry via
    :func:`~the_similarity.platform.adapters.finance.register_backtest_run`.

    Returns the ``run_id`` and headline metrics on success, or a ``status=failed``
    with error detail on failure.
    """
    # 1. Resolve the symbol to a dataset_id. Raises 404 if not found.
    dataset_id = _resolve_symbol(body.symbol)

    # 2. Load the price data as a numpy array.
    try:
        values, _dates = load_series(dataset_id, column="close")
        history = np.array(values, dtype=np.float64)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Failed to load data for '{body.symbol}': {exc}",
        ) from exc

    # 3. Run the backtest. Import lazily to keep module-level imports light
    #    (the backtester pulls numpy + the full method stack).
    try:
        from the_similarity.api import backtest as run_backtest

        report = run_backtest(
            history=history,
            window_size=body.window_size,
            forward_bars=body.forward_bars,
            n_trials=body.n_trials,
            seed=body.seed,
            top_k=body.k_analogs,
            # register=True + pass the registry so it writes to the
            # test-injected DB, not the default one.
            register=False,  # We register manually below for control.
        )
    except Exception as exc:
        # Backtest failed — register a failed run and return the error.
        logger.exception("Backtest failed for %s: %s", body.symbol, exc)
        from the_similarity.platform.adapters.finance import (
            register_backtest_run,
        )

        # Register a minimal failed run so the registry tracks the attempt.
        # Use 0.0 (not None) for numeric metrics because the trust adapter's
        # build_trust_artifact calls float() on them and None would raise.
        run_id = register_backtest_run(
            backtest_result={
                "hit_rate": 0.0,
                "crps": 0.0,
                "coverage": 0.0,
                "window_size": body.window_size,
                "forward_bars": body.forward_bars,
                "n_valid_trials": 0,
                "n_skipped_trials": 0,
            },
            config={
                "window_size": body.window_size,
                "forward_bars": body.forward_bars,
                "n_trials": body.n_trials,
                "top_k": body.k_analogs,
                "symbol": body.symbol,
                "status": "failed",
            },
            seed=body.seed,
            registry=registry,
            source_id=body.symbol,
        )
        return BacktestResponse(
            run_id=run_id,
            status="failed",
            error=str(exc),
        )

    # 4. Register the successful result.
    from the_similarity.platform.adapters.finance import register_backtest_run

    run_id = register_backtest_run(
        backtest_result=report,
        config={
            "window_size": body.window_size,
            "forward_bars": body.forward_bars,
            "n_trials": body.n_trials,
            "top_k": body.k_analogs,
            "symbol": body.symbol,
        },
        seed=body.seed,
        registry=registry,
        source_id=body.symbol,
    )

    # 5. Build summary from the report for the response.
    summary = {
        "hit_rate": getattr(report, "hit_rate", None),
        "mean_error": getattr(report, "mean_error", None),
        "crps": getattr(report, "crps", None),
        "coverage": getattr(report, "coverage", None),
        "n_valid_trials": getattr(report, "n_valid_trials", 0),
        "n_skipped_trials": getattr(report, "n_skipped_trials", 0),
    }

    return BacktestResponse(
        run_id=run_id,
        status="succeeded",
        summary=summary,
    )


__all__ = ["BacktestRequest", "BacktestResponse", "router"]
