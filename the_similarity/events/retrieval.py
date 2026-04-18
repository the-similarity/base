"""
Sliding-window analogue retrieval over historical event streams.

Given a set of *query* events (e.g. the last week's headlines), this module
finds the historical time window whose aggregate event profile is most similar.

Algorithm
---------
1. Compute the **centroid** of the query events' feature vectors (element-wise
   mean).
2. Slide a fixed-width window over the chronologically sorted historical
   events.
3. For each window position compute the centroid of the events inside the
   window and measure cosine similarity to the query centroid.
4. Return the top-*k* windows sorted by descending similarity.

This is intentionally a brute-force baseline.  For scale, swap the inner
loop for an approximate nearest-neighbour index on the window centroids.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Dict, List

import numpy as np

from the_similarity.events.features import FEATURE_DIM, extract_event_features


def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine similarity, safe for zero-norm vectors."""
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    if na == 0.0 or nb == 0.0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


def _compute_centroid(events: List[dict]) -> np.ndarray:
    """Mean feature vector across a list of event dicts.

    Returns a zero vector when *events* is empty.
    """
    if not events:
        return np.zeros(FEATURE_DIM, dtype=np.float64)
    vectors = np.array([extract_event_features(e) for e in events])
    return vectors.mean(axis=0)


def retrieve_analogues(
    query_events: List[dict],
    historical: List[dict],
    k: int = 5,
    window_days: int = 30,
) -> List[Dict]:
    """Find historical windows most similar to *query_events*.

    Parameters
    ----------
    query_events : list[dict]
        Recent events to match.  Each dict needs ``event_type`` and
        ``timestamp`` at minimum.
    historical : list[dict]
        Full historical event stream.  Same dict schema.
    k : int
        Number of top windows to return.
    window_days : int
        Width of the sliding window in calendar days.

    Returns
    -------
    list[dict]
        Each entry contains:
        - ``window_start`` (str) — ISO date of window start.
        - ``window_end`` (str) — ISO date of window end.
        - ``similarity`` (float) — cosine similarity to the query centroid.
        - ``events_in_window`` (list[dict]) — the raw event dicts inside the
          window.
        - ``outcomes`` (dict) — placeholder for downstream enrichment (empty
          dict for now).
    """
    if not query_events or not historical:
        return []

    query_centroid = _compute_centroid(query_events)

    # ── Sort historical events by timestamp ──────────────────────────
    sorted_hist = sorted(
        historical, key=lambda e: datetime.fromisoformat(e["timestamp"])
    )

    # ── Determine the overall time range ─────────────────────────────
    first_ts = datetime.fromisoformat(sorted_hist[0]["timestamp"])
    last_ts = datetime.fromisoformat(sorted_hist[-1]["timestamp"])
    window_delta = timedelta(days=window_days)

    # ── Slide the window with a 1-day step ───────────────────────────
    results: list[dict] = []
    current_start = first_ts
    while current_start + window_delta <= last_ts + timedelta(days=1):
        current_end = current_start + window_delta
        # Collect events falling inside [current_start, current_end).
        window_events = [
            e
            for e in sorted_hist
            if current_start
            <= datetime.fromisoformat(e["timestamp"])
            < current_end
        ]
        if window_events:
            centroid = _compute_centroid(window_events)
            sim = _cosine_similarity(query_centroid, centroid)
            results.append(
                {
                    "window_start": current_start.isoformat()[:10],
                    "window_end": current_end.isoformat()[:10],
                    "similarity": sim,
                    "events_in_window": window_events,
                    "outcomes": {},  # placeholder for downstream enrichment
                }
            )
        current_start += timedelta(days=1)

    # ── Sort by similarity descending, return top-k ──────────────────
    results.sort(key=lambda r: r["similarity"], reverse=True)
    return results[:k]
