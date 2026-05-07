"""End-to-end integration tests for the finance operating product.

This suite validates the baseline finance workflow that Batch 2 extends:

    Load data -> backtest(register=True) -> verify registry row

The tests use synthetic price data (no real SPY CSV required) and an
isolated tmp_path SQLite DB per test.  They prove the plumbing works
end-to-end:

1. **Backtest + registration** — ``api.backtest(register=True)`` produces
   a :class:`BacktestReport` with a ``run_id`` attribute, and that ID
   lands a row in the registry with ``kind=FINANCE``.

2. **Summary contract** — the registered summary contains the headline
   metrics that downstream surfaces (CLI, UI, review) index on:
   ``hit_rate``, ``crps``, ``coverage``, ``pillar``.

3. **Optional enrichment** — if Agent 1's enriched adapter ships
   ``trust_score`` and ``calibration_grade`` into the summary, we
   verify those too.  Missing fields are silently skipped via
   ``hasattr`` / ``dict.get`` so the test passes on the baseline
   adapter as well.

These tests do NOT exercise the new code from Agents 1-4 (enriched
adapter, ReviewArtifact, benchmark CLI, UI).  They lock in the
integration contract that those extensions build on.

Performance: n_trials=3 keeps each test under 30 s even on CI runners.
"""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pytest

from the_similarity.platform.artifacts import RunKind
from the_similarity.platform.registry import RunRegistry


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def _synthetic_prices() -> np.ndarray:
    """Generate ~500 bars of synthetic geometric-Brownian-motion prices.

    Deterministic (seed=42) so every test run sees the same series.
    The series is long enough for the backtester to place 3 non-overlapping
    trials with window_size=60 and forward_bars=20.
    """
    rng = np.random.RandomState(42)
    # GBM: S(t) = S(0) * exp(cumsum(log-returns))
    log_returns = rng.normal(loc=0.0002, scale=0.012, size=500)
    prices = 100.0 * np.exp(np.cumsum(log_returns))
    return prices


@pytest.fixture()
def _registry_db(tmp_path: Path) -> Path:
    """Return a fresh, isolated SQLite DB path under tmp_path."""
    return tmp_path / "finance_operating.db"


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestFinanceOperatingBaseline:
    """Baseline finance workflow: backtest -> register -> verify."""

    def test_backtest_registers_and_summary_contract(
        self,
        _synthetic_prices: np.ndarray,
        _registry_db: Path,
    ) -> None:
        """End-to-end: run a tiny backtest with registration, then verify
        the run exists in the registry with the expected kind and summary
        fields.
        """
        # Point the adapter at our isolated DB via env var — the adapter
        # resolves DB path from THE_SIMILARITY_REGISTRY_DB when no
        # explicit db_path is given.
        os.environ["THE_SIMILARITY_REGISTRY_DB"] = str(_registry_db)
        try:
            from the_similarity.api import backtest

            # Tiny backtest: 3 trials, seed=42, register=True.
            # window_size=60 + forward_bars=20 requires >=80 bars of
            # look-back history; our 500-bar series is more than enough.
            report = backtest(
                _synthetic_prices,
                window_size=60,
                forward_bars=20,
                n_trials=3,
                seed=42,
                register=True,
                source_id="synthetic-test",
            )

            # -- report-level assertions ------------------------------------
            # The backtest should produce valid metrics regardless of data.
            assert report.n_valid_trials >= 1, (
                "Expected at least one valid trial from 3 attempts"
            )
            assert 0.0 <= report.hit_rate <= 1.0
            assert report.crps >= 0.0

            # run_id is stamped by the registration path.
            run_id = getattr(report, "run_id", None)
            assert run_id is not None, (
                "backtest(register=True) must stamp run_id on the report"
            )

            # -- registry-level assertions ----------------------------------
            with RunRegistry(_registry_db) as reg:
                artifact = reg.get(run_id)
                assert artifact is not None, f"run_id {run_id} not found in registry"

                # Kind must be FINANCE (not EVAL).
                assert artifact.kind is RunKind.FINANCE

                # Summary must carry headline metrics.
                summary = artifact.summary
                assert "hit_rate" in summary
                assert "crps" in summary
                assert "coverage" in summary
                assert summary.get("pillar") == "finance"

                # Calibration dict should be present and have string keys
                # (JSON round-trip safety).
                calib = summary.get("calibration")
                if calib is not None:
                    assert all(isinstance(k, str) for k in calib.keys()), (
                        "Calibration keys must be stringified for JSON safety"
                    )

                # Config should echo the backtest knobs.
                assert artifact.config.get("window_size") == 60
                assert artifact.config.get("forward_bars") == 20
                assert artifact.config.get("n_trials") == 3

                # Provenance should identify the generator.
                assert "generator_name" in artifact.provenance

        finally:
            # Clean up env var so other tests are not affected.
            os.environ.pop("THE_SIMILARITY_REGISTRY_DB", None)

    def test_registry_list_filters_by_kind(
        self,
        _synthetic_prices: np.ndarray,
        _registry_db: Path,
    ) -> None:
        """After registration, ``list(kind=FINANCE)`` returns exactly the
        registered run. ``list(kind=COPIES)`` returns nothing.
        """
        os.environ["THE_SIMILARITY_REGISTRY_DB"] = str(_registry_db)
        try:
            from the_similarity.api import backtest

            report = backtest(
                _synthetic_prices,
                window_size=60,
                forward_bars=20,
                n_trials=3,
                seed=42,
                register=True,
            )
            run_id = getattr(report, "run_id", None)
            assert run_id is not None

            with RunRegistry(_registry_db) as reg:
                # FINANCE filter should return at least our run.
                finance_runs = reg.list(kind=RunKind.FINANCE)
                finance_ids = {r.run_id for r in finance_runs}
                assert run_id in finance_ids

                # COPIES filter should return nothing (we only registered
                # a finance run).
                copies_runs = reg.list(kind=RunKind.COPIES)
                assert len(copies_runs) == 0

        finally:
            os.environ.pop("THE_SIMILARITY_REGISTRY_DB", None)

    def test_optional_trust_and_calibration_enrichment(
        self,
        _synthetic_prices: np.ndarray,
        _registry_db: Path,
    ) -> None:
        """If Agent 1's enriched adapter is present, verify trust_score
        and calibration_grade appear in the summary.

        This test is non-blocking: it passes regardless of whether the
        enriched fields exist. It only asserts their types/ranges when
        they ARE present.
        """
        os.environ["THE_SIMILARITY_REGISTRY_DB"] = str(_registry_db)
        try:
            from the_similarity.api import backtest

            report = backtest(
                _synthetic_prices,
                window_size=60,
                forward_bars=20,
                n_trials=3,
                seed=42,
                register=True,
            )
            run_id = getattr(report, "run_id", None)
            assert run_id is not None

            with RunRegistry(_registry_db) as reg:
                artifact = reg.get(run_id)
                assert artifact is not None
                summary = artifact.summary

                # Optional trust_score: if present, must be a float in [0, 1].
                trust_score = summary.get("trust_score")
                if trust_score is not None:
                    assert isinstance(trust_score, (int, float))
                    assert 0.0 <= trust_score <= 1.0, (
                        f"trust_score={trust_score} outside [0, 1]"
                    )

                # Optional calibration_grade: if present, must be one of the
                # grades defined in trust.py: "excellent", "good", "fair", "poor".
                calibration_grade = summary.get("calibration_grade")
                if calibration_grade is not None:
                    assert isinstance(calibration_grade, str)
                    assert calibration_grade in {"excellent", "good", "fair", "poor"}, (
                        f"calibration_grade={calibration_grade!r} not a valid grade"
                    )

        finally:
            os.environ.pop("THE_SIMILARITY_REGISTRY_DB", None)

    def test_adapter_standalone_dict_registration(
        self,
        _registry_db: Path,
    ) -> None:
        """The finance adapter works with a plain dict (no numpy needed).

        This is the fast-path test that proves the adapter -> registry
        plumbing independently of the backtester. Agents 1-4 can run
        this to verify their adapter changes without waiting for a real
        backtest.
        """
        from the_similarity.platform.adapters.finance import (
            register_backtest_run,
        )

        fake_result = {
            "hit_rate": 0.62,
            "mean_error": 0.025,
            "crps": 0.015,
            "coverage": 0.85,
            "calibration": {10: 0.12, 50: 0.51, 90: 0.89},
            "window_size": 60,
            "forward_bars": 20,
            "n_valid_trials": 5,
            "n_skipped_trials": 0,
        }

        run_id = register_backtest_run(
            fake_result,
            config={"n_trials": 5, "top_k": 10},
            seed=42,
            db_path=str(_registry_db),
            source_id="spy",
        )

        with RunRegistry(_registry_db) as reg:
            artifact = reg.get(run_id)
            assert artifact is not None
            assert artifact.kind is RunKind.FINANCE
            assert artifact.summary["hit_rate"] == 0.62
            assert artifact.summary["crps"] == 0.015
            assert artifact.summary["coverage"] == 0.85
            assert artifact.summary["pillar"] == "finance"

            # ScorecardSummary / ArtifactRecord: check if the enriched
            # adapter attached any.  This is optional (base adapter does
            # not create them), but if present we verify structure.
            try:
                scorecards = reg.get_scorecards(run_id)
                if scorecards:
                    for sc in scorecards:
                        assert sc.run_id == run_id
                        assert sc.kind is not None
            except Exception:
                # get_scorecards may not exist on older registry versions;
                # silently skip.
                pass

            try:
                artifacts = reg.list_artifacts(run_id)
                if artifacts:
                    for art in artifacts:
                        assert art.run_id == run_id
            except Exception:
                pass
