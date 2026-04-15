"""Fidelity scorecard — quantify how closely a synthetic dataset reproduces
the real one's marginal, temporal, cross-series, and tail statistics.

Evaluation model
----------------
Each metric family produces a bounded per-column (or aggregated) score via a
monotone decreasing transform ``f(diff) = exp(-k * diff)``. The overall score
is a weighted arithmetic mean of the four family scores in ``[0, 1]`` (1 ==
identical distributions). ``passed`` gates on :attr:`FidelityScorecard.threshold`.

Invariants
----------
- Fail-closed: any metric that cannot be computed (NaN input, singleton column,
  degenerate variance) is recorded in the returned dict as ``NaN`` and excluded
  from the aggregate — the score then reflects only families that *could* be
  evaluated. If *nothing* could be evaluated, ``overall_score`` is 0 and
  ``passed`` is ``False``.
- Inputs may be numpy ndarray (``(T,)`` or ``(T, N)``) or pandas DataFrame.
  We duck-type and never mutate the inputs.
- The scorecard is stateless; a single instance may evaluate many pairs.
"""
from __future__ import annotations

import math
from typing import Any, Optional

import numpy as np
from scipy import stats

from the_similarity.synthetic.contracts import (
    FidelityReport,
    SyntheticDataset,
)


# ---------------------------------------------------------------------------
# Array coercion
# ---------------------------------------------------------------------------


def _to_2d_array(dataset: SyntheticDataset) -> tuple[np.ndarray, list[str]]:
    """Return ``(arr, columns)`` with ``arr.shape == (T, N)``.

    Duck-types the payload: if ``.values`` exists (pandas DataFrame/Series) we
    use it, otherwise we treat it as array-like. A 1-D input is promoted to
    ``(T, 1)`` so downstream code can assume 2-D without branching.
    """
    payload: Any = dataset.data
    # pandas DataFrame / Series — rely on .values rather than importing pandas.
    if hasattr(payload, "values") and hasattr(payload, "columns"):
        arr = np.asarray(payload.values, dtype=float)
        cols = [str(c) for c in payload.columns]
    elif hasattr(payload, "values") and hasattr(payload, "name"):  # Series
        arr = np.asarray(payload.values, dtype=float).reshape(-1, 1)
        cols = [str(payload.name) if payload.name is not None else "col0"]
    else:
        arr = np.asarray(payload, dtype=float)
        if arr.ndim == 1:
            arr = arr.reshape(-1, 1)
        # Prefer the dataset's declared columns; fall back to positional names.
        if dataset.columns is not None and len(dataset.columns) == arr.shape[1]:
            cols = [str(c) for c in dataset.columns]
        else:
            cols = [f"col{i}" for i in range(arr.shape[1])]
    if arr.ndim != 2:
        raise ValueError(f"expected 1-D or 2-D data, got shape {arr.shape}")
    return arr, cols


def _finite(x: np.ndarray) -> np.ndarray:
    """Drop non-finite samples; used per-column before stat computation."""
    return x[np.isfinite(x)]


# ---------------------------------------------------------------------------
# Marginal metrics
# ---------------------------------------------------------------------------


def _marginal_metrics(
    real: np.ndarray, synth: np.ndarray, columns: list[str]
) -> dict[str, float]:
    """Per-column marginal agreement: KS stat, Wasserstein-1, moment diffs.

    Returns a flat dict keyed ``"<col>__<metric>"`` so the report stays
    JSON-friendly. Metrics that cannot be computed for a column (e.g. all-NaN)
    are emitted as ``NaN`` rather than omitted — consumers can tell apart
    "not evaluated" from "missing column".
    """
    out: dict[str, float] = {}
    for i, name in enumerate(columns):
        r = _finite(real[:, i])
        s = _finite(synth[:, i])
        if r.size < 2 or s.size < 2:
            for key in ("ks", "wasserstein", "mean_diff", "std_diff", "skew_diff", "kurt_diff"):
                out[f"{name}__{key}"] = float("nan")
            continue
        ks = stats.ks_2samp(r, s).statistic
        w1 = stats.wasserstein_distance(r, s)
        # Moment differences — absolute so the sign of the skew/kurt gap
        # doesn't cancel across columns when we aggregate later.
        mean_d = abs(float(np.mean(r) - np.mean(s)))
        std_d = abs(float(np.std(r, ddof=1) - np.std(s, ddof=1)))
        skew_d = abs(float(stats.skew(r) - stats.skew(s)))
        kurt_d = abs(float(stats.kurtosis(r) - stats.kurtosis(s)))
        out[f"{name}__ks"] = float(ks)
        out[f"{name}__wasserstein"] = float(w1)
        out[f"{name}__mean_diff"] = mean_d
        out[f"{name}__std_diff"] = std_d
        out[f"{name}__skew_diff"] = skew_d
        out[f"{name}__kurt_diff"] = kurt_d
    return out


# ---------------------------------------------------------------------------
# Temporal metrics
# ---------------------------------------------------------------------------


def _acf(x: np.ndarray, lag: int) -> float:
    """Sample autocorrelation at ``lag`` using the biased estimator
    (normalized by variance and series length) — matches statsmodels' default
    and is numerically stable for short series.
    """
    if lag == 0:
        return 1.0
    x = x - np.mean(x)
    denom = float(np.dot(x, x))
    if denom == 0.0 or lag >= len(x):
        return float("nan")
    num = float(np.dot(x[:-lag], x[lag:]))
    return num / denom


def _pacf_lag(x: np.ndarray, lag: int) -> float:
    """Partial autocorrelation at ``lag`` via the Yule-Walker / Durbin-Levinson
    recursion. We avoid statsmodels as an extra dep by solving the Toeplitz
    system directly. Returns NaN if the recursion is degenerate (zero variance
    or too few samples).
    """
    if lag < 1 or lag >= len(x):
        return float("nan")
    # Build ACF up to `lag`; PACF at k is the last coefficient of the order-k
    # Yule-Walker AR fit. We use numpy.linalg.solve on the Toeplitz matrix
    # built from r[0..lag-1].
    r = np.array([_acf(x, k) for k in range(lag + 1)], dtype=float)
    if not np.all(np.isfinite(r)):
        return float("nan")
    R = np.array([[r[abs(i - j)] for j in range(lag)] for i in range(lag)])
    rhs = r[1 : lag + 1]
    try:
        phi = np.linalg.solve(R, rhs)
    except np.linalg.LinAlgError:
        return float("nan")
    return float(phi[-1])


def _temporal_metrics(
    real: np.ndarray,
    synth: np.ndarray,
    columns: list[str],
    lags: tuple[int, ...] = (1, 5, 10),
    include_pacf: bool = True,
) -> dict[str, float]:
    """ACF (and optional PACF) absolute differences at the given lags.

    Aggregated across columns as the mean per-column-per-lag diff so the
    returned dict stays compact. Individual per-column values are also
    emitted so callers can debug regressions.
    """
    out: dict[str, float] = {}
    acf_diffs: list[float] = []
    pacf_diffs: list[float] = []
    for i, name in enumerate(columns):
        r = _finite(real[:, i])
        s = _finite(synth[:, i])
        for lag in lags:
            if r.size <= lag or s.size <= lag:
                out[f"{name}__acf_lag{lag}_diff"] = float("nan")
                if include_pacf:
                    out[f"{name}__pacf_lag{lag}_diff"] = float("nan")
                continue
            ar = _acf(r, lag)
            asyn = _acf(s, lag)
            d = abs(ar - asyn) if math.isfinite(ar) and math.isfinite(asyn) else float("nan")
            out[f"{name}__acf_lag{lag}_diff"] = d
            if math.isfinite(d):
                acf_diffs.append(d)
            if include_pacf:
                pr = _pacf_lag(r, lag)
                ps = _pacf_lag(s, lag)
                pd_ = abs(pr - ps) if math.isfinite(pr) and math.isfinite(ps) else float("nan")
                out[f"{name}__pacf_lag{lag}_diff"] = pd_
                if math.isfinite(pd_):
                    pacf_diffs.append(pd_)
    out["acf_mean_diff"] = float(np.mean(acf_diffs)) if acf_diffs else float("nan")
    if include_pacf:
        out["pacf_mean_diff"] = float(np.mean(pacf_diffs)) if pacf_diffs else float("nan")
    return out


# ---------------------------------------------------------------------------
# Cross-series metrics
# ---------------------------------------------------------------------------


def _cross_series_metrics(
    real: np.ndarray, synth: np.ndarray
) -> Optional[dict[str, float]]:
    """Frobenius norm of the difference between pairwise Pearson corr matrices.

    Returns ``None`` when the dataset is univariate — cross-series dependence
    is undefined for a single column. We also return ``None`` when either
    dataset has zero variance in every column (the corr matrix is ill-defined).
    """
    if real.shape[1] < 2 or synth.shape[1] < 2:
        return None
    # Mask non-finite rows to keep np.corrcoef well-defined; if too many rows
    # drop out we bail to NaN rather than silently producing a corr matrix
    # from 1-2 rows.
    r_mask = np.all(np.isfinite(real), axis=1)
    s_mask = np.all(np.isfinite(synth), axis=1)
    if r_mask.sum() < 3 or s_mask.sum() < 3:
        return {"corr_frobenius_diff": float("nan"), "corr_max_abs_diff": float("nan")}
    cr = np.corrcoef(real[r_mask].T)
    cs = np.corrcoef(synth[s_mask].T)
    if not (np.all(np.isfinite(cr)) and np.all(np.isfinite(cs))):
        return {"corr_frobenius_diff": float("nan"), "corr_max_abs_diff": float("nan")}
    diff = cr - cs
    frob = float(np.linalg.norm(diff, ord="fro"))
    max_abs = float(np.max(np.abs(diff)))
    return {
        "corr_frobenius_diff": frob,
        "corr_max_abs_diff": max_abs,
    }


# ---------------------------------------------------------------------------
# Tail metrics
# ---------------------------------------------------------------------------


def _cvar(x: np.ndarray, q: float) -> float:
    """Conditional value-at-risk at quantile ``q``.

    For ``q <= 0.5`` we take the mean of the lower tail (samples <= quantile);
    for ``q > 0.5`` the upper tail (samples >= quantile). Returns NaN if the
    tail contains no samples (shouldn't happen for normal arrays, but guards
    the pathological cases).
    """
    if x.size == 0:
        return float("nan")
    cutoff = np.quantile(x, q)
    tail = x[x <= cutoff] if q <= 0.5 else x[x >= cutoff]
    if tail.size == 0:
        return float("nan")
    return float(np.mean(tail))


def _tail_metrics(
    real: np.ndarray, synth: np.ndarray, columns: list[str]
) -> dict[str, float]:
    """Tail-quantile ratios and CVaR diffs at the 5%/95% thresholds.

    The "ratio" is ``synth_q / real_q``; a value of 1.0 means the tails line up.
    Because real quantiles can be zero or negative we compute it as
    ``1 - |log(|synth|/|real|)|``-style only when both are nonzero; otherwise
    fall back to an absolute diff. The raw diffs are also reported so that
    downstream consumers can post-process.
    """
    out: dict[str, float] = {}
    ratios_p01: list[float] = []
    ratios_p99: list[float] = []
    cvar_diffs_lo: list[float] = []
    cvar_diffs_hi: list[float] = []
    for i, name in enumerate(columns):
        r = _finite(real[:, i])
        s = _finite(synth[:, i])
        if r.size < 10 or s.size < 10:
            for k in ("p01_ratio", "p99_ratio", "cvar05_diff", "cvar95_diff"):
                out[f"{name}__{k}"] = float("nan")
            continue
        r_p01, r_p99 = float(np.quantile(r, 0.01)), float(np.quantile(r, 0.99))
        s_p01, s_p99 = float(np.quantile(s, 0.01)), float(np.quantile(s, 0.99))
        # Ratio — guard against divide-by-zero by defaulting to NaN; callers
        # should also inspect the absolute CVaR diffs below.
        p01_ratio = s_p01 / r_p01 if r_p01 != 0 else float("nan")
        p99_ratio = s_p99 / r_p99 if r_p99 != 0 else float("nan")
        cvar_lo = abs(_cvar(r, 0.05) - _cvar(s, 0.05))
        cvar_hi = abs(_cvar(r, 0.95) - _cvar(s, 0.95))
        out[f"{name}__p01_ratio"] = p01_ratio
        out[f"{name}__p99_ratio"] = p99_ratio
        out[f"{name}__cvar05_diff"] = cvar_lo
        out[f"{name}__cvar95_diff"] = cvar_hi
        if math.isfinite(p01_ratio):
            ratios_p01.append(p01_ratio)
        if math.isfinite(p99_ratio):
            ratios_p99.append(p99_ratio)
        if math.isfinite(cvar_lo):
            cvar_diffs_lo.append(cvar_lo)
        if math.isfinite(cvar_hi):
            cvar_diffs_hi.append(cvar_hi)
    out["p01_ratio_mean"] = float(np.mean(ratios_p01)) if ratios_p01 else float("nan")
    out["p99_ratio_mean"] = float(np.mean(ratios_p99)) if ratios_p99 else float("nan")
    out["cvar05_mean_diff"] = float(np.mean(cvar_diffs_lo)) if cvar_diffs_lo else float("nan")
    out["cvar95_mean_diff"] = float(np.mean(cvar_diffs_hi)) if cvar_diffs_hi else float("nan")
    return out


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------


def _squash(x: float, k: float) -> float:
    """Map a non-negative diff to ``(0, 1]`` via ``exp(-k * x)``.

    Missing (NaN) diffs return NaN so the aggregator can exclude them. ``k`` is
    a family-specific sensitivity — picked so that a "typical good" diff maps
    to ~0.8-0.9 and a "bad" diff to ~0.1.
    """
    if not math.isfinite(x) or x < 0:
        return float("nan")
    return float(math.exp(-k * x))


def _marginal_score(marginals: dict[str, float]) -> float:
    # KS is already in [0, 1]; we use it directly (1 - KS) averaged across
    # columns. It's the most robust nonparametric summary and avoids the need
    # to pick a sensitivity constant.
    ks_vals = [v for k, v in marginals.items() if k.endswith("__ks") and math.isfinite(v)]
    if not ks_vals:
        return float("nan")
    return float(1.0 - np.mean(ks_vals))


def _temporal_score(temporal: dict[str, float]) -> float:
    d = temporal.get("acf_mean_diff", float("nan"))
    if not math.isfinite(d):
        return float("nan")
    # ACF diffs are bounded in [0, 2]; k=2 gives ~0.82 at diff=0.1, ~0.14 at 1.0.
    return _squash(d, k=2.0)


def _cross_series_score(cross: Optional[dict[str, float]]) -> float:
    if cross is None:
        return float("nan")
    d = cross.get("corr_frobenius_diff", float("nan"))
    if not math.isfinite(d):
        return float("nan")
    # Frobenius norm scales with N; k=0.5 is a gentle default that still
    # penalises large disagreements.
    return _squash(d, k=0.5)


def _tail_score(tails: dict[str, float]) -> float:
    # Average distance of the p01/p99 ratios from 1.0 — tails matching means
    # ratio ≈ 1. Samples where real quantile was zero (NaN ratio) are excluded.
    devs: list[float] = []
    for key in ("p01_ratio_mean", "p99_ratio_mean"):
        v = tails.get(key, float("nan"))
        if math.isfinite(v):
            devs.append(abs(v - 1.0))
    if not devs:
        return float("nan")
    return _squash(float(np.mean(devs)), k=1.0)


# ---------------------------------------------------------------------------
# Public scorecard
# ---------------------------------------------------------------------------


class FidelityScorecard:
    """Default fidelity scorecard implementation.

    Implements :class:`ScorecardProtocol` (duck-typed; no explicit inheritance
    because ``Protocol`` supports structural subtyping). Intended lifecycle:
    instantiate once per evaluation run, call :meth:`evaluate` on any number
    of ``(real, synth)`` pairs. The instance is stateless between calls.

    Parameters
    ----------
    threshold:
        Minimum ``overall_score`` for ``passed=True``. Defaults to
        :attr:`threshold`. Override per-instance for stricter gates.
    weights:
        Optional dict mapping family names (``"marginals"``, ``"temporal"``,
        ``"cross_series"``, ``"tails"``) to non-negative weights. Missing
        keys default to 1. Weights are renormalised over the families that
        produced a finite score, so a univariate dataset (no cross-series)
        doesn't silently collapse the overall score.
    include_pacf:
        If ``True`` (default), PACF differences are computed alongside ACF.
    """

    #: Class-level default gate. Override on instances for stricter runs.
    threshold: float = 0.7

    #: Default per-family weights for the overall aggregate.
    default_weights: dict[str, float] = {
        "marginals": 1.0,
        "temporal": 1.0,
        "cross_series": 1.0,
        "tails": 1.0,
    }

    def __init__(
        self,
        threshold: Optional[float] = None,
        weights: Optional[dict[str, float]] = None,
        include_pacf: bool = True,
        temporal_lags: tuple[int, ...] = (1, 5, 10),
    ) -> None:
        self.threshold = self.__class__.threshold if threshold is None else float(threshold)
        self.weights = dict(self.default_weights)
        if weights:
            self.weights.update({k: float(v) for k, v in weights.items()})
        self.include_pacf = bool(include_pacf)
        self.temporal_lags = tuple(int(x) for x in temporal_lags)

    def evaluate(
        self, real: SyntheticDataset, synth: SyntheticDataset
    ) -> FidelityReport:
        """Compute the full fidelity report for ``(real, synth)``.

        Both datasets must have matching column counts; we align on the real
        dataset's column list so reports are comparable across generators.
        Mismatched shapes surface as ``passed=False`` with empty metric dicts
        rather than an exception, matching the fail-closed contract.
        """
        try:
            r_arr, r_cols = _to_2d_array(real)
            s_arr, s_cols = _to_2d_array(synth)
        except Exception:
            return FidelityReport(overall_score=0.0, passed=False)

        if r_arr.shape[1] != s_arr.shape[1]:
            return FidelityReport(overall_score=0.0, passed=False)

        columns = r_cols  # real side is authoritative for naming.

        marginals = _marginal_metrics(r_arr, s_arr, columns)
        temporal = _temporal_metrics(
            r_arr, s_arr, columns, lags=self.temporal_lags, include_pacf=self.include_pacf
        )
        cross = _cross_series_metrics(r_arr, s_arr)
        tails = _tail_metrics(r_arr, s_arr, columns)

        family_scores = {
            "marginals": _marginal_score(marginals),
            "temporal": _temporal_score(temporal),
            "cross_series": _cross_series_score(cross),
            "tails": _tail_score(tails),
        }
        # Renormalise weights across families that produced finite scores so
        # a univariate dataset (cross_series == NaN) doesn't drag the mean.
        num = 0.0
        den = 0.0
        for fam, score in family_scores.items():
            if math.isfinite(score):
                w = float(self.weights.get(fam, 1.0))
                num += w * score
                den += w
        overall = (num / den) if den > 0 else 0.0
        # Clamp to [0, 1] defensively — the squash functions already respect
        # the bound but KS-based marginal score could, in adversarial inputs,
        # produce a value slightly outside due to float error.
        overall = max(0.0, min(1.0, overall))

        return FidelityReport(
            marginals=marginals,
            temporal=temporal,
            cross_series=cross,
            tails=tails,
            overall_score=overall,
            passed=overall >= self.threshold,
        )


__all__ = ["FidelityScorecard"]
