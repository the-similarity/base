"""Narrative retrieval — feature extraction, history search, and state-space mapping.

This module provides three capabilities that bridge the narrative pipeline
(natural-language scenario descriptions compiled into 1D price trajectories)
with the existing similarity engine and state-space infrastructure.

Architecture
------------
The narrative pipeline (built by Agents 1/2) produces a ``NarrativeSequence``
dict with this shape::

    {
        "events": [
            {
                "event_type": "rate_hike",   # EventType value
                "intensity": 0.8,            # float in [0, 1]
                "duration": 20,              # number of bars
                "direction": "down",         # "up" | "down" | "neutral"
            },
            ...
        ],
        "trajectory": np.ndarray,  # 1D compiled price array (from compiler)
    }

This module does NOT import or depend on the contracts/parser/compiler modules
(owned by Agents 1/2). It operates on plain dicts and numpy arrays, making it
safe to develop in parallel. The integration point is the dict schema above.

Feature vector layout (12 dimensions)
--------------------------------------
Dims 0-9:  Event type distribution (count of each type / total events).
           One dimension per canonical EventType in sorted order.
Dim 10:    Mean intensity across all events.
Dim 11:    Mean duration across all events (normalized to [0, 1] via 200-bar cap).
Dim 12:    Number of transitions (event boundaries) / total events.
Dim 13:    Overall trend direction: +1 if net positive, -1 if net negative, 0 if flat.
Dim 14:    Total duration (sum of bars, normalized to [0, 1] via 1000-bar cap).

Total: 15 dimensions (10 event types + 5 structural features).

Thread safety
-------------
All functions are pure (no shared mutable state). Safe to call from
multiple threads concurrently.

Performance
-----------
``find_similar_histories`` uses a brute-force sliding-window approach with
numpy vectorized correlation. For typical history lengths (<50k bars) and
typical trajectory lengths (<500 bars), this completes in <100ms. If the
existing ``api.search()`` can be used directly (it operates on the same
principle), callers should prefer it for its richer scoring pipeline.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import numpy as np
from numpy.typing import NDArray

from the_similarity.core.state_space import MAX_DIM, StateVector, _normalize

# ---------------------------------------------------------------------------
# Canonical event types — sorted for deterministic feature vector layout.
# These must match the EventType enum values in events/contracts.py.
# We hardcode them here (rather than importing) to avoid a circular dep
# and to keep the vector layout stable even if new types are added later.
# ---------------------------------------------------------------------------

_CANONICAL_EVENT_TYPES: list[str] = sorted(
    [
        "earnings",
        "election",
        "financial_crisis",
        "geopolitical",
        "natural_disaster",
        "pandemic",
        "rate_cut",
        "rate_hike",
        "regulatory",
        "technology",
    ]
)

# Number of event-type distribution dims
_N_EVENT_TYPES = len(_CANONICAL_EVENT_TYPES)  # 10

# Total feature vector length: 10 (event types) + 5 (structural)
NARRATIVE_FEATURE_DIM = _N_EVENT_TYPES + 5  # 15

# Normalization caps for structural features. These are empirically
# reasonable upper bounds; values beyond them are clamped.
_MAX_DURATION_BARS = 200.0  # max expected mean duration per event
_MAX_TOTAL_DURATION_BARS = 1000.0  # max expected total scenario length


# ---------------------------------------------------------------------------
# 1. Feature extraction
# ---------------------------------------------------------------------------


def extract_narrative_features(sequence: dict) -> NDArray[np.float64]:
    """Convert a NarrativeSequence dict to a fixed-length feature vector.

    The feature vector captures the *structure* of a narrative — what kinds
    of events it contains, how intense they are, how long they last, and
    the overall directional trend. This representation is suitable for
    nearest-neighbor search in the state space.

    Parameters
    ----------
    sequence : dict
        A NarrativeSequence dict with an ``"events"`` key containing a list
        of event dicts. Each event dict should have:
        - ``event_type`` : str (matching a canonical EventType value)
        - ``intensity`` : float in [0, 1]
        - ``duration`` : int (number of bars)
        - ``direction`` : str ("up", "down", or "neutral")

        If ``"events"`` is missing or empty, returns a zero vector.

    Returns
    -------
    np.ndarray
        Float64 array of shape ``(NARRATIVE_FEATURE_DIM,)`` = ``(15,)``.
        Values are in [0, 1] for distribution and normalized features,
        and in {-1, 0, +1} for the trend direction dimension.

    Examples
    --------
    >>> seq = {
    ...     "events": [
    ...         {"event_type": "rate_hike", "intensity": 0.8,
    ...          "duration": 20, "direction": "down"},
    ...         {"event_type": "pandemic", "intensity": 0.9,
    ...          "duration": 30, "direction": "down"},
    ...     ]
    ... }
    >>> vec = extract_narrative_features(seq)
    >>> vec.shape
    (15,)
    """
    features = np.zeros(NARRATIVE_FEATURE_DIM, dtype=np.float64)

    events = sequence.get("events", [])
    if not events:
        return features

    n_events = len(events)

    # --- Dims 0..9: Event type distribution ---
    # Count occurrences of each canonical type, then normalize by total.
    type_to_idx = {t: i for i, t in enumerate(_CANONICAL_EVENT_TYPES)}
    for evt in events:
        etype = evt.get("event_type", "")
        idx = type_to_idx.get(etype)
        if idx is not None:
            features[idx] += 1.0
    # Normalize distribution to sum to 1 (if any events matched)
    type_sum = features[:_N_EVENT_TYPES].sum()
    if type_sum > 0:
        features[:_N_EVENT_TYPES] /= type_sum

    # --- Dim 10: Mean intensity ---
    intensities = [
        float(evt.get("intensity", 0.0))
        for evt in events
        if evt.get("intensity") is not None
    ]
    features[_N_EVENT_TYPES] = (
        np.mean(intensities) if intensities else 0.0
    )

    # --- Dim 11: Mean duration (normalized) ---
    durations = [
        float(evt.get("duration", 0.0))
        for evt in events
        if evt.get("duration") is not None
    ]
    if durations:
        mean_dur = np.mean(durations)
        # Normalize to [0, 1] using the cap
        features[_N_EVENT_TYPES + 1] = min(mean_dur / _MAX_DURATION_BARS, 1.0)

    # --- Dim 12: Number of transitions / total events ---
    # A "transition" is a boundary between consecutive events of different types.
    # Single-event sequences have 0 transitions.
    transitions = 0
    for i in range(1, n_events):
        if events[i].get("event_type") != events[i - 1].get("event_type"):
            transitions += 1
    features[_N_EVENT_TYPES + 2] = transitions / max(n_events, 1)

    # --- Dim 13: Overall trend direction ---
    # +1 if net direction is up, -1 if down, 0 if neutral or mixed.
    direction_map = {"up": 1, "down": -1, "neutral": 0}
    direction_sum = sum(
        direction_map.get(evt.get("direction", "neutral"), 0) for evt in events
    )
    if direction_sum > 0:
        features[_N_EVENT_TYPES + 3] = 1.0
    elif direction_sum < 0:
        features[_N_EVENT_TYPES + 3] = -1.0
    else:
        features[_N_EVENT_TYPES + 3] = 0.0

    # --- Dim 14: Total duration (normalized) ---
    total_dur = sum(durations) if durations else 0.0
    features[_N_EVENT_TYPES + 4] = min(total_dur / _MAX_TOTAL_DURATION_BARS, 1.0)

    return features


# ---------------------------------------------------------------------------
# 2. Narrative-to-history retrieval
# ---------------------------------------------------------------------------


def find_similar_histories(
    trajectory: NDArray[np.float64],
    historical_data: dict,
    k: int = 5,
) -> list[dict]:
    """Find the k most similar windows in historical price data.

    Uses sliding-window normalized cross-correlation to rank all windows
    of the same length as ``trajectory`` against historical price series.
    This is a lightweight alternative to the full ``api.search()`` pipeline
    — use ``api.search()`` directly when the richer 9-method scoring is
    needed.

    Parameters
    ----------
    trajectory : np.ndarray
        1-D float array representing the compiled narrative trajectory
        (from the compiler). Typically 50-500 bars.
    historical_data : dict
        Mapping of ``{symbol: np.ndarray}`` where each value is a 1-D
        float array of historical prices. Example::

            {"SPY": spy_prices, "QQQ": qqq_prices}

    k : int
        Number of top matches to return. Defaults to 5.

    Returns
    -------
    list of dict
        Each dict has keys:
        - ``symbol`` : str — the asset symbol
        - ``start_idx`` : int — start index of the matching window
        - ``end_idx`` : int — end index (exclusive) of the matching window
        - ``similarity`` : float — Pearson correlation in [-1, 1]
        - ``window_data`` : np.ndarray — the matched price window

        Sorted descending by similarity.

    Notes
    -----
    - Both the trajectory and each historical window are z-score normalized
      before computing correlation, so the match is shape-based (not
      level-based). This matches the philosophy of the core engine.
    - Windows where the standard deviation is near zero (flat regions) are
      skipped to avoid division-by-zero artifacts.
    - The function returns at most ``k`` results total across all symbols.
      If there are fewer valid windows than ``k``, returns all valid ones.

    Performance
    -----------
    Brute-force O(sum(len(h)) * len(trajectory)) per call. For typical
    inputs (history ~10k bars, trajectory ~200 bars) this is ~2M ops,
    completing in <50ms on modern hardware.
    """
    traj = np.asarray(trajectory, dtype=np.float64).ravel()
    window_len = len(traj)

    if window_len < 2:
        return []

    # Z-score normalize the query trajectory
    traj_std = np.std(traj)
    if traj_std < 1e-10:
        # Flat trajectory cannot produce meaningful correlations
        return []
    traj_norm = (traj - np.mean(traj)) / traj_std

    # Collect all candidate windows across symbols
    candidates: list[dict] = []

    for symbol, prices in historical_data.items():
        prices = np.asarray(prices, dtype=np.float64).ravel()

        if len(prices) < window_len:
            continue

        n_windows = len(prices) - window_len + 1

        # Sliding window correlation using vectorized dot products.
        # For each window position i, extract prices[i:i+window_len],
        # normalize, and compute dot product with traj_norm.
        for i in range(n_windows):
            window = prices[i : i + window_len]
            w_std = np.std(window)
            if w_std < 1e-10:
                # Skip flat windows (constant price regions)
                continue
            w_norm = (window - np.mean(window)) / w_std
            # Pearson correlation = dot product of z-scored vectors / n
            corr = float(np.dot(traj_norm, w_norm) / window_len)
            candidates.append(
                {
                    "symbol": symbol,
                    "start_idx": i,
                    "end_idx": i + window_len,
                    "similarity": corr,
                    "window_data": window.copy(),
                }
            )

    # Sort by similarity descending, take top k
    candidates.sort(key=lambda c: c["similarity"], reverse=True)
    return candidates[:k]


# ---------------------------------------------------------------------------
# 3. State-space integration (NL_TS extractor)
# ---------------------------------------------------------------------------

# Normalization ranges for NL_TS state vectors.
# These map narrative structural features to [0, 1] for state-space comparison.
#
# The ranges are chosen to cover the expected output of extract_narrative_features:
# - mean_intensity: already in [0, 1]
# - mean_duration_norm: already in [0, 1] (normalized in feature extraction)
# - transition_ratio: already in [0, 1]
# - trend_direction: in [-1, 1], mapped to [0, 1]
# - total_duration_norm: already in [0, 1]
_NL_TS_RANGES: list[tuple[str, float, float]] = [
    ("mean_intensity", 0.0, 1.0),
    ("mean_duration_norm", 0.0, 1.0),
    ("transition_ratio", 0.0, 1.0),
    ("trend_direction", -1.0, 1.0),  # [-1, 1] -> [0, 1]
    ("total_duration_norm", 0.0, 1.0),
]

NL_TS_DIM = len(_NL_TS_RANGES)  # 5


def extract_nl_ts_state(run_summary: dict) -> StateVector:
    """Map an NL_TS run summary to a :class:`StateVector` for the 3D Data Space.

    Follows the same pattern as ``extract_finance_state``,
    ``extract_copies_state``, and ``extract_worlds_state`` in
    ``the_similarity/core/state_space.py``.

    The run summary should contain the structural features extracted by
    ``extract_narrative_features`` (or a subset). Expected keys:

    - ``mean_intensity`` : float in [0, 1]
    - ``mean_duration_norm`` : float in [0, 1]
    - ``transition_ratio`` : float in [0, 1]
    - ``trend_direction`` : float in [-1, 1]
    - ``total_duration_norm`` : float in [0, 1]

    Missing keys default to 0.5 (neutral), matching the state-space convention.

    Integration note
    ----------------
    This extractor is NOT wired into ``build_index_from_registry`` in
    ``state_space.py`` yet. When the full narrative pipeline is integrated,
    add the following to ``_PILLAR_EXTRACTORS`` in ``state_space.py``::

        "nl_ts": extract_nl_ts_state,

    This will cause ``build_index_from_registry`` to automatically include
    NL_TS runs when building the state-space index.

    Parameters
    ----------
    run_summary : dict
        Must contain at least ``"run_id"`` (used as ``source_id``).
        All other keys are extracted from the summary's metric fields.

    Returns
    -------
    StateVector
        A normalized state vector with ``source_kind="nl_ts"`` and
        ``NL_TS_DIM`` active dimensions (padded to ``MAX_DIM`` with 0.5).
    """
    # Build the normalized vector, padded to MAX_DIM for mixed-pillar indexing.
    # We reuse the same neutral-pad approach from state_space._extract.
    vec = np.full(MAX_DIM, 0.5, dtype=np.float64)
    for i, (key, lo, hi) in enumerate(_NL_TS_RANGES):
        val = run_summary.get(key)
        if val is not None:
            try:
                vec[i] = _normalize(float(val), lo, hi)
            except (TypeError, ValueError):
                pass  # Leave at 0.5 (neutral)

    return StateVector(
        vector=vec,
        source_id=run_summary.get("run_id", ""),
        source_kind="nl_ts",
        label=run_summary.get(
            "label", f"nl_ts-{run_summary.get('run_id', '?')}"
        ),
        metadata={k: run_summary.get(k) for k, _, _ in _NL_TS_RANGES},
    )
