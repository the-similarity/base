"""Standardised baseline vs candidate delta computation.

Every autoresearch lane needs to answer the same question in a uniform
way:

    "Is the candidate's metric *meaningfully* different from the
    baseline's, and in which direction?"

Before this module each lane rolled its own convention. That's an
accountability problem: reviewers comparing two lanes' reports could
not tell whether "CRPS delta = -0.02" meant "better" or "worse"
without reading the lane's source. This module fixes that with an
explicit ``direction`` parameter on every delta.

Two layers are exposed:

1. :func:`compute_delta` — scalar (baseline, candidate, direction) →
   :class:`Delta` with signed raw delta and an ``is_improvement`` bool.
   Cheap, used when the lane only has aggregate scalars.
2. :func:`paired_bootstrap` — paired resampling over per-slice or
   per-trial observations. Returns a :class:`BootstrapResult` with a
   bootstrap-based p-value and 95% CI. Default ``n_resamples=1000`` and
   ``seed=42`` per the planning doc.

Implementation notes
--------------------
* The bootstrap is paired: the *i-th* baseline value is paired with the
  *i-th* candidate value, and each resample draws index positions with
  replacement — preserving correlation structure (e.g. same trial
  seed → same price path).
* ``n_resamples=1000`` is chosen because at this size the 95% CI on the
  bootstrap p-value is ~±1.5 percentage points, which is tight enough
  for a keep/discard gate but cheap enough to run inside a unit test.
* The direction literal is validated so typos become immediate
  ``ValueError`` rather than a silently-wrong decision.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Literal, Sequence


Direction = Literal["lower_is_better", "higher_is_better"]

_VALID_DIRECTIONS: frozenset[str] = frozenset({"lower_is_better", "higher_is_better"})


# ---------------------------------------------------------------------------
# Scalar delta
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Delta:
    """Scalar delta between a baseline and a candidate.

    ``raw_delta`` is always ``candidate - baseline``. ``is_improvement``
    respects the metric's preferred direction: for ``lower_is_better``
    metrics (CRPS, calibration error) an improvement is a negative raw
    delta; for ``higher_is_better`` metrics (hit rate, correlation) a
    positive raw delta.
    """

    baseline: float
    candidate: float
    direction: Direction
    raw_delta: float
    relative_delta: float | None
    is_improvement: bool


def _validate_direction(direction: str) -> None:
    if direction not in _VALID_DIRECTIONS:
        raise ValueError(
            f"direction must be one of {sorted(_VALID_DIRECTIONS)}; got {direction!r}"
        )


def compute_delta(baseline: float, candidate: float, *, direction: Direction) -> Delta:
    """Return a signed :class:`Delta` between the two scalars.

    ``relative_delta`` is ``raw_delta / baseline`` when the baseline is
    nonzero, else ``None``. This is the convention the projector-v2 lane
    already uses; keeping it stable lets existing reports migrate
    without changing their numerics.
    """
    _validate_direction(direction)
    raw = float(candidate) - float(baseline)
    rel: float | None
    if baseline != 0:
        rel = raw / float(baseline)
    else:
        rel = None
    is_improvement = raw < 0 if direction == "lower_is_better" else raw > 0
    return Delta(
        baseline=float(baseline),
        candidate=float(candidate),
        direction=direction,
        raw_delta=raw,
        relative_delta=rel,
        is_improvement=is_improvement,
    )


# ---------------------------------------------------------------------------
# Paired bootstrap
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BootstrapResult:
    """Output of :func:`paired_bootstrap`.

    ``p_value`` is a two-sided bootstrap p-value against the null that
    the paired difference distribution has zero mean. We compute it as
    2 × min(P(Δ̄_resampled ≤ 0), P(Δ̄_resampled ≥ 0)), clipped to [0, 1].

    ``significant`` is ``True`` iff ``p_value < alpha`` (default 0.05 at
    the caller). Exposing the p-value separately lets callers apply
    lane-specific alphas.
    """

    mean_delta: float
    ci_low: float
    ci_high: float
    p_value: float
    n_resamples: int
    significant: bool
    direction: Direction


def paired_bootstrap(
    baseline: Sequence[float],
    candidate: Sequence[float],
    *,
    direction: Direction,
    n_resamples: int = 1000,
    seed: int = 42,
    alpha: float = 0.05,
) -> BootstrapResult:
    """Paired bootstrap of the (candidate − baseline) per-observation delta.

    Arguments
    ---------
    baseline, candidate:
        Equal-length sequences of paired observations (one per slice /
        trial / fold). Mismatched lengths raise ``ValueError``.
    direction:
        Per-metric convention (see :data:`_VALID_DIRECTIONS`).
    n_resamples:
        Bootstrap budget. Default 1000 per the planning spec.
    seed:
        Deterministic seed. Default 42.
    alpha:
        Significance threshold for the convenience ``significant`` flag.

    Returns
    -------
    :class:`BootstrapResult` with the mean paired delta, 95% CI, and a
    two-sided bootstrap p-value.
    """
    _validate_direction(direction)
    if len(baseline) != len(candidate):
        raise ValueError(
            "baseline and candidate must have equal length; "
            f"got {len(baseline)} and {len(candidate)}"
        )
    n = len(baseline)
    if n == 0:
        raise ValueError("Cannot bootstrap zero observations")

    paired_diffs = [float(c) - float(b) for b, c in zip(baseline, candidate)]
    mean_delta = sum(paired_diffs) / n

    # If the paired diffs are all exactly zero the resamples are all
    # zero too — short-circuit to avoid doing 1k resamples that all
    # trivially produce the same sample mean.
    if all(d == 0.0 for d in paired_diffs):
        return BootstrapResult(
            mean_delta=0.0,
            ci_low=0.0,
            ci_high=0.0,
            p_value=1.0,
            n_resamples=n_resamples,
            significant=False,
            direction=direction,
        )

    rng = random.Random(seed)
    resampled_means: list[float] = []
    for _ in range(n_resamples):
        # Resample indices with replacement. ``rng.choices`` is ~2×
        # faster than a Python loop around ``randrange`` and is all
        # stdlib so no numpy dep is forced on downstream callers.
        idx = rng.choices(range(n), k=n)
        s = 0.0
        for i in idx:
            s += paired_diffs[i]
        resampled_means.append(s / n)

    resampled_means.sort()
    # 95% percentile CI.
    lo_idx = max(0, int(0.025 * n_resamples) - 1)
    hi_idx = min(n_resamples - 1, int(0.975 * n_resamples))
    ci_low = resampled_means[lo_idx]
    ci_high = resampled_means[hi_idx]

    # Two-sided bootstrap p-value. Fraction of resamples on the
    # "wrong side" of zero, doubled, clipped to [0, 1].
    n_le_zero = sum(1 for m in resampled_means if m <= 0)
    n_ge_zero = sum(1 for m in resampled_means if m >= 0)
    p_two_sided = 2.0 * min(n_le_zero, n_ge_zero) / n_resamples
    p_two_sided = max(0.0, min(1.0, p_two_sided))

    return BootstrapResult(
        mean_delta=mean_delta,
        ci_low=ci_low,
        ci_high=ci_high,
        p_value=p_two_sided,
        n_resamples=n_resamples,
        significant=p_two_sided < alpha,
        direction=direction,
    )


# ---------------------------------------------------------------------------
# Convenience: build a full delta table from two metric dicts
# ---------------------------------------------------------------------------


def delta_table(
    baseline_metrics: dict[str, float],
    candidate_metrics: dict[str, float],
    *,
    directions: dict[str, Direction],
) -> dict[str, Delta]:
    """Compute a :class:`Delta` for every metric the caller lists in ``directions``.

    Silently skips metrics absent from either side. This is the primary
    entry point the canonical report uses — it guarantees a metric
    never appears in the delta section with an unknown direction.
    """
    table: dict[str, Delta] = {}
    for metric, direction in directions.items():
        if metric not in baseline_metrics or metric not in candidate_metrics:
            continue
        table[metric] = compute_delta(
            float(baseline_metrics[metric]),
            float(candidate_metrics[metric]),
            direction=direction,
        )
    return table


__all__ = [
    "Direction",
    "Delta",
    "BootstrapResult",
    "compute_delta",
    "paired_bootstrap",
    "delta_table",
]
