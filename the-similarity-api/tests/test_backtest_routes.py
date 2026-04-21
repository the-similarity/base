"""Route-level tests for ``app.backtest_routes`` (POST /platform/backtests).

Every test uses a tmp-path SQLite registry injected via dependency override,
matching the pattern in ``test_platform_routes.py``. The actual backtest
engine call is mocked to avoid needing real price data in CI.

Coverage map
------------
- :func:`test_trigger_backtest_success` — happy path with mocked engine.
- :func:`test_trigger_backtest_symbol_not_found` — unknown symbol returns 404.
- :func:`test_trigger_backtest_invalid_params` — bad params return 422.
- :func:`test_trigger_backtest_engine_failure` — engine exception returns
  status=failed with error detail and registers a failed run.
- :func:`test_trigger_backtest_run_registered` — verifies the run appears
  in the registry after a successful trigger.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.platform_routes import get_registry
from the_similarity.platform.registry import RunRegistry


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    """TestClient with a tmp-path registry DB injected via dependency override.

    Mirrors the fixture in ``test_platform_routes.py`` so the override
    pattern is consistent across all API test modules.
    """
    db_path = tmp_path / "registry.db"

    def _override() -> Iterator[RunRegistry]:
        registry = RunRegistry(db_path)
        try:
            yield registry
        finally:
            registry.close()

    app.dependency_overrides[get_registry] = _override
    try:
        with TestClient(app) as tc:
            tc.db_path = db_path  # type: ignore[attr-defined]
            yield tc
    finally:
        app.dependency_overrides.pop(get_registry, None)


# ---------------------------------------------------------------------------
# Fake BacktestReport — mimics the shape used by the finance adapter
# ---------------------------------------------------------------------------


@dataclass
class _FakeBacktestReport:
    """Minimal stand-in for ``the_similarity.core.backtester.BacktestReport``.

    Provides the attributes the finance adapter's ``_coerce_report`` reads
    via ``getattr``, without pulling the real backtester (which needs numpy
    + the full method stack).
    """

    hit_rate: float = 0.65
    mean_error: float = 0.02
    crps: float = 0.15
    coverage: float = 0.80
    interval_score: float = 0.10
    profit_factor: float = 1.2
    max_drawdown: float = 0.05
    sharpe: float = 1.1
    n_valid_trials: int = 18
    n_skipped_trials: int = 2
    window_size: int = 50
    forward_bars: int = 20
    calibration: dict = field(default_factory=lambda: {10: 0.11, 50: 0.48, 90: 0.89})
    # The api.backtest() function sets these on the report.
    trials: list = field(default_factory=list)
    config: object = None
    seed: int = 42


# ---------------------------------------------------------------------------
# Mock helpers
# ---------------------------------------------------------------------------


def _mock_load_catalog():
    """Return a fake catalog with one entry for 'spy'."""
    return [
        {
            "asset_class": "equity",
            "symbol": "spy",
            "timeframe": "1d",
            "source": "test",
        }
    ]


def _mock_load_series(dataset_id: str, column: str = "close"):
    """Return fake price data — 200 points of synthetic close prices."""
    import numpy as np

    np.random.seed(42)
    values = np.cumsum(np.random.randn(200)).tolist()
    dates = [f"2025-01-{i:03d}" for i in range(200)]
    return values, dates


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestTriggerBacktest:
    """Tests for POST /platform/backtests."""

    @patch("app.backtest_routes.load_catalog", side_effect=_mock_load_catalog)
    @patch("app.backtest_routes.load_series", side_effect=_mock_load_series)
    @patch("the_similarity.api.backtest")
    def test_trigger_backtest_success(
        self,
        mock_backtest: MagicMock,
        mock_series: MagicMock,
        mock_catalog: MagicMock,
        client: TestClient,
    ):
        """Happy path: valid symbol + params -> succeeded response with run_id."""
        mock_backtest.return_value = _FakeBacktestReport()

        resp = client.post(
            "/platform/backtests",
            json={
                "symbol": "spy",
                "window_size": 50,
                "forward_bars": 20,
                "seed": 42,
                "k_analogs": 6,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "succeeded"
        assert "run_id" in data
        assert data["run_id"]  # non-empty
        assert data["summary"] is not None
        assert data["summary"]["hit_rate"] == 0.65
        assert data["error"] is None

    @patch("app.backtest_routes.load_catalog", return_value=[])
    def test_trigger_backtest_symbol_not_found(
        self,
        mock_catalog: MagicMock,
        client: TestClient,
    ):
        """Unknown symbol returns 404 with descriptive detail."""
        resp = client.post(
            "/platform/backtests",
            json={
                "symbol": "NONEXISTENT",
                "window_size": 50,
                "forward_bars": 20,
            },
        )
        assert resp.status_code == 404
        assert "NONEXISTENT" in resp.json()["detail"]

    def test_trigger_backtest_invalid_params(self, client: TestClient):
        """Invalid parameters (e.g. window_size=0) return 422."""
        resp = client.post(
            "/platform/backtests",
            json={
                "symbol": "spy",
                "window_size": 0,  # Must be > 5
                "forward_bars": 20,
            },
        )
        assert resp.status_code == 422

    def test_trigger_backtest_missing_required_field(self, client: TestClient):
        """Missing required fields return 422."""
        resp = client.post(
            "/platform/backtests",
            json={
                "symbol": "spy",
                # missing window_size and forward_bars
            },
        )
        assert resp.status_code == 422

    @patch("app.backtest_routes.load_catalog", side_effect=_mock_load_catalog)
    @patch("app.backtest_routes.load_series", side_effect=_mock_load_series)
    @patch("the_similarity.api.backtest", side_effect=ValueError("Insufficient data"))
    def test_trigger_backtest_engine_failure(
        self,
        mock_backtest: MagicMock,
        mock_series: MagicMock,
        mock_catalog: MagicMock,
        client: TestClient,
    ):
        """Engine failure returns status=failed with error detail."""
        resp = client.post(
            "/platform/backtests",
            json={
                "symbol": "spy",
                "window_size": 50,
                "forward_bars": 20,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "failed"
        assert "Insufficient data" in data["error"]
        assert data["run_id"]  # Still registered

    @patch("app.backtest_routes.load_catalog", side_effect=_mock_load_catalog)
    @patch("app.backtest_routes.load_series", side_effect=_mock_load_series)
    @patch("the_similarity.api.backtest")
    def test_trigger_backtest_run_registered(
        self,
        mock_backtest: MagicMock,
        mock_series: MagicMock,
        mock_catalog: MagicMock,
        client: TestClient,
    ):
        """Successful backtest creates a run visible in the registry."""
        mock_backtest.return_value = _FakeBacktestReport()

        # Trigger the backtest
        resp = client.post(
            "/platform/backtests",
            json={
                "symbol": "spy",
                "window_size": 50,
                "forward_bars": 20,
            },
        )
        run_id = resp.json()["run_id"]

        # Verify the run exists in the registry via the runs endpoint
        runs_resp = client.get("/platform/runs")
        assert runs_resp.status_code == 200
        run_ids = [r["run_id"] for r in runs_resp.json()]
        assert run_id in run_ids

    @patch("app.backtest_routes.load_catalog", side_effect=_mock_load_catalog)
    @patch("app.backtest_routes.load_series", side_effect=_mock_load_series)
    @patch("the_similarity.api.backtest")
    def test_trigger_backtest_case_insensitive_symbol(
        self,
        mock_backtest: MagicMock,
        mock_series: MagicMock,
        mock_catalog: MagicMock,
        client: TestClient,
    ):
        """Symbol matching is case-insensitive (SPY, spy, Spy all work)."""
        mock_backtest.return_value = _FakeBacktestReport()

        resp = client.post(
            "/platform/backtests",
            json={
                "symbol": "SPY",
                "window_size": 50,
                "forward_bars": 20,
            },
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "succeeded"

    @patch("app.backtest_routes.load_catalog", side_effect=_mock_load_catalog)
    @patch("app.backtest_routes.load_series", side_effect=_mock_load_series)
    @patch("the_similarity.api.backtest")
    def test_trigger_backtest_default_params(
        self,
        mock_backtest: MagicMock,
        mock_series: MagicMock,
        mock_catalog: MagicMock,
        client: TestClient,
    ):
        """Default k_analogs, seed, and n_trials are applied when omitted."""
        mock_backtest.return_value = _FakeBacktestReport()

        resp = client.post(
            "/platform/backtests",
            json={
                "symbol": "spy",
                "window_size": 50,
                "forward_bars": 20,
            },
        )
        assert resp.status_code == 200

        # Verify the backtest was called with defaults
        call_kwargs = mock_backtest.call_args
        assert call_kwargs.kwargs.get("seed", call_kwargs[1].get("seed")) == 42
        assert call_kwargs.kwargs.get("top_k", call_kwargs[1].get("top_k")) == 6
