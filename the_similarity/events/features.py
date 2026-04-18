"""
Event feature extraction — converts raw event dicts into fixed-length
numerical vectors suitable for cosine-similarity search.

Feature vector layout (14 dimensions total)
--------------------------------------------
Index  | Meaning
-------|-------------------------------------------------------
 0-7   | event_type one-hot  (8 categories, see EVENT_TYPES)
 8     | month-of-year sin   (sin(2π · month / 12))
 9     | month-of-year cos   (cos(2π · month / 12))
10     | day-of-week sin     (sin(2π · dow / 7))
11     | day-of-week cos     (cos(2π · dow / 7))
12     | impact magnitude    (clamped to [0, 1], 0 if missing)
13     | impact direction    (+1 up, -1 down, 0 unknown)
"""

from __future__ import annotations

import math
from datetime import datetime
from typing import Dict

import numpy as np

# ── Canonical event-type vocabulary ──────────────────────────────────────
# Order matters — index in this list == one-hot position.
EVENT_TYPES: list[str] = [
    "rate_decision",       # 0  — central-bank rate moves
    "economic_data",       # 1  — GDP, CPI, NFP, etc.
    "geopolitical",        # 2  — wars, sanctions, elections
    "earnings",            # 3  — corporate earnings releases
    "policy",              # 4  — fiscal policy, regulation
    "natural_disaster",    # 5  — earthquakes, hurricanes, pandemics
    "market_crash",        # 6  — flash crashes, circuit breakers
    "other",               # 7  — catch-all
]

FEATURE_DIM: int = 14  # total length of the output vector


def _parse_timestamp(ts: str) -> datetime:
    """Parse an ISO-8601 date or datetime string.

    Supports ``YYYY-MM-DD`` and ``YYYY-MM-DDTHH:MM:SS`` (with or without
    timezone offset).  Falls back to the stdlib ``fromisoformat`` parser.
    """
    return datetime.fromisoformat(ts)


def _one_hot_event_type(event_type: str) -> np.ndarray:
    """Return an 8-element one-hot vector for *event_type*.

    Unknown types are mapped to the ``other`` bucket (index 7).
    """
    vec = np.zeros(len(EVENT_TYPES), dtype=np.float64)
    try:
        idx = EVENT_TYPES.index(event_type)
    except ValueError:
        idx = EVENT_TYPES.index("other")
    vec[idx] = 1.0
    return vec


def _cyclical_encode(value: float, period: float) -> tuple[float, float]:
    """Encode a cyclical quantity as (sin, cos) pair.

    Parameters
    ----------
    value : float
        Current position in the cycle (e.g. month 1-12).
    period : float
        Full cycle length (e.g. 12 for months, 7 for weekdays).
    """
    angle = 2.0 * math.pi * value / period
    return math.sin(angle), math.cos(angle)


def extract_event_features(event: Dict) -> np.ndarray:
    """Convert a raw event dict into a fixed-length feature vector.

    Parameters
    ----------
    event : dict
        Must contain at least ``event_type`` (str) and ``timestamp`` (str,
        ISO-8601).  Optional keys:
        - ``impact_magnitude`` (float, 0-1 scale) — defaults to 0.
        - ``impact_direction`` (str, one of ``"up"``/``"down"``/``"unknown"``)
          — defaults to ``"unknown"`` (encoded as 0).

    Returns
    -------
    np.ndarray
        Float64 vector of length :data:`FEATURE_DIM` (14).
    """
    # ── event type one-hot (dims 0-7) ────────────────────────────────
    event_type = event.get("event_type", "other")
    one_hot = _one_hot_event_type(event_type)

    # ── temporal cyclical features (dims 8-11) ───────────────────────
    ts = _parse_timestamp(event["timestamp"])
    month_sin, month_cos = _cyclical_encode(ts.month, 12.0)
    dow_sin, dow_cos = _cyclical_encode(ts.weekday(), 7.0)  # Monday=0

    # ── impact features (dims 12-13) ─────────────────────────────────
    magnitude = float(event.get("impact_magnitude", 0.0))
    magnitude = max(0.0, min(1.0, magnitude))  # clamp to [0, 1]

    direction_str = event.get("impact_direction", "unknown")
    direction_map = {"up": 1.0, "down": -1.0, "unknown": 0.0}
    direction = direction_map.get(direction_str, 0.0)

    # ── assemble ─────────────────────────────────────────────────────
    vec = np.empty(FEATURE_DIM, dtype=np.float64)
    vec[0:8] = one_hot
    vec[8] = month_sin
    vec[9] = month_cos
    vec[10] = dow_sin
    vec[11] = dow_cos
    vec[12] = magnitude
    vec[13] = direction
    return vec
