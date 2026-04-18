"""Tests for the event forecast evaluation scorecard.

Covers:
- Perfect predictor -> Brier ~0
- Random/coin-flip predictor -> Brier ~0.25
- Calibration bins sum to total predictions
- Log score is always negative
- Overall grade boundaries
- Calibration curve helper
- Round-trip serialization (to_dict / from_dict)
- Platform adapter integration
"""

from __future__ import annotations

import json
import math
import os
import tempfile
from unittest.mock import MagicMock

import pytest

from the_similarity.events.scorecard import (
    EventScorecard,
    EventScoreReport,
    calibration_curve,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _perfect_predictions(n: int = 100):
    """Generate predictions that perfectly match outcomes.

    Assigns probability 1.0 to events that resolve True and 0.0 to
    events that resolve False. 50/50 split.
    """
    predictions = []
    actuals = []
    for i in range(n):
        resolved = i % 2 == 0
        predictions.append(
            {
                "question_id": f"q{i}",
                "predicted_probability": 1.0 if resolved else 0.0,
            }
        )
        actuals.append({"question_id": f"q{i}", "resolved": resolved})
    return predictions, actuals


def _random_predictions(n: int = 1000, seed: int = 42):
    """Generate coin-flip predictions (all 0.5) with random outcomes.

    With p=0.5 for every question, Brier = mean((0.5 - a)^2) = 0.25
    regardless of the actual outcomes (since (0.5-0)^2 = (0.5-1)^2 = 0.25).
    """
    import random

    rng = random.Random(seed)
    predictions = []
    actuals = []
    for i in range(n):
        predictions.append(
            {"question_id": f"q{i}", "predicted_probability": 0.5}
        )
        actuals.append({"question_id": f"q{i}", "resolved": rng.random() > 0.5})
    return predictions, actuals


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestPerfectPredictor:
    """A predictor that assigns p=1 to True and p=0 to False."""

    def test_brier_score_near_zero(self):
        preds, actuals = _perfect_predictions()
        report = EventScorecard.evaluate(preds, actuals)
        assert report.brier_score == pytest.approx(0.0, abs=1e-10)

    def test_grade_excellent(self):
        preds, actuals = _perfect_predictions()
        report = EventScorecard.evaluate(preds, actuals)
        assert report.overall_grade == "excellent"

    def test_log_score_near_zero(self):
        """Perfect predictor's log score approaches 0 (from below)."""
        preds, actuals = _perfect_predictions()
        report = EventScorecard.evaluate(preds, actuals)
        # With clamping, log(1-eps) is very close to 0.
        assert report.log_score < 0
        assert report.log_score > -0.001


class TestRandomPredictor:
    """A predictor that always says 0.5 — the coin-flip baseline."""

    def test_brier_score_quarter(self):
        preds, actuals = _random_predictions()
        report = EventScorecard.evaluate(preds, actuals)
        # (0.5 - 0)^2 = (0.5 - 1)^2 = 0.25 for every question.
        assert report.brier_score == pytest.approx(0.25, abs=1e-10)

    def test_grade_fair(self):
        """Brier = 0.25 falls in the 'fair' bucket (0.2 <= b < 0.3)."""
        preds, actuals = _random_predictions()
        report = EventScorecard.evaluate(preds, actuals)
        assert report.overall_grade == "fair"


class TestCalibrationBins:
    """Calibration bin structure and invariants."""

    def test_bins_sum_to_total(self):
        """Sum of bin counts must equal n_resolved."""
        preds, actuals = _random_predictions(n=200)
        report = EventScorecard.evaluate(preds, actuals)
        total_in_bins = sum(b["count"] for b in report.calibration_bins)
        assert total_in_bins == report.n_resolved

    def test_ten_bins(self):
        preds, actuals = _perfect_predictions()
        report = EventScorecard.evaluate(preds, actuals)
        assert len(report.calibration_bins) == 10

    def test_bin_boundaries(self):
        """Each bin covers a 0.1-wide interval from 0 to 1."""
        preds, actuals = _perfect_predictions()
        report = EventScorecard.evaluate(preds, actuals)
        for i, b in enumerate(report.calibration_bins):
            assert b["bin_lower"] == pytest.approx(i / 10)
            assert b["bin_upper"] == pytest.approx((i + 1) / 10)


class TestLogScore:
    """Log score properties."""

    def test_log_score_is_negative(self):
        """Log of probabilities in (0, 1) is always negative."""
        preds, actuals = _random_predictions()
        report = EventScorecard.evaluate(preds, actuals)
        assert report.log_score < 0

    def test_confident_wrong_penalized(self):
        """A confident wrong prediction should yield a very negative log score."""
        # Predict 0.99 for something that resolves False.
        preds = [{"question_id": "q1", "predicted_probability": 0.99}]
        actuals = [{"question_id": "q1", "resolved": False}]
        report = EventScorecard.evaluate(preds, actuals)
        # log(1 - 0.99) = log(0.01) ~ -4.6
        assert report.log_score < -4.0


class TestGradeBoundaries:
    """Overall grade thresholds."""

    def test_excellent(self):
        # Brier < 0.1 -> excellent
        preds = [{"question_id": "q1", "predicted_probability": 0.95}]
        actuals = [{"question_id": "q1", "resolved": True}]
        report = EventScorecard.evaluate(preds, actuals)
        # Brier = (0.95 - 1)^2 = 0.0025
        assert report.overall_grade == "excellent"

    def test_good(self):
        # Brier in [0.1, 0.2) -> good
        # (0.65 - 1)^2 = 0.1225
        preds = [{"question_id": "q1", "predicted_probability": 0.65}]
        actuals = [{"question_id": "q1", "resolved": True}]
        report = EventScorecard.evaluate(preds, actuals)
        assert report.overall_grade == "good"

    def test_poor(self):
        # Brier >= 0.3 -> poor
        # (0.2 - 1)^2 = 0.64
        preds = [{"question_id": "q1", "predicted_probability": 0.2}]
        actuals = [{"question_id": "q1", "resolved": True}]
        report = EventScorecard.evaluate(preds, actuals)
        assert report.overall_grade == "poor"


class TestCalibrationCurve:
    """calibration_curve() helper."""

    def test_returns_bins_and_ideal(self):
        preds, actuals = _random_predictions(n=100)
        report = EventScorecard.evaluate(preds, actuals)
        result = calibration_curve(report)
        assert "bins" in result
        assert "ideal" in result

    def test_ideal_is_diagonal(self):
        """Each ideal point should have predicted == actual (y = x)."""
        preds, actuals = _random_predictions(n=100)
        report = EventScorecard.evaluate(preds, actuals)
        result = calibration_curve(report)
        for pt in result["ideal"]:
            assert pt["predicted"] == pt["actual"]

    def test_empty_bins_excluded(self):
        """Only non-empty bins appear in the curve data."""
        # All predictions are 0.5 -> only bin 5 has data.
        preds, actuals = _random_predictions(n=50)
        report = EventScorecard.evaluate(preds, actuals)
        result = calibration_curve(report)
        assert len(result["bins"]) == 1
        assert result["bins"][0]["count"] == 50


class TestSerialization:
    """Round-trip to_dict / from_dict."""

    def test_round_trip(self):
        preds, actuals = _perfect_predictions(n=20)
        original = EventScorecard.evaluate(preds, actuals)
        d = original.to_dict()
        # Ensure it's JSON-serializable
        json_str = json.dumps(d)
        restored = EventScoreReport.from_dict(json.loads(json_str))
        assert restored.brier_score == pytest.approx(original.brier_score)
        assert restored.overall_grade == original.overall_grade
        assert restored.n_resolved == original.n_resolved
        assert len(restored.calibration_bins) == len(original.calibration_bins)


class TestEdgeCases:
    """Edge cases and boundary conditions."""

    def test_no_matching_questions(self):
        """No overlap between predictions and actuals -> NaN metrics."""
        preds = [{"question_id": "a", "predicted_probability": 0.5}]
        actuals = [{"question_id": "b", "resolved": True}]
        report = EventScorecard.evaluate(preds, actuals)
        assert math.isnan(report.brier_score)
        assert math.isnan(report.log_score)
        assert report.n_resolved == 0
        assert report.overall_grade == "poor"

    def test_empty_inputs(self):
        report = EventScorecard.evaluate([], [])
        assert math.isnan(report.brier_score)
        assert report.n_predictions == 0
        assert report.n_resolved == 0


class TestEvalAdapter:
    """Platform integration via eval_adapter."""

    def test_register_event_eval(self):
        """Adapter creates a ScorecardSummary and calls registry."""
        from the_similarity.events.eval_adapter import register_event_eval

        preds, actuals = _perfect_predictions(n=10)
        report = EventScorecard.evaluate(preds, actuals)

        mock_registry = MagicMock()
        register_event_eval(report, run_id="test-run-123", registry=mock_registry)

        mock_registry.register_scorecard.assert_called_once()
        summary = mock_registry.register_scorecard.call_args[0][0]
        assert summary.run_id == "test-run-123"
        assert summary.kind.value == "calibration"
        assert summary.passed is True  # brier ~0 < 0.2

    def test_writes_json_to_run_dir(self):
        """Adapter writes event_scorecard.json when run_dir is provided."""
        from the_similarity.events.eval_adapter import register_event_eval

        preds, actuals = _perfect_predictions(n=10)
        report = EventScorecard.evaluate(preds, actuals)

        mock_registry = MagicMock()
        with tempfile.TemporaryDirectory() as tmpdir:
            register_event_eval(
                report,
                run_id="test-run-456",
                registry=mock_registry,
                run_dir=tmpdir,
            )
            out_path = os.path.join(tmpdir, "event_scorecard.json")
            assert os.path.exists(out_path)
            with open(out_path) as f:
                data = json.load(f)
            assert data["brier_score"] == pytest.approx(0.0, abs=1e-10)
