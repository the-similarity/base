"""Event forecast evaluation — scorecard, calibration, and platform integration.

This package provides probabilistic forecast scoring for binary event
questions (e.g. "Will X happen by date Y?"). The primary entrypoint is
:class:`~the_similarity.events.scorecard.EventScorecard`, which computes
Brier scores, calibration diagnostics, resolution, and log-likelihood
from a set of predicted probabilities and observed outcomes.

Modules
-------
scorecard
    Core evaluation logic: ``EventScorecard.evaluate()`` -> ``EventScoreReport``.
eval_adapter
    Platform integration: register an ``EventScoreReport`` as a
    :class:`~the_similarity.platform.contracts.ScorecardSummary` in the
    unified registry.
"""
