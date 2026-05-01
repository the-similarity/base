"""Service-layer tests for the cross-timeframe ``/search`` branch.

The single-timeframe path is exercised end-to-end by the engine's own
test suite via ``the_similarity.search``; these tests cover the API
boundary added when ``request.timeframes`` is non-empty:

1. Empty ``timeframes`` keeps the legacy single-resolution behavior.
2. Non-empty ``timeframes`` actually routes through
   ``the_similarity.cross_timeframe_search`` (verified via monkeypatch).
3. ``history_dates`` validation returns 400 when missing or
   length-mismatched, instead of letting the engine raise an
   uninformative ValueError.

These are fast unit tests (no FastAPI TestClient round-trip required) —
``execute_search`` is a pure function over the contract object.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import numpy as np
import pytest
from fastapi import HTTPException

import the_similarity
from app.services import execute_search
from the_similarity.contracts.api import SearchRequest


def _synthetic_series(n: int = 800) -> tuple[list[float], list[str]]:
    """Reproducible price-like series + ISO-8601 minute timestamps.

    Returns lists (the contract uses ``list[float]`` and ``list[str]``)
    rather than numpy arrays so the SearchRequest validates without an
    extra conversion step in the test body.
    """
    rng = np.random.default_rng(0)
    values = (100.0 + np.cumsum(rng.standard_normal(n) * 0.1)).tolist()
    base = datetime(2024, 1, 1)
    dates = [(base + timedelta(minutes=i)).isoformat() for i in range(n)]
    return values, dates


def test_empty_timeframes_uses_single_resolution_search(monkeypatch):
    """``timeframes=[]`` is the default and must NOT trigger cross-tf."""
    values, _ = _synthetic_series()
    cross_called: list[bool] = []
    real_search = the_similarity.search

    def fake_cross(*_args, **_kwargs):
        cross_called.append(True)
        raise AssertionError("cross_timeframe_search should not be called")

    monkeypatch.setattr(the_similarity, "cross_timeframe_search", fake_cross)
    # Use the real single-tf engine — this test is mostly about routing.
    monkeypatch.setattr(the_similarity, "search", real_search)

    request = SearchRequest(
        query_values=values[100:160],
        history_values=values,
        top_k=3,
        forward_bars=10,
    )
    response = execute_search(request)

    assert cross_called == []
    assert response.matches  # the engine produced something


def test_non_empty_timeframes_routes_to_cross_timeframe(monkeypatch):
    """``timeframes`` set => the service must call cross_timeframe_search.

    We swap in a stub that returns an empty SearchResults so the test
    stays fast and deterministic. The assertion that matters is *which*
    engine entry point gets invoked and that the kwargs match what the
    contract promised.
    """
    from the_similarity.api import SearchResults

    values, dates = _synthetic_series()
    captured: dict = {}

    def fake_cross(query, history, timeframes, **kwargs):
        captured["timeframes"] = list(timeframes)
        captured["history_len"] = len(history.values)
        captured["history_has_dates"] = history.dates is not None
        captured["forward_bars"] = kwargs.get("forward_bars")
        captured["top_k"] = kwargs.get("top_k")
        return SearchResults(matches=[], query=np.asarray(query, dtype=np.float64))

    monkeypatch.setattr(the_similarity, "cross_timeframe_search", fake_cross)

    request = SearchRequest(
        query_values=values[100:160],
        history_values=values,
        history_dates=dates,
        timeframes=["5min", "15min", "1h"],
        top_k=5,
        forward_bars=20,
    )
    response = execute_search(request)

    assert captured["timeframes"] == ["5min", "15min", "1h"]
    assert captured["history_has_dates"] is True
    assert captured["history_len"] == len(values)
    assert captured["top_k"] == 5
    assert captured["forward_bars"] == 20
    # Empty SearchResults stub => empty matches in response.
    assert response.matches == []


def test_missing_history_dates_returns_400():
    values, _ = _synthetic_series()
    request = SearchRequest(
        query_values=values[100:160],
        history_values=values,
        timeframes=["5min"],
        # history_dates intentionally omitted
    )
    with pytest.raises(HTTPException) as exc:
        execute_search(request)
    assert exc.value.status_code == 400
    assert "history_dates" in exc.value.detail.lower()


def test_history_dates_length_mismatch_returns_400():
    values, dates = _synthetic_series()
    request = SearchRequest(
        query_values=values[100:160],
        history_values=values,
        history_dates=dates[:-5],  # off-by-five mismatch
        timeframes=["5min"],
    )
    with pytest.raises(HTTPException) as exc:
        execute_search(request)
    assert exc.value.status_code == 400
    assert "length" in exc.value.detail.lower()


def test_unparseable_history_dates_returns_400():
    values, dates = _synthetic_series()
    bad_dates = list(dates)
    bad_dates[10] = "not-a-real-iso-timestamp"
    request = SearchRequest(
        query_values=values[100:160],
        history_values=values,
        history_dates=bad_dates,
        timeframes=["5min"],
    )
    with pytest.raises(HTTPException) as exc:
        execute_search(request)
    assert exc.value.status_code == 400
    assert "history_dates" in exc.value.detail.lower()
