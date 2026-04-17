"""Privacy scorecard for synthetic time-series datasets.

Implements :class:`PrivacyScorecard`, which satisfies
:class:`~the_similarity.synthetic.contracts.ScorecardProtocol`. Six cheap,
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
4. **Attribute inference risk** — for each column, train a shallow decision
   tree (max_depth=3) on the synthetic data to predict that column from all
   others, then evaluate on real data. If accuracy is significantly above a
   random baseline, the synthetic structure leaks attribute relationships
   that may aid re-identification.
5. **Holdout leakage check** — split real data 80/20. Measure DCR between
   synthetic and the held-out 20% vs. DCR between synthetic and training
   80%. If holdout DCR is close to train DCR, the generator may have
   memorized the training distribution too closely. Reported as
   ``train_dcr / holdout_dcr`` — values near 1.0 are healthy; >> 1 = leakage.
6. **Outlier (tail) exposure** — check if synthetic data reproduces the most
   extreme real records. Count how many real records in the top/bottom 1%
   percentile have a near-neighbour (within 2 sigma) in synthetic data.
   Reported as ``tail_exposure_rate`` in [0, 1].

**These are heuristic probes, not formal privacy guarantees. They detect
gross leakage patterns but cannot certify differential privacy or membership
privacy.**

Design choices
--------------
- All metrics operate on flat ``(n_samples, n_features)`` matrices. Row
  semantics (timestep vs. sequence) are the caller's concern; we just
  treat every row as an independent point. This keeps the attacks O(NM) and
  lets them apply equally to univariate or multivariate series.
- Risk scores are clipped to ``[0, 1]`` with ``1 = maximum risk``.
  ``overall_score`` is a weighted combination of sub-risks (see
  ``_RISK_WEIGHTS``). Higher overall_score = better privacy.
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
from sklearn.tree import DecisionTreeClassifier

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


def _compute_attribute_inference(
    real: np.ndarray, synth: np.ndarray
) -> dict[str, float]:
    """Attribute inference risk for each column.

    For each column *j*, train a DecisionTreeClassifier (max_depth=3) on the
    synthetic data to predict discretised column *j* from all other columns,
    then evaluate accuracy on the real data. The "risk" is accuracy minus the
    random-guess baseline (1 / n_bins). Positive deltas mean the synthetic
    structure leaks enough about column *j* that an attacker can infer it.

    We discretise continuous columns into 5 equal-frequency bins so the tree
    sees a categorical target; this avoids regressor variance issues with tiny
    datasets and keeps the baseline well-defined.

    Returns a dict mapping ``"col_<j>"`` to the accuracy delta above baseline.
    """
    n_features = real.shape[1]
    if n_features < 2 or real.shape[0] < 10 or synth.shape[0] < 10:
        # Not enough data/features for meaningful attribute inference.
        return {}

    n_bins = 5  # equal-frequency quantile bins for the target
    result: dict[str, float] = {}

    for j in range(n_features):
        # --- prepare features (all columns except j) ---
        synth_x = np.delete(synth, j, axis=1)
        real_x = np.delete(real, j, axis=1)

        # --- discretise target column into bins ---
        # Use synth quantiles for bin edges so train and eval use the same
        # binning scheme. np.percentile returns edges; digitize assigns bins.
        col_synth = synth[:, j]
        col_real = real[:, j]

        # Guard against constant columns: all values identical → single bin,
        # baseline = 1.0, delta = 0.
        if np.ptp(col_synth) == 0:
            result[f"col_{j}"] = 0.0
            continue

        edges = np.percentile(
            col_synth,
            np.linspace(0, 100, n_bins + 1)[1:-1],  # inner edges only
        )
        # np.unique deduplicates edges when many values share a quantile,
        # which would otherwise create empty bins and inflate accuracy.
        edges = np.unique(edges)

        synth_y = np.digitize(col_synth, edges)
        real_y = np.digitize(col_real, edges)

        n_classes = len(np.unique(synth_y))
        baseline = 1.0 / max(n_classes, 1)

        # --- train on synth, evaluate on real ---
        tree = DecisionTreeClassifier(max_depth=3, random_state=0)
        tree.fit(synth_x, synth_y)
        acc = float(tree.score(real_x, real_y))

        # Delta above baseline: 0 = no better than random, 1 = perfect.
        delta = float(np.clip(acc - baseline, 0.0, 1.0))
        result[f"col_{j}"] = delta

    return result


def _compute_holdout_leakage(
    real: np.ndarray, synth: np.ndarray
) -> dict[str, float]:
    """Holdout leakage check.

    Split real data 80/20. Measure median DCR from synthetic to the training
    80% (``train_dcr``) and from synthetic to the held-out 20%
    (``holdout_dcr``). If the generator memorized training rows, synthetic
    samples will cluster closer to the training set than to the holdout.

    Returns ``train_dcr``, ``holdout_dcr``, and ``ratio = train_dcr /
    holdout_dcr``. Ratio near 1.0 = healthy (synth is equally close to both
    splits); ratio >> 1 means synth is suspiciously closer to the training
    split, indicating memorization.
    """
    n = real.shape[0]
    if n < 10 or synth.shape[0] < 2:
        return {"train_dcr": float("nan"), "holdout_dcr": float("nan"), "ratio": 1.0}

    # Deterministic 80/20 split (no RNG — row order is the caller's concern).
    split = int(n * 0.8)
    train = real[:split]
    holdout = real[split:]

    if holdout.shape[0] == 0 or train.shape[0] == 0:
        return {"train_dcr": float("nan"), "holdout_dcr": float("nan"), "ratio": 1.0}

    synth_to_train = _nn_min_distances(synth, train, exclude_self=False)
    synth_to_holdout = _nn_min_distances(synth, holdout, exclude_self=False)

    train_dcr = float(np.median(synth_to_train))
    holdout_dcr = float(np.median(synth_to_holdout))

    # Guard against zero denominator: if holdout_dcr is zero, synth rows sit
    # exactly on holdout rows (extreme leakage, but also a degenerate case).
    denom = holdout_dcr if holdout_dcr > 0 else 1e-12
    ratio = train_dcr / denom

    return {"train_dcr": train_dcr, "holdout_dcr": holdout_dcr, "ratio": ratio}


def _compute_tail_exposure(
    real: np.ndarray, synth: np.ndarray, tail_pct: float = 1.0
) -> dict[str, float]:
    """Outlier (tail) exposure rate.

    Identify real records in the top/bottom ``tail_pct`` percentile of each
    column. A tail record is "exposed" if there exists a synthetic row within
    2 sigma (column-wise std) L2 distance. The tail_exposure_rate is the
    fraction of unique tail records that are exposed.

    This catches a common failure mode: generators that reproduce extreme
    values, making them easy targets for re-identification by an adversary
    who knows which real individuals have extreme attributes.

    Returns ``n_tail_records``, ``n_exposed``, and ``rate = n_exposed /
    n_tail_records``.
    """
    n_real, n_feat = real.shape
    if n_real < 10 or synth.shape[0] < 2 or n_feat == 0:
        return {"n_tail_records": 0.0, "n_exposed": 0.0, "rate": 0.0}

    # --- identify tail record indices ---
    # A record is "tail" if ANY of its features is in the extreme percentile.
    tail_mask = np.zeros(n_real, dtype=bool)
    for j in range(n_feat):
        lo = np.percentile(real[:, j], tail_pct)
        hi = np.percentile(real[:, j], 100.0 - tail_pct)
        tail_mask |= (real[:, j] <= lo) | (real[:, j] >= hi)

    tail_records = real[tail_mask]
    n_tail = tail_records.shape[0]
    if n_tail == 0:
        return {"n_tail_records": 0.0, "n_exposed": 0.0, "rate": 0.0}

    # --- threshold: based on the real-to-real nearest-neighbour baseline ---
    # We use the 5th percentile of real↔real NN distances as the "normal"
    # spacing, then define "exposed" as a tail record having a synthetic
    # neighbour closer than this baseline. This adapts to both data scale
    # and density: for dense regions the threshold is tight, for sparse
    # regions (where tails live) a match at baseline distance is suspicious.
    if real.shape[0] >= 2:
        real_to_real = _nn_min_distances(real, real, exclude_self=True)
        threshold = float(np.percentile(real_to_real, 5))
    else:
        # Degenerate: single row, use a small epsilon.
        col_std = np.std(real, axis=0)
        col_std = np.where(col_std > 0, col_std, 1e-12)
        threshold = 0.5 * np.sqrt(np.sum(col_std ** 2))
    # Guard against zero threshold (all real rows identical).
    if threshold <= 0:
        threshold = 1e-12

    # --- check exposure via nearest-neighbour ---
    dists = _nn_min_distances(tail_records, synth, exclude_self=False)
    n_exposed = int(np.sum(dists <= threshold))

    rate = n_exposed / n_tail

    return {
        "n_tail_records": float(n_tail),
        "n_exposed": float(n_exposed),
        "rate": float(np.clip(rate, 0.0, 1.0)),
    }


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


def _attribute_inference_risk(deltas: dict[str, float]) -> float:
    """Aggregate per-column attribute inference deltas into a single risk.

    Takes the *maximum* column delta. A single highly inferable column is
    enough to enable re-identification (fail-closed). The delta is already
    in [0, 1], so it maps directly to risk.
    """
    if not deltas:
        return 0.0
    max_delta = max(deltas.values())
    return float(np.clip(max_delta, 0.0, 1.0))


def _holdout_leakage_risk(ratio: float) -> float:
    """Convert holdout leakage ratio to risk.

    Ratio = train_dcr / holdout_dcr. Healthy generators produce ratio ~ 1.0
    (synth is equidistant from train and holdout). Ratio >> 1 means synth
    clusters around training data. We map ratio to risk linearly:
    ratio <= 1.0 → 0 risk, ratio >= 2.0 → 1 risk (full leakage).
    """
    if not np.isfinite(ratio):
        return 0.0  # NaN = insufficient data, not a signal of leakage.
    return float(np.clip(ratio - 1.0, 0.0, 1.0))


def _tail_exposure_risk(rate: float) -> float:
    """Convert tail exposure rate directly to risk.

    Rate is already in [0, 1]: 0 = no outliers exposed, 1 = all outliers
    reproduced in synthetic data. Maps directly.
    """
    if not np.isfinite(rate):
        return 0.0
    return float(np.clip(rate, 0.0, 1.0))


# Weighted risk aggregation. Each sub-metric contributes to the overall
# score proportionally to its weight. The original three heuristics retain
# the majority of the weight to preserve backward-compatible behavior; the
# three new heuristics share the remainder.
#
# Weights (sum = 1.0):
#   nn_leakage:             0.25  — DCR is the gold standard distance check
#   memorization:           0.25  — direct copy detection
#   membership_inference:   0.20  — proxy MIA
#   attribute_inference:    0.10  — column-level inference probe
#   holdout_leakage:        0.10  — train/holdout distance comparison
#   tail_exposure:          0.10  — outlier re-identification
_RISK_WEIGHTS = {
    "nn_leakage": 0.25,
    "memorization": 0.25,
    "membership_inference": 0.20,
    "attribute_inference": 0.10,
    "holdout_leakage": 0.10,
    "tail_exposure": 0.10,
}


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
        """Run all six sub-diagnostics and return a :class:`PrivacyReport`.

        The six heuristics (three original + three new) are:
        1. Nearest-neighbour leakage (DCR)
        2. Memorization (exact/near dupes)
        3. Membership inference proxy (AUC)
        4. Attribute inference risk (per-column decision tree)
        5. Holdout leakage check (train/holdout DCR ratio)
        6. Tail exposure rate (outlier re-identification)

        Fail-closed: if either dataset is empty or coercion yields zero
        usable rows, the report is returned with ``passed=False`` and
        diagnostic zeros in the metric dicts.
        """
        real_arr = _to_matrix(real)
        synth_arr = _to_matrix(synth)

        # --- Original three heuristics ---
        nn_leakage = _compute_nn_leakage(real_arr, synth_arr)
        memorization = _compute_memorization(
            real_arr, synth_arr, exact_eps=self.exact_eps
        )
        membership_proxy = _compute_membership_proxy(real_arr, synth_arr)

        # --- New heuristics ---
        attr_inference = _compute_attribute_inference(real_arr, synth_arr)
        holdout_leakage = _compute_holdout_leakage(real_arr, synth_arr)
        tail_exposure = _compute_tail_exposure(real_arr, synth_arr)

        # --- Weighted risk aggregation ---
        # Each sub-metric is converted to a risk in [0, 1] then weighted.
        # The overall score = 1 - max(worst_risk, weighted_risk).
        # Fail-closed: any single high-risk sub-metric (>= 0.8) drives the
        # score via the max() term, preventing dilution by low-risk metrics.
        risk_values = {
            "nn_leakage": _nn_risk(nn_leakage["leakage_ratio"]),
            "memorization": float(np.clip(memorization["near_dupe_frac"], 0.0, 1.0)),
            "membership_inference": _membership_risk(membership_proxy["auc"]),
            "attribute_inference": _attribute_inference_risk(attr_inference),
            "holdout_leakage": _holdout_leakage_risk(holdout_leakage["ratio"]),
            "tail_exposure": _tail_exposure_risk(tail_exposure["rate"]),
        }

        # Weighted sum: sum(weight_i * risk_i). Weights sum to 1.0.
        weighted_risk = sum(
            _RISK_WEIGHTS[k] * risk_values[k] for k in _RISK_WEIGHTS
        )
        # Fail-closed guard: the worst single risk still caps the score.
        # This preserves the original invariant where one catastrophic
        # sub-metric (e.g. 100% memorization) cannot be hidden by good
        # scores on the other five metrics.
        worst_risk = max(risk_values.values()) if risk_values else 1.0
        effective_risk = max(weighted_risk, worst_risk)
        overall_score = float(np.clip(1.0 - effective_risk, 0.0, 1.0))
        passed = overall_score >= self.passed_threshold

        report = PrivacyReport(
            nn_leakage=nn_leakage,
            memorization=memorization,
            membership_proxy=membership_proxy,
            attribute_inference_risk=attr_inference,
            holdout_leakage_ratio=holdout_leakage["ratio"],
            tail_exposure_rate=tail_exposure["rate"],
            overall_score=overall_score,
            passed=bool(passed),
        )
        # `replace` is a no-op here but guarantees we emit a value object,
        # not a reference the caller could mutate in place.
        return replace(report)


__all__ = ["PrivacyScorecard"]
