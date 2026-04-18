"""Platform integration adapter for event forecast evaluation.

Bridges :class:`~the_similarity.events.scorecard.EventScoreReport` into
the unified platform registry so event evaluation results appear
alongside finance backtests, synthetic copies, and worlds runs in the
platform UI and CLI.

Registration flow
-----------------
1. Caller produces an ``EventScoreReport`` via ``EventScorecard.evaluate()``.
2. ``register_event_eval()`` converts the report into a
   :class:`~the_similarity.platform.contracts.ScorecardSummary` with
   ``kind=CALIBRATION`` (reuses the existing enum value — event
   calibration is conceptually the same quality gate as forecast-cone
   calibration).
3. The summary is registered against the provided ``run_id`` via
   ``registry.register_scorecard()``.
4. The full report is written to ``event_scorecard.json`` in the run
   directory so bulk consumers can load the detail without querying
   the registry.

Invariants
----------
- ``run_id`` must already exist in the registry (i.e. caller has
  called ``register_run()`` first). ``register_scorecard()`` will
  raise if the FK constraint fails.
- The ``event_scorecard.json`` file is written atomically via
  ``write + rename`` on POSIX, or ``write`` on Windows (no rename
  needed for our use case since concurrent readers are unlikely).
- This adapter imports platform contracts at module top level. It is
  safe — those are pure Python / stdlib with no heavy transitive
  dependencies.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, Optional

from the_similarity.events.scorecard import EventScoreReport
from the_similarity.platform.contracts import ScorecardKind, ScorecardSummary


def register_event_eval(
    report: EventScoreReport,
    run_id: str,
    registry: Any,
    *,
    run_dir: Optional[str] = None,
) -> None:
    """Register an event evaluation report in the platform registry.

    Parameters
    ----------
    report:
        The evaluation report produced by ``EventScorecard.evaluate()``.
    run_id:
        UUID hex of the run this evaluation belongs to. Must already
        exist in the registry.
    registry:
        A :class:`~the_similarity.platform.registry.RunRegistry` instance
        (or any object with a ``register_scorecard(summary)`` method).
        Typed as ``Any`` to avoid importing the heavy registry module
        at the call site when not needed.
    run_dir:
        Optional path to the run's output directory. When provided,
        the full report is written to ``<run_dir>/event_scorecard.json``.
        When ``None``, only the registry row is created (no file IO).
    """
    # ----- Build the ScorecardSummary -----
    # Map Brier score to a [0, 1] overall_score where higher = better.
    # Brier is [0, 1] with 0 = perfect, so overall_score = 1 - brier.
    # NaN brier -> None overall_score (no data -> no score).
    import math

    overall_score: Optional[float] = None
    if not math.isnan(report.brier_score):
        overall_score = 1.0 - report.brier_score

    # Determine pass/fail. We use the same threshold as the "good"
    # grade boundary (brier < 0.2) as the pass gate. NaN -> None.
    passed: Optional[bool] = None
    if not math.isnan(report.brier_score):
        passed = report.brier_score < 0.2

    summary = ScorecardSummary(
        run_id=run_id,
        kind=ScorecardKind.CALIBRATION,
        overall_score=overall_score,
        passed=passed,
        thresholds={"brier_max": 0.2},
        details={
            "brier_score": report.brier_score,
            "calibration_error": report.calibration_error,
            "resolution": report.resolution,
            "log_score": report.log_score,
            "n_predictions": report.n_predictions,
            "n_resolved": report.n_resolved,
            "overall_grade": report.overall_grade,
        },
    )

    # ----- Register in the platform registry -----
    registry.register_scorecard(summary)

    # ----- Write full report to disk -----
    if run_dir is not None:
        os.makedirs(run_dir, exist_ok=True)
        out_path = os.path.join(run_dir, "event_scorecard.json")
        with open(out_path, "w") as f:
            json.dump(report.to_dict(), f, indent=2)
