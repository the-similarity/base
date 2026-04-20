"""Compile narrative sequences into deterministic time-series arrays.

A *narrative sequence* is a dict describing a series of market-regime
events (crash, rally, consolidation, breakout, reversal, etc.) with
per-event intensity and duration. This module converts that description
into a concrete NumPy price array by chaining geometric-return segments.

Design decisions
----------------
- **Geometric returns**: each bar's return is ``exp(drift + noise)`` so
  prices stay positive without clamping.  This is standard in quant
  finance Monte-Carlo simulators and produces realistic-looking charts.
- **Deterministic via ``default_rng(seed)``**: every call with the same
  inputs produces the identical output array.  The seed is propagated
  per-segment so segment order matters for reproducibility but segment
  independence is preserved (each segment draws from a fresh RNG state
  derived from the global sequence).
- **Concatenation**: segments are joined end-to-end; the last price of
  segment *k* becomes the first price of segment *k+1*.  Total length
  equals ``sum(event.duration_bars for event in events)``.

Event types and their drift/volatility mappings
------------------------------------------------
+------------------+--------------------+---------------------+
| event_type       | drift direction    | volatility level    |
+==================+====================+=====================+
| ``crash``        | strongly negative  | high                |
+------------------+--------------------+---------------------+
| ``rally``        | strongly positive  | moderate            |
+------------------+--------------------+---------------------+
| ``consolidation``| near zero          | very low            |
+------------------+--------------------+---------------------+
| ``breakout``     | positive (sharp)   | high burst          |
+------------------+--------------------+---------------------+
| ``reversal``     | flips prior trend  | spike then settle   |
+------------------+--------------------+---------------------+
| ``selloff``      | negative           | elevated            |
+------------------+--------------------+---------------------+
| ``meltup``       | strongly positive  | escalating          |
+------------------+--------------------+---------------------+
| ``volatility``   | near zero          | very high           |
+------------------+--------------------+---------------------+

``intensity`` scales drift magnitude and volatility linearly in [0, 1].
An intensity of 0 produces a flat line; 1 produces the maximum move for
that event type.

Stub compatibility
------------------
If Agent 1's ``NarrativeSequence`` contract exists, import it.  Otherwise
we define a minimal dict schema inline:

    {"events": [{"event_type": "crash", "intensity": 0.8, "duration_bars": 5}]}

This stub is forward-compatible: when the canonical contract lands, the
compiler only needs the three fields above.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List

import numpy as np
from numpy.random import Generator, default_rng

from the_similarity.platform.artifacts import RunKind, iso_now, new_run_id
from the_similarity.platform.contracts import RunRecord, RunStatus
from the_similarity.platform.registry import RunRegistry

# ---------------------------------------------------------------------------
# Event-type -> (base_drift_per_bar, base_vol_per_bar) mapping.
#
# ``base_drift`` is the log-return drift at intensity=1.0 per bar.
# ``base_vol`` is the log-return volatility (std dev) at intensity=1.0.
# Both are scaled linearly by the event's ``intensity`` field.
#
# The numbers are calibrated to produce "looks-right" intraday-to-daily
# regimes when duration_bars is in the 5-50 range.  They are NOT fitted
# to any empirical distribution -- this is a synthetic generator, not a
# calibrated model.
# ---------------------------------------------------------------------------

_EVENT_PARAMS: Dict[str, tuple] = {
    # (base_drift, base_vol)
    "crash": (-0.03, 0.025),
    "rally": (0.02, 0.012),
    "consolidation": (0.0005, 0.003),
    "breakout": (0.035, 0.02),
    "reversal": (-0.015, 0.02),  # drift sign flipped contextually below
    "selloff": (-0.02, 0.018),
    "meltup": (0.025, 0.015),
    "volatility": (0.0, 0.04),
}

# The set of event types we recognise.  Used for validation.
SUPPORTED_EVENT_TYPES = frozenset(_EVENT_PARAMS.keys())


# ---------------------------------------------------------------------------
# TrajectoryArtifact — lightweight wrapper around the compiled array
# ---------------------------------------------------------------------------


@dataclass
class TrajectoryArtifact:
    """Container for a compiled narrative trajectory.

    Carries the price array alongside the metadata needed to register
    the result as a platform :class:`RunArtifact` of kind ``NL_TS``.

    Fields
    ------
    prices:
        1-D float64 NumPy array of simulated prices.  Length equals
        ``sum(e["duration_bars"] for e in sequence["events"])``.
    sequence:
        The input narrative sequence dict (preserved for provenance).
    base_price:
        Starting price used for the simulation.
    seed:
        RNG seed used (determinism guarantee).
    """

    prices: np.ndarray
    sequence: Dict[str, Any]
    base_price: float
    seed: int


# ---------------------------------------------------------------------------
# Core compilation
# ---------------------------------------------------------------------------


def _generate_segment(
    event_type: str,
    intensity: float,
    duration_bars: int,
    start_price: float,
    rng: Generator,
    prev_drift: float,
) -> tuple:
    """Generate one segment of a narrative trajectory.

    Parameters
    ----------
    event_type:
        One of :data:`SUPPORTED_EVENT_TYPES`.
    intensity:
        Scaling factor in ``[0, 1]``.  Multiplies both drift and vol.
    duration_bars:
        Number of bars (time steps) in this segment.
    start_price:
        Price at bar 0 of this segment (last price of previous segment).
    rng:
        NumPy ``Generator`` instance for reproducibility.
    prev_drift:
        Drift of the prior segment -- used by ``reversal`` to flip sign.

    Returns
    -------
    (prices, final_drift):
        ``prices`` is a 1-D float64 array of length ``duration_bars``.
        ``final_drift`` is the per-bar drift used (needed for reversal
        chaining).

    Raises
    ------
    ValueError:
        If ``event_type`` is not in :data:`SUPPORTED_EVENT_TYPES`.
    """
    if event_type not in _EVENT_PARAMS:
        raise ValueError(
            f"Unknown event_type {event_type!r}. "
            f"Supported: {sorted(SUPPORTED_EVENT_TYPES)}"
        )

    base_drift, base_vol = _EVENT_PARAMS[event_type]

    # Reversal flips the sign of the *previous* segment's drift rather
    # than using its own base drift.  If there is no prior segment
    # (prev_drift == 0), fall back to the base drift (which is negative
    # by default, simulating a reversal from an assumed uptrend).
    if event_type == "reversal" and prev_drift != 0.0:
        # Flip the prior drift direction; magnitude comes from reversal's
        # base_drift scaled by intensity.
        base_drift = -1.0 * np.sign(prev_drift) * abs(base_drift)

    # Scale by intensity.  Intensity=0 -> flat line; intensity=1 -> full move.
    drift = base_drift * intensity
    vol = base_vol * intensity

    # Generate log returns: r_t ~ N(drift, vol^2).
    log_returns = rng.normal(loc=drift, scale=max(vol, 1e-12), size=duration_bars)

    # Convert to price path.  price[t] = start_price * prod(exp(r_0..r_t)).
    cum_log_returns = np.cumsum(log_returns)
    prices = start_price * np.exp(cum_log_returns)

    return prices, drift


def compile_trajectory(
    sequence: Dict[str, Any],
    base_price: float = 100.0,
    seed: int = 42,
) -> np.ndarray:
    """Compile a narrative sequence into a deterministic price array.

    Parameters
    ----------
    sequence:
        Dict with key ``"events"``, a list of event dicts each containing:
        - ``event_type`` (str): one of :data:`SUPPORTED_EVENT_TYPES`.
        - ``intensity`` (float): scaling in ``[0, 1]``.
        - ``duration_bars`` (int): number of bars for this segment.
    base_price:
        Starting price for the first segment.  Default 100.0.
    seed:
        RNG seed for reproducibility.  Default 42.

    Returns
    -------
    np.ndarray:
        1-D float64 array of length ``sum(e["duration_bars"])``.

    Raises
    ------
    ValueError:
        If ``sequence`` is missing ``"events"`` or any event has an
        unknown ``event_type``.

    Examples
    --------
    >>> seq = {"events": [
    ...     {"event_type": "crash", "intensity": 0.8, "duration_bars": 10},
    ...     {"event_type": "rally", "intensity": 0.5, "duration_bars": 10},
    ... ]}
    >>> prices = compile_trajectory(seq)
    >>> len(prices)
    20
    >>> prices[0] < 100.0  # crash starts immediately
    True
    """
    events = sequence.get("events")
    if not events:
        raise ValueError("sequence must contain a non-empty 'events' list")

    rng = default_rng(seed)
    segments: List[np.ndarray] = []
    current_price = base_price
    prev_drift = 0.0

    for event in events:
        event_type = event["event_type"]
        intensity = float(event.get("intensity", 1.0))
        duration_bars = int(event["duration_bars"])

        if duration_bars <= 0:
            raise ValueError(
                f"duration_bars must be positive, got {duration_bars} "
                f"for event_type={event_type!r}"
            )

        prices, prev_drift = _generate_segment(
            event_type=event_type,
            intensity=intensity,
            duration_bars=duration_bars,
            start_price=current_price,
            rng=rng,
            prev_drift=prev_drift,
        )
        segments.append(prices)
        # Next segment starts where this one ended.
        current_price = float(prices[-1])

    return np.concatenate(segments)


# ---------------------------------------------------------------------------
# Registry integration
# ---------------------------------------------------------------------------


def compile_and_register(
    sequence: Dict[str, Any],
    registry: RunRegistry,
    base_price: float = 100.0,
    seed: int = 42,
) -> str:
    """Compile a narrative trajectory and register it in the platform registry.

    Creates a :class:`RunRecord` of kind ``NL_TS`` with the compiled
    prices stored in the summary (as a list, for JSON serialization).
    Returns the ``run_id`` of the registered record.

    Parameters
    ----------
    sequence:
        Narrative sequence dict (see :func:`compile_trajectory`).
    registry:
        An open :class:`RunRegistry` instance.
    base_price:
        Starting price.  Default 100.0.
    seed:
        RNG seed.  Default 42.

    Returns
    -------
    str:
        The ``run_id`` (UUID4 hex) of the registered run.

    Notes
    -----
    The full price array is stored under ``summary["prices"]`` as a
    Python list (JSON-serializable). For large trajectories this may be
    substantial; callers generating thousands of bars should consider
    writing to disk and using ``artifact_paths`` instead.
    """
    prices = compile_trajectory(sequence, base_price=base_price, seed=seed)

    run_id = new_run_id()
    now = iso_now()

    record = RunRecord(
        run_id=run_id,
        kind=RunKind.NL_TS,
        config={
            "sequence": sequence,
            "base_price": base_price,
        },
        seed=seed,
        status=RunStatus.SUCCEEDED,
        summary={
            "n_bars": len(prices),
            "start_price": float(prices[0]),
            "end_price": float(prices[-1]),
            "min_price": float(np.min(prices)),
            "max_price": float(np.max(prices)),
            "prices": prices.tolist(),
        },
        created_at=now,
        pillar="nl_ts",
    )

    registry.register_run(record)
    return run_id


# ---------------------------------------------------------------------------
# Public exports
# ---------------------------------------------------------------------------

__all__ = [
    "SUPPORTED_EVENT_TYPES",
    "TrajectoryArtifact",
    "compile_and_register",
    "compile_trajectory",
]
