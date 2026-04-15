"""Utility benchmark scorecard — TRTS / TSTR one-step-ahead forecasting.

Measures whether synthetic data is useful for a concrete downstream task
(the "utility" dimension of synthetic-data evaluation). We pick the
simplest defensible task: univariate one-step-ahead regression with lag
features via ridge regression.

Pipeline
--------
1. Extract the first series (univariate) from both real and synthetic
   datasets as a 1-D float array.
2. Build supervised pairs ``(X_t, y_t)`` where ``X_t = [y[t-L], ..., y[t-1]]``
   and target ``y_t = y[t]``. Lags are ``1..L`` (``L = LAGS``).
3. Chronologically split the real series into train / test at
   ``TRAIN_FRAC`` (default 0.7). Synthetic is used whole — generators are
   responsible for their own sample size.
4. Fit a :class:`sklearn.linear_model.Ridge` (seeded) on three regimes:
   real-baseline (train=real_train, test=real_test), TRTS (train=real_train,
   test=synth), TSTR (train=synth, test=real_test). Report MAE / RMSE / R².
5. ``transfer_gap = (tstr_mae - baseline_mae) / baseline_mae`` — relative
   degradation when training on synthetic rather than real. Smaller is
   better; negative means synthetic actually *helped*.
6. ``passed`` iff ``transfer_gap < THRESHOLD``.

Fail-closed invariants
----------------------
- Any non-finite metric (NaN / inf from degenerate splits, constant
  targets, singular fits) forces ``passed=False`` — the diagnostic is
  preserved in the metric dicts for inspection rather than silently
  coerced to a pass.
- Too-short inputs (fewer rows than ``LAGS + 2``) also fail closed with
  an explanatory sentinel in the report.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np

from the_similarity.synthetic.contracts import (
    ScorecardProtocol,
    SyntheticDataset,
    UtilityReport,
)


def _to_1d_array(data: Any) -> np.ndarray:
    """Coerce ``SyntheticDataset.data`` (ndarray or DataFrame) to a 1-D
    float64 numpy array taking the first column for multi-series inputs.

    Returning float64 keeps ridge's numerics well-conditioned and avoids
    surprises from integer-typed source data.
    """
    # pandas is a first-party dep but importing lazily keeps this module
    # light when callers only pass numpy arrays (common in tests).
    try:
        import pandas as pd
    except ImportError:  # pragma: no cover - pandas is required in prod
        pd = None  # type: ignore[assignment]

    if pd is not None and isinstance(data, pd.DataFrame):
        if data.shape[1] == 0:
            return np.empty(0, dtype=np.float64)
        return data.iloc[:, 0].to_numpy(dtype=np.float64, copy=True)
    if pd is not None and isinstance(data, pd.Series):
        return data.to_numpy(dtype=np.float64, copy=True)

    arr = np.asarray(data, dtype=np.float64)
    if arr.ndim == 1:
        return arr.copy()
    if arr.ndim == 2:
        if arr.shape[1] == 0:
            return np.empty(0, dtype=np.float64)
        return arr[:, 0].copy()
    raise ValueError(f"Unsupported data ndim={arr.ndim}; expected 1 or 2")


def _make_lag_matrix(y: np.ndarray, lags: int) -> tuple[np.ndarray, np.ndarray]:
    """Build supervised ``(X, y)`` for one-step-ahead regression.

    ``X[i] = [y[i], y[i+1], ..., y[i+lags-1]]`` and target
    ``y_out[i] = y[i+lags]``. Length of output = ``len(y) - lags``. Caller
    must ensure ``len(y) > lags``.
    """
    n = len(y) - lags
    X = np.empty((n, lags), dtype=np.float64)
    for k in range(lags):
        X[:, k] = y[k : k + n]
    y_out = y[lags : lags + n]
    return X, y_out


def _metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict[str, float]:
    """MAE / RMSE / R² with NaN-safe coercion.

    R² uses the standard ``1 - SS_res / SS_tot`` definition; when the
    target has zero variance we emit ``nan`` rather than dividing by
    zero — the caller's fail-closed path treats NaN as a failure.
    """
    from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

    if len(y_true) == 0:
        return {"mae": float("nan"), "rmse": float("nan"), "r2": float("nan")}
    mae = float(mean_absolute_error(y_true, y_pred))
    mse = float(mean_squared_error(y_true, y_pred))
    rmse = math.sqrt(mse)
    # r2_score warns and returns nan-ish when variance is zero; catch the
    # degenerate case explicitly so the metric dict carries a clean NaN.
    if np.var(y_true) == 0.0:
        r2 = float("nan")
    else:
        r2 = float(r2_score(y_true, y_pred))
    return {"mae": mae, "rmse": rmse, "r2": r2}


def _fit_predict(
    X_train: np.ndarray,
    y_train: np.ndarray,
    X_test: np.ndarray,
    y_test: np.ndarray,
    *,
    alpha: float,
    seed: int,
) -> dict[str, float]:
    """Fit a seeded Ridge on (X_train, y_train) and score on (X_test, y_test)."""
    from sklearn.linear_model import Ridge

    # `random_state` only matters for Ridge's stochastic solvers, but we
    # pass it for determinism regardless of solver choice.
    model = Ridge(alpha=alpha, random_state=seed)
    model.fit(X_train, y_train)
    y_pred = model.predict(X_test)
    return _metrics(y_test, y_pred)


def _all_finite(metrics: dict[str, float]) -> bool:
    """True iff every metric is a finite float (no NaN / inf)."""
    return all(isinstance(v, float) and math.isfinite(v) for v in metrics.values())


@dataclass
class UtilityScorecard:
    """Train-on-synthetic / test-on-real utility benchmark.

    Implements :class:`ScorecardProtocol` for the utility dimension. The
    downstream task is deliberately minimal — one-step-ahead Ridge with
    lag features — so that differences in the report reflect data
    quality, not modelling choices.

    Class attributes
    ----------------
    THRESHOLD:
        Maximum acceptable ``transfer_gap`` for the report to be marked
        ``passed``. 0.3 = TSTR may be up to 30% worse (by MAE) than the
        real baseline before we reject.
    LAGS:
        Number of lag features (``1..LAGS``). 5 is a defensible default
        for daily financial series.
    TRAIN_FRAC:
        Fraction of the real series used as the training split; the
        remainder is held out as the real test set.
    RIDGE_ALPHA:
        L2 penalty for Ridge. 1.0 is sklearn's default.
    SEED:
        Deterministic RNG seed passed to Ridge.
    """

    THRESHOLD: float = 0.3
    LAGS: int = 5
    TRAIN_FRAC: float = 0.7
    RIDGE_ALPHA: float = 1.0
    SEED: int = 0

    def evaluate(
        self, real: SyntheticDataset, synth: SyntheticDataset
    ) -> UtilityReport:
        """Compute TRTS / TSTR / real-baseline metrics and the transfer gap.

        Returns a :class:`UtilityReport`. On any failure (too-short input,
        degenerate variance, non-finite metric) the report fails closed:
        ``passed=False`` with a ``reason`` sentinel merged into the
        affected metric dict.
        """
        real_y = _to_1d_array(real.data)
        synth_y = _to_1d_array(synth.data)

        min_len = self.LAGS + 2
        if len(real_y) < min_len or len(synth_y) < min_len:
            reason = {
                "reason_too_short": 1.0,
                "real_len": float(len(real_y)),
                "synth_len": float(len(synth_y)),
            }
            return UtilityReport(
                trts=dict(reason),
                tstr=dict(reason),
                real_baseline=dict(reason),
                transfer_gap=float("nan"),
                passed=False,
            )

        # Chronological split — never shuffle; time-series leakage is the
        # whole thing we're guarding against.
        split = int(round(len(real_y) * self.TRAIN_FRAC))
        # Guarantee both halves have enough rows to build lag features.
        split = max(min_len, min(split, len(real_y) - min_len))
        real_train = real_y[:split]
        real_test = real_y[split:]

        X_rtrain, y_rtrain = _make_lag_matrix(real_train, self.LAGS)
        X_rtest, y_rtest = _make_lag_matrix(real_test, self.LAGS)
        X_synth, y_synth = _make_lag_matrix(synth_y, self.LAGS)

        baseline = _fit_predict(
            X_rtrain, y_rtrain, X_rtest, y_rtest,
            alpha=self.RIDGE_ALPHA, seed=self.SEED,
        )
        trts = _fit_predict(
            X_rtrain, y_rtrain, X_synth, y_synth,
            alpha=self.RIDGE_ALPHA, seed=self.SEED,
        )
        tstr = _fit_predict(
            X_synth, y_synth, X_rtest, y_rtest,
            alpha=self.RIDGE_ALPHA, seed=self.SEED,
        )

        baseline_mae = baseline["mae"]
        tstr_mae = tstr["mae"]

        # transfer_gap is only meaningful when baseline_mae is positive
        # and finite; otherwise surface NaN and fail closed.
        if (
            not math.isfinite(baseline_mae)
            or not math.isfinite(tstr_mae)
            or baseline_mae <= 0.0
        ):
            transfer_gap = float("nan")
        else:
            transfer_gap = (tstr_mae - baseline_mae) / baseline_mae

        all_finite = (
            _all_finite(baseline)
            and _all_finite(trts)
            and _all_finite(tstr)
            and math.isfinite(transfer_gap)
        )
        passed = bool(all_finite and transfer_gap < self.THRESHOLD)

        return UtilityReport(
            trts=trts,
            tstr=tstr,
            real_baseline=baseline,
            transfer_gap=float(transfer_gap),
            passed=passed,
        )


# Runtime protocol check — cheap assertion that future refactors don't
# drift away from the ScorecardProtocol surface.
assert isinstance(UtilityScorecard(), ScorecardProtocol)


__all__ = ["UtilityScorecard"]
