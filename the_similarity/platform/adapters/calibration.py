"""Calibration artifact — per-percentile coverage analysis for finance runs.

This artifact reformats data already available in
``BacktestReport.calibration()``. It exists as a convenience for the
platform registry surface. If maintaining two representations becomes
a burden, delete this and read calibration directly from BacktestReport.

A :class:`CalibrationArtifact` captures the detailed calibration picture
for a backtest run: for each nominal percentile (e.g. P10, P25, P50,
P75, P90), what was the expected coverage, what was actually observed,
and how large is the error?

This is richer than the headline ``calibration_grade`` in the
:class:`~the_similarity.platform.adapters.trust.TrustArtifact` — it
exposes the full error curve so dashboards can plot calibration
reliability diagrams and analysts can spot systematic over-/under-
coverage at specific quantiles.

Serialization
-------------
:meth:`CalibrationArtifact.to_dict` / :meth:`CalibrationArtifact.from_dict`
provide JSON round-trip support. The canonical disk filename is
``calibration.json``, written alongside the run's ``artifact.json``
when registration is enabled.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List

from the_similarity.platform.artifacts import iso_now


# ---------------------------------------------------------------------------
# CalibrationArtifact
# ---------------------------------------------------------------------------


@dataclass
class CalibrationArtifact:
    """Detailed calibration analysis for a finance backtest run.

    Fields
    ------
    run_id:
        FK to the parent :class:`~the_similarity.platform.contracts.RunRecord`.
    percentiles:
        List of nominal percentile values analyzed (e.g. ``[10, 25, 50, 75, 90]``).
    expected_coverage:
        List of expected coverage rates, one per percentile. For percentile P,
        expected_coverage = P / 100. Length matches ``percentiles``.
    observed_coverage:
        List of observed (empirical) coverage rates from the backtest trials.
        Length matches ``percentiles``.
    calibration_errors:
        List of per-percentile absolute errors: ``|observed - expected|``.
        Length matches ``percentiles``.
    mean_calibration_error:
        Mean of ``calibration_errors`` — the headline calibration quality number.
    max_calibration_error:
        Worst-case single-percentile error — identifies the most problematic
        quantile.
    created_at:
        ISO-8601 UTC timestamp.
    """

    run_id: str
    percentiles: List[int]
    expected_coverage: List[float]
    observed_coverage: List[float]
    calibration_errors: List[float]
    mean_calibration_error: float
    max_calibration_error: float
    created_at: str

    # -- serialization --------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        """Return a JSON-safe dict — straight field pass-through."""
        return {
            "run_id": self.run_id,
            "percentiles": self.percentiles,
            "expected_coverage": self.expected_coverage,
            "observed_coverage": self.observed_coverage,
            "calibration_errors": self.calibration_errors,
            "mean_calibration_error": self.mean_calibration_error,
            "max_calibration_error": self.max_calibration_error,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "CalibrationArtifact":
        """Reconstruct from a JSON-decoded dict. Unknown keys ignored."""
        return cls(
            run_id=d["run_id"],
            percentiles=d["percentiles"],
            expected_coverage=d["expected_coverage"],
            observed_coverage=d["observed_coverage"],
            calibration_errors=d["calibration_errors"],
            mean_calibration_error=d["mean_calibration_error"],
            max_calibration_error=d["max_calibration_error"],
            created_at=d["created_at"],
        )


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def build_calibration_artifact(
    run_id: str,
    calibration: Dict[str, float],
) -> CalibrationArtifact:
    """Build a :class:`CalibrationArtifact` from per-percentile calibration data.

    Parameters
    ----------
    run_id:
        The run_id of the parent finance run.
    calibration:
        Map from percentile key (e.g. ``"10"``, ``"50"``, ``"90"``) to
        observed coverage rate. Keys must be numeric strings representing
        the percentile (0-100). Non-numeric keys are silently skipped.

    Returns
    -------
    CalibrationArtifact
        Fully populated artifact with computed error curves.
    """
    # Sort by percentile value for consistent ordering.
    sorted_items = []
    for p_str, observed in calibration.items():
        try:
            p_int = int(p_str)
        except (ValueError, TypeError):
            continue
        sorted_items.append((p_int, observed))
    sorted_items.sort(key=lambda x: x[0])

    percentiles = [p for p, _ in sorted_items]
    observed_coverage = [obs for _, obs in sorted_items]
    expected_coverage = [p / 100.0 for p in percentiles]
    calibration_errors = [
        abs(obs - exp) for obs, exp in zip(observed_coverage, expected_coverage)
    ]

    mean_error = (
        sum(calibration_errors) / len(calibration_errors) if calibration_errors else 0.0
    )
    max_error = max(calibration_errors) if calibration_errors else 0.0

    return CalibrationArtifact(
        run_id=run_id,
        percentiles=percentiles,
        expected_coverage=expected_coverage,
        observed_coverage=observed_coverage,
        calibration_errors=calibration_errors,
        mean_calibration_error=mean_error,
        max_calibration_error=max_error,
        created_at=iso_now(),
    )


__all__ = [
    "CalibrationArtifact",
    "build_calibration_artifact",
]
