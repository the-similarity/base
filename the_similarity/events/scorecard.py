"""Event forecast evaluation scorecard.

Evaluates binary event predictions (``predicted_probability`` vs
``resolved: bool``) using standard probabilistic scoring rules:

- **Brier score** — mean squared error of probability forecasts.
  Perfect = 0, coin-flip = 0.25, always-wrong = 1.
- **Log score** — mean log-likelihood. More sensitive to confident
  wrong predictions than Brier. Always negative (since ``log(p) < 0``
  for ``p < 1``).
- **Calibration** — binned comparison of predicted probability vs
  observed frequency. 10 equal-width bins from ``[0, 0.1)`` to
  ``[0.9, 1.0]``.
- **Resolution** — variance of predicted probabilities relative to the
  base rate. Higher resolution means the predictor is more decisive
  (not everyone gets the base-rate prediction).

Invariants
----------
- ``predictions`` and ``actuals`` are matched by ``question_id``. Only
  questions present in *both* lists contribute to the score.
- Probabilities are clamped to ``[eps, 1 - eps]`` (``eps = 1e-15``)
  before log scoring to avoid ``-inf``.
- Empty intersection -> all metrics are ``NaN`` and grade is ``"poor"``.

Usage
-----
::

    from the_similarity.events.scorecard import EventScorecard

    report = EventScorecard.evaluate(
        predictions=[{"question_id": "q1", "predicted_probability": 0.8}],
        actuals=[{"question_id": "q1", "resolved": True}],
    )
    print(report.brier_score, report.overall_grade)
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Clamp floor/ceiling for log scoring. Prevents -inf when a prediction
# is exactly 0 or 1 and the outcome disagrees. 1e-15 is small enough
# to have negligible impact on Brier/calibration but keeps log_score
# finite.
_EPS = 1e-15

# Number of calibration bins (equal-width from 0 to 1). 10 is the
# standard choice in the literature (Bröcker 2009, Niculescu-Mizil &
# Caruana 2005).
_N_BINS = 10

# Brier-score thresholds for overall_grade. These follow the general
# convention in forecasting literature:
#   < 0.1 : excellent (better than a well-calibrated base-rate model)
#   < 0.2 : good (useful signal above climatology)
#   < 0.3 : fair (marginal utility)
#   >= 0.3: poor (worse than a base-rate model or coin-flip)
_GRADE_THRESHOLDS = [
    (0.1, "excellent"),
    (0.2, "good"),
    (0.3, "fair"),
]


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class EventScoreReport:
    """Complete evaluation report for a set of event forecasts.

    All numeric fields are ``float``. ``NaN`` indicates insufficient
    data (no resolved questions matched). Consumers must handle ``NaN``
    explicitly — do not assume all fields are finite.

    Fields
    ------
    brier_score:
        Mean (predicted - actual)^2 across all resolved questions.
        Range: [0, 1]. Lower is better.
    calibration_bins:
        List of 10 dicts, one per equal-width bin:
        ``{"bin_lower": float, "bin_upper": float,
          "mean_predicted": float | None, "mean_actual": float | None,
          "count": int}``.
        ``mean_predicted`` / ``mean_actual`` are ``None`` when count=0.
    calibration_error:
        Mean absolute difference between ``mean_predicted`` and
        ``mean_actual`` across non-empty bins. Measures overall
        miscalibration. Lower is better.
    resolution:
        Variance of predicted probabilities around the base rate.
        Higher means the predictor differentiates well between
        likely and unlikely events. Range: [0, 0.25].
    log_score:
        Mean log-likelihood: ``mean(actual * log(p) + (1-a) * log(1-p))``.
        Always negative (a perfect predictor approaches 0 from below).
        More penalizing of confident wrong predictions than Brier.
    n_predictions:
        Total number of prediction entries supplied.
    n_resolved:
        Number of questions that had a matching actual outcome.
    overall_grade:
        Human-readable quality label: "excellent", "good", "fair", "poor".
    """

    brier_score: float
    calibration_bins: List[Dict[str, Any]]
    calibration_error: float
    resolution: float
    log_score: float
    n_predictions: int
    n_resolved: int
    overall_grade: str

    def to_dict(self) -> Dict[str, Any]:
        """JSON-safe dict representation.

        Uses ``dataclasses.asdict`` for a deep copy, which handles
        nested lists/dicts correctly. No enum coercion needed since
        all fields are primitives.
        """
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "EventScoreReport":
        """Reconstruct from a JSON-decoded dict.

        Tolerates extra keys (forward compat) by filtering to known
        field names. Missing keys raise ``TypeError`` on construction
        so callers get an immediate failure rather than a partial
        object.
        """
        known_fields = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in d.items() if k in known_fields}
        return cls(**filtered)


# ---------------------------------------------------------------------------
# Scorecard evaluator
# ---------------------------------------------------------------------------


class EventScorecard:
    """Stateless evaluator for binary event forecasts.

    All logic lives in the :meth:`evaluate` classmethod — no instance
    state is needed. The class exists as a namespace and extension
    point (future: configurable bin count, weighting schemes).
    """

    @classmethod
    def evaluate(
        cls,
        predictions: List[Dict[str, Any]],
        actuals: List[Dict[str, Any]],
    ) -> EventScoreReport:
        """Score a set of binary event predictions against outcomes.

        Parameters
        ----------
        predictions:
            List of ``{"question_id": str, "predicted_probability": float}``.
            Probabilities must be in ``[0, 1]``.
        actuals:
            List of ``{"question_id": str, "resolved": bool}``.

        Returns
        -------
        EventScoreReport
            Full evaluation report. All metrics are ``NaN`` and grade
            is ``"poor"`` when no predictions can be matched to actuals.
        """
        # ----- Match predictions to actuals by question_id -----
        # Build a lookup from question_id -> resolved (bool). Questions
        # that appear multiple times in actuals: last one wins (idempotent
        # re-resolution).
        actuals_map: Dict[str, bool] = {
            a["question_id"]: bool(a["resolved"]) for a in actuals
        }

        # Pair up: only keep predictions that have a matching actual.
        # Each pair is (predicted_probability, actual_int) where
        # actual_int is 0 or 1.
        pairs: List[tuple[float, int]] = []
        for pred in predictions:
            qid = pred["question_id"]
            if qid in actuals_map:
                p = float(pred["predicted_probability"])
                a = 1 if actuals_map[qid] else 0
                pairs.append((p, a))

        n_predictions = len(predictions)
        n_resolved = len(pairs)

        # ----- Edge case: no matched pairs -----
        if n_resolved == 0:
            return EventScoreReport(
                brier_score=float("nan"),
                calibration_bins=cls._empty_bins(),
                calibration_error=float("nan"),
                resolution=float("nan"),
                log_score=float("nan"),
                n_predictions=n_predictions,
                n_resolved=0,
                overall_grade="poor",
            )

        # ----- Brier score: mean (p - a)^2 -----
        brier = sum((p - a) ** 2 for p, a in pairs) / n_resolved

        # ----- Log score: mean log-likelihood -----
        # Clamp probabilities away from 0 and 1 to avoid log(0) = -inf.
        log_sum = 0.0
        for p, a in pairs:
            p_clamped = max(_EPS, min(1 - _EPS, p))
            # Log-likelihood for a single Bernoulli observation:
            #   a * log(p) + (1 - a) * log(1 - p)
            log_sum += a * math.log(p_clamped) + (1 - a) * math.log(1 - p_clamped)
        log_score = log_sum / n_resolved

        # ----- Resolution: var(predicted) relative to base rate -----
        # Resolution = (1/N) * sum((p_i - base_rate)^2)
        # This measures how much the predictor's probabilities spread
        # around the overall base rate. A predictor that always outputs
        # the base rate has resolution = 0.
        base_rate = sum(a for _, a in pairs) / n_resolved
        resolution = sum((p - base_rate) ** 2 for p, _ in pairs) / n_resolved

        # ----- Calibration bins -----
        bins = cls._compute_bins(pairs)
        calibration_error = cls._calibration_error(bins)

        # ----- Grade -----
        grade = cls._grade(brier)

        return EventScoreReport(
            brier_score=brier,
            calibration_bins=bins,
            calibration_error=calibration_error,
            resolution=resolution,
            log_score=log_score,
            n_predictions=n_predictions,
            n_resolved=n_resolved,
            overall_grade=grade,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_bins(
        pairs: List[tuple[float, int]],
    ) -> List[Dict[str, Any]]:
        """Group prediction-outcome pairs into 10 equal-width bins.

        Bin edges: [0, 0.1), [0.1, 0.2), ..., [0.9, 1.0].
        The last bin is closed on the right to include p=1.0 exactly.
        """
        # Initialize accumulators. Each bin tracks sum of predicted, sum
        # of actual, and count. Using lists (not dicts) for O(1) index.
        bin_pred_sums = [0.0] * _N_BINS
        bin_actual_sums = [0.0] * _N_BINS
        bin_counts = [0] * _N_BINS

        for p, a in pairs:
            # Determine bin index. For p in [0, 1], bin = floor(p * 10).
            # Clamp to [0, 9] to handle p=1.0 exactly.
            idx = min(int(p * _N_BINS), _N_BINS - 1)
            bin_pred_sums[idx] += p
            bin_actual_sums[idx] += a
            bin_counts[idx] += 1

        result: List[Dict[str, Any]] = []
        for i in range(_N_BINS):
            lower = i / _N_BINS
            upper = (i + 1) / _N_BINS
            count = bin_counts[i]
            if count > 0:
                mean_pred = bin_pred_sums[i] / count
                mean_actual = bin_actual_sums[i] / count
            else:
                mean_pred = None
                mean_actual = None
            result.append(
                {
                    "bin_lower": lower,
                    "bin_upper": upper,
                    "mean_predicted": mean_pred,
                    "mean_actual": mean_actual,
                    "count": count,
                }
            )
        return result

    @staticmethod
    def _calibration_error(bins: List[Dict[str, Any]]) -> float:
        """Mean absolute deviation between predicted and actual frequency.

        Only non-empty bins contribute. Returns ``NaN`` if all bins are
        empty (should not happen when n_resolved > 0).
        """
        total_error = 0.0
        n_nonempty = 0
        for b in bins:
            if b["count"] > 0:
                # Both mean_predicted and mean_actual are guaranteed
                # non-None when count > 0.
                total_error += abs(b["mean_predicted"] - b["mean_actual"])
                n_nonempty += 1
        if n_nonempty == 0:
            return float("nan")
        return total_error / n_nonempty

    @staticmethod
    def _grade(brier: float) -> str:
        """Map Brier score to a human-readable grade string."""
        for threshold, label in _GRADE_THRESHOLDS:
            if brier < threshold:
                return label
        return "poor"

    @staticmethod
    def _empty_bins() -> List[Dict[str, Any]]:
        """Return 10 empty calibration bins (count=0, means=None)."""
        return [
            {
                "bin_lower": i / _N_BINS,
                "bin_upper": (i + 1) / _N_BINS,
                "mean_predicted": None,
                "mean_actual": None,
                "count": 0,
            }
            for i in range(_N_BINS)
        ]


# ---------------------------------------------------------------------------
# Calibration curve helper
# ---------------------------------------------------------------------------


def calibration_curve(report: EventScoreReport) -> Dict[str, Any]:
    """Extract calibration data suitable for plotting.

    Returns a dict with two keys:

    - ``bins``: list of ``{"predicted": float, "actual": float, "count": int}``
      for each non-empty calibration bin. These are the points to plot.
    - ``ideal``: list of ``{"predicted": float, "actual": float}`` — the
      perfect-calibration diagonal (y = x), sampled at each non-empty
      bin's predicted value. Useful for overlaying a reference line.

    The caller (UI, notebook, CLI) can render this however they like;
    this function stays IO-free and framework-agnostic.
    """
    bins_data: List[Dict[str, Any]] = []
    ideal_data: List[Dict[str, Any]] = []

    for b in report.calibration_bins:
        if b["count"] > 0:
            pred = b["mean_predicted"]
            actual = b["mean_actual"]
            bins_data.append(
                {"predicted": pred, "actual": actual, "count": b["count"]}
            )
            # Ideal line: for every predicted probability, the actual
            # frequency should equal the predicted probability.
            ideal_data.append({"predicted": pred, "actual": pred})

    return {"bins": bins_data, "ideal": ideal_data}
