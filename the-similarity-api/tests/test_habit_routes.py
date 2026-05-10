"""Tests for the Habitpulse forecast endpoint.

The endpoint is stateless and pure-compute, so these tests only need a
TestClient and a synthetic habit series. We verify:

1. Happy path: a 60-day series with structure returns analogues + a 7-day cone.
2. Validation: a series shorter than ``2 * window + forward_bars`` rejects.
3. Degenerate path: an all-ones series returns a flat cone with zero risk.
"""
from __future__ import annotations

import numpy as np
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _series(n: int = 60) -> list[float]:
    """Synthetic habit series with a weekly rhythm + occasional misses."""
    rng = np.random.default_rng(0)
    base = (np.arange(n) % 7 < 5).astype(float)  # M-F = done, weekend = miss
    noise = (rng.random(n) > 0.85).astype(float)  # 15% random misses
    return np.clip(base - noise, 0.0, 1.0).tolist()


def test_forecast_happy_path() -> None:
    body = {"series": _series(60), "window": 7, "forward_bars": 7, "top_k": 3}
    resp = client.post("/habit/forecast", json=body)
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert len(data["analogues"]) <= 3
    for a in data["analogues"]:
        assert a["end_idx"] > a["start_idx"]
        assert 0.0 <= a["score"] <= 100.0
        assert isinstance(a["forward"], list)

    assert len(data["cone"]["p10"]) == 7
    assert len(data["cone"]["p50"]) == 7
    assert len(data["cone"]["p75"]) == 7

    assert 0.0 <= data["relapse_risk"] <= 1.0


def test_forecast_rejects_short_series() -> None:
    body = {"series": [1.0] * 10, "window": 7, "forward_bars": 7}
    resp = client.post("/habit/forecast", json=body)
    assert resp.status_code == 422


def test_forecast_flat_series_returns_flat_cone() -> None:
    body = {"series": [1.0] * 60, "window": 7, "forward_bars": 7}
    resp = client.post("/habit/forecast", json=body)
    assert resp.status_code == 200
    data = resp.json()
    assert data["analogues"] == []
    assert data["cone"]["p50"] == [1.0] * 7
    assert data["relapse_risk"] == 0.0
