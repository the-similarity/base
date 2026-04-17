"""Privacy scorecard for synthetic time-series datasets.

Implements :class:`PrivacyScorecard`, which satisfies
:class:`~the_similarity.synthetic.contracts.ScorecardProtocol`. Three cheap,
attack-free diagnostics are computed and aggregated into an overall risk
score:

1. **Nearest-neighbour leakage (DCR)** — for every synthetic row, measure the
   minimum L2 distance to the real set (Distance to Closest Record). Compare
   the low-tail of that distribution against a real-vs-real baseline. If the
   synth-to-real 5th percentile is much smaller than the real-to-real 5th
   percentile, synthetic samples are sitting suspiciously close to real
   records.
2. **Memorization** — count exact and near-exact duplicates between the two
   sets (L2 < eps). A handful of exact copies is an outright leak; a high
   near-dupe fraction suggests the generator has overfit.
3. **Membership inference proxy** — a shadow-model-free surrogate. Split the
   real set into "members" (first half, treated as training seen by the
   generator) and "non-members" (second half). For each real row, use its
   minimum distance to the synthetic set as a one-dimensional score. A k-NN
   classifier trained on that single feature is overkill — the feature alone
   is a proper real-valued score, so we compute ROC-AUC directly against the
   membership labels. AUC > 0.5 means distance-to-synth discriminates
   members, i.e. the generator leaked training identity.

Design choices
--------------
- All three metrics operate on flat ``(n_samples, n_features)`` matrices. Row
  semantics (timestep vs. sequence) are the caller's concern; we just
  treat every row as an independent point. This keeps the attacks O(NM) and
  lets them apply equally to univariate or multivariate series.
- Risk scores are clipped to ``[0, 1]`` with ``1 = maximum risk``.
  ``overall_score = 1 - max(risks)`` so higher is always better privacy.
  A single failing sub-score drives the overall score down — this is the
  intended fail-closed behavior.
- We rely only on numpy, pandas, and scikit-learn (already project deps). No
  deep shadow models, no heavy MIA harness — the point is a fast gate, not a
  publishable attack.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Optional

import numpy as np

# sklearn is a project-wide dep; imported at module top because these
# scorecards are typically called in a loop and repeated import costs add up.
from sklearn.metrics import roc_auc_score
from sklearn.neighbors import NearestNeighbors

from the_similarity.synthetic.contracts import (
    PrivacyReport,
    SyntheticDataset,
)


# ---------------------------------------------------------------------------
# Matrix coercion
# ---------------------------------------------------------------------------


def _to_matrix(ds: SyntheticDataset) -> np.ndarray:
    """Coerce a SyntheticDataset's payload to a 2-D float64 numpy array.

    Accepts pandas DataFrames, 1-D arrays (treated as a single feature), and
    2-D arrays (passed through). Non-finite rows are dropped — an all-NaN
    row would poison every distance calculation downstream, and silently
    propagating NaN violates the fail-closed contract.
    """
    data = ds.data
    # Late import so the module stays importable without pandas for callers
    # who only use numpy payloads.
    try:
        import pandas as pd  # noqa: WPS433 — local import is intentional
    except ImportError:  # pragma: no cover - pandas is a hard dep
        pd = None  # type: ignore[assignment]

    if pd is not None and isinstance(data, pd.DataFrame):
        arr = data.to_numpy(dtype=np.float64, copy=False)
    else:
        arr = np.asarray(data, dtype=np.float64)

    if arr.ndim == 1:
        arr = arr.reshape(-1, 1)
    elif arr.ndim != 2:
        raise ValueError(
            f"PrivacyScorecard expects 1-D or 2-D data, got shape {arr.shape}"
        )

    # Drop rows with any non-finite entries. Keeps distances well-defined
    # without masking metric output for callers.
    finite_mask = np.isfinite(arr).all(axis=1)
    return arr[finite_mask]


def _nn_min_distances(
    query: np.ndarray, reference: np.ndarray, exclude_self: bool = False
) -> np.ndarray:
    """Return the distance from every row in ``query`` to its nearest row in
    ``reference``.

    When ``exclude_self`` is True, the reference is the same set as the
    query and the nearest neighbour of each row is *itself* — we ask for two
    neighbours and drop index 0. This is how we build the real↔real DCR
    baseline without a row matching itself at distance zero.
    """
    if reference.shape[0] == 0 or query.shape[0] == 0:
        return np.array([], dtype=np.float64)

    k = 2 if exclude_self else 1
    # brute-force is fine here: these diagnostics run on the eval set
    # (~10^3 rows), and ball_tree/kd_tree offers no speedup for small N and
    # high-D payloads where distances are dense anyway.
    nn = NearestNeighbors(n_neighbors=min(k, reference.shape[0]), algorithm="brute")
    nn.fit(reference)
    distances, _ = nn.kneighbors(query, return_distance=True)
    if exclude_self and distances.shape[1] >= 2:
        return distances[:, 1]
    return distances[:, 0]


# ---------------------------------------------------------------------------
# Sub-metrics
# ---------------------------------------------------------------------------


def _compute_nn_leakage(real: np.ndarray, synth: np.ndarray) -> dict[str, float]:
    """Distance-to-Closest-Record diagnostic.

    Returns ``median_dcr``, ``p05_dcr`` (the synth-to-real tails),
    ``real_baseline_p05`` (5th percentile of the real↔real nearest-neighbour
    distribution — our "normal" spacing), and ``leakage_ratio`` =
    ``p05_dcr / real_baseline_p05``. A ratio close to 1 means the synth set
    sits at normal density; ratios much below 1 mean synth samples crowd the
    real set more tightly than the real set crowds itself.
    """
    if real.shape[0] < 2 or synth.shape[0] == 0:
        return {
            "median_dcr": float("nan"),
            "p05_dcr": float("nan"),
            "real_baseline_p05": float("nan"),
            "leakage_ratio": float("nan"),
        }

    synth_to_real = _nn_min_distances(synth, real, exclude_self=False)
    real_to_real = _nn_min_distances(real, real, exclude_self=True)

    median_dcr = float(np.median(synth_to_real))
    p05_dcr = float(np.percentile(synth_to_real, 5))
    real_baseline_p05 = float(np.percentile(real_to_real, 5))

    # Guard against a degenerate zero-baseline (exact duplicate rows in the
    # real set). Fall back to a tiny epsilon so the ratio is finite; this
    # makes the metric read as "very low leakage ratio" rather than NaN and
    # keeps downstream risk computation well defined.
    denom = real_baseline_p05 if real_baseline_p05 > 0 else 1e-12
    leakage_ratio = p05_dcr / denom

    return {
        "median_dcr": median_dcr,
        "p05_dcr": p05_dcr,
        "real_baseline_p05": real_baseline_p05,
        "leakage_ratio": float(leakage_ratio),
    }


def _compute_memorization(
    real: np.ndarray,
    synth: np.ndarray,
    exact_eps: float = 1e-9,
    near_eps: Optional[float] = None,
) -> dict[str, float]:
    """Count exact and near-exact duplicates between real and synth.

    ``exact_eps`` gates rows that match bit-for-bit up to float rounding.
    ``near_eps`` gates rows that match after a small numerical tolerance;
    when not supplied, we derive it as 1% of the median real↔real nearest-
    neighbour distance, which adapts to the scale of the data (returns
    vs. prices vs. normalised series).
    """
    if real.shape[0] == 0 or synth.shape[0] == 0:
        return {"exact_dupes": 0.0, "near_dupes": 0.0, "near_dupe_frac": 0.0}

    synth_to_real = _nn_min_distances(synth, real, exclude_self=False)

    if near_eps is None:
        if real.shape[0] >= 2:
            real_to_real = _nn_min_distances(real, real, exclude_self=True)
            baseline = float(np.median(real_to_real))
        else:
            baseline = 0.0
        # 1% of typical spacing — small enough to only fire on true near-
        # copies, not legitimate samples that happen to land nearby.
        near_eps = max(baseline * 0.01, exact_eps * 10)

    exact_dupes = int(np.sum(synth_to_real < exact_eps))
    near_dupes = int(np.sum(synth_to_real < near_eps))
    near_dupe_frac = near_dupes / float(synth.shape[0])

    return {
        "exact_dupes": float(exact_dupes),
        "near_dupes": float(near_dupes),
        "near_dupe_frac": float(near_dupe_frac),
    }


def _compute_membership_proxy(real: np.ndarray, synth: np.ndarray) -> dict[str, float]:
    """Shadow-model-free membership inference proxy.

    We split ``real`` in half: the first half pretends to be the training
    "members" (seen by the generator) and the second half the
    "non-members". For each real row, its minimum L2 distance to the synth
    set is a one-dimensional score — a generator that memorized training
    data will place synth samples closer to members than to non-members.
    We compute ROC-AUC of ``(-distance, member_label)``: 0.5 = no signal,
    >0.5 = distance discriminates members, i.e. leakage.

    Returns ``auc`` and ``n_queries`` (total real rows used).
    """
    n_real = real.shape[0]
    if n_real < 4 or synth.shape[0] == 0:
        return {"auc": 0.5, "n_queries": float(n_real)}

    # Deterministic split — no RNG needed since the input order is already
    # the caller's responsibility. This keeps the scorecard pure.
    half = n_real // 2
    members = real[:half]
    non_members = real[half : 2 * half]  # balance the two halves

    member_dists = _nn_min_distances(members, synth, exclude_self=False)
    non_member_dists = _nn_min_distances(non_members, synth, exclude_self=False)

    y_true = np.concatenate(
        [np.ones(member_dists.shape[0]), np.zeros(non_member_dists.shape[0])]
    )
    # Lower distance = more likely to be a member, so negate for scoring.
    scores = np.concatenate([-member_dists, -non_member_dists])

    # roc_auc_score raises on a degenerate single-class input; guard it.
    if len(np.unique(y_true)) < 2:
        auc = 0.5
    else:
        auc = float(roc_auc_score(y_true, scores))

    return {"auc": auc, "n_queries": float(y_true.shape[0])}


# ---------------------------------------------------------------------------
# Risk aggregation
# ---------------------------------------------------------------------------


def _nn_risk(leakage_ratio: float) -> float:
    """Convert the DCR leakage ratio into a risk in ``[0, 1]``.

    ``ratio >= 1`` (synth spacing matches real spacing) → 0 risk.
    ``ratio <= 0`` (synth rows sit on top of real rows) → 1 risk.
    Linear in between.
    """
    if not np.isfinite(leakage_ratio):
        # Missing data: treat as full risk (fail closed).
        return 1.0
    return float(np.clip(1.0 - leakage_ratio, 0.0, 1.0))


def _membership_risk(auc: float) -> float:
    """Map AUC to risk. 0.5 → 0, 1.0 → 1, below 0.5 clipped to 0 (the attack
    underperformed chance — we don't reward that, but it is not leakage)."""
    if not np.isfinite(auc):
        return 1.0
    return float(np.clip(2.0 * (auc - 0.5), 0.0, 1.0))


# ---------------------------------------------------------------------------
# Public scorecard
# ---------------------------------------------------------------------------


class PrivacyScorecard:
    """Privacy scorecard implementing :class:`ScorecardProtocol`.

    Usage
    -----
    >>> card = PrivacyScorecard()
    >>> report = card.evaluate(real_ds, synth_ds)
    >>> report.passed
    True

    The class is stateless; :meth:`evaluate` is pure with respect to its
    inputs. ``passed_threshold`` is a class attribute so users can override
    it globally (e.g. ``PrivacyScorecard.passed_threshold = 0.8``) or per-
    instance.
    """

    # Overall score must meet or exceed this to be considered "passed".
    # 0.6 = at most 40% risk on the worst sub-metric. Tuned as a reasonable
    # default for timeseries generators; tighten for regulated data.
    passed_threshold: float = 0.6

    # Bit-for-bit match tolerance. Anything closer than this counts as an
    # exact duplicate regardless of dtype noise.
    exact_eps: float = 1e-9

    def evaluate(
        self, real: SyntheticDataset, synth: SyntheticDataset
    ) -> PrivacyReport:
        """Run the three sub-diagnostics and return a :class:`PrivacyReport`.

        Fail-closed: if either dataset is empty or coercion yields zero
        usable rows, the report is returned with ``passed=False`` and
        diagnostic zeros in the metric dicts.
        """
        real_arr = _to_matrix(real)
        synth_arr = _to_matrix(synth)

        nn_leakage = _compute_nn_leakage(real_arr, synth_arr)
        memorization = _compute_memorization(
            real_arr, synth_arr, exact_eps=self.exact_eps
        )
        membership_proxy = _compute_membership_proxy(real_arr, synth_arr)

        # Aggregate the three per-dimension risks and take the worst — this
        # is the fail-closed aggregation: one bad signal tanks the score.
        risks = [
            _nn_risk(nn_leakage["leakage_ratio"]),
            float(np.clip(memorization["near_dupe_frac"], 0.0, 1.0)),
            _membership_risk(membership_proxy["auc"]),
        ]
        worst_risk = max(risks) if risks else 1.0
        overall_score = float(np.clip(1.0 - worst_risk, 0.0, 1.0))
        passed = overall_score >= self.passed_threshold

        report = PrivacyReport(
            nn_leakage=nn_leakage,
            memorization=memorization,
            membership_proxy=membership_proxy,
            overall_score=overall_score,
            passed=bool(passed),
        )
        # `replace` is a no-op here but guarantees we emit a value object,
        # not a reference the caller could mutate in place.
        return replace(report)


__all__ = ["PrivacyScorecard"]
