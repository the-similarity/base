"""Seasonal-naive baseline forecaster.

The seasonal-naive forecaster is the canonical "first thing to beat"
in time-series forecasting. P50 = repeat the last full seasonal cycle
of length ``m``. P10 / P90 are the Gaussian-approximate ±1.28σ band
around that point forecast, where σ is the standard deviation of
seasonal-lag residuals on the training set.

Why Gaussian ±1.28σ rather than empirical quantiles?
    1.28σ ≈ the 80th-percentile two-sided z-score, so this directly
    targets an 80% prediction interval (the ``coverage_p10_p90`` metric
    target). The Gaussian assumption is wrong for heavy-tailed series
    but it is the standard reference baseline in the M4/Monash
    literature — using it lets the harness compare against published
    seasonal-naive numbers without ambiguity.
"""

from __future__ import annotations

import numpy as np

from benchmarks.core import Forecast

# z = norm.ppf(0.90) ≈ 1.2815515655446004 — hard-coded so we don't pull
# in scipy.stats just for a single constant. Verified against scipy at
# repo-init time; precision well beyond what the metric needs.
_Z_80 = 1.2815515655446004


class SeasonalNaive:
    """Repeat-last-cycle baseline with Gaussian residual band."""

    name = "naive"

    def forecast(
        self,
        train: np.ndarray,
        horizon: int,
        seasonality: int,
    ) -> Forecast:
        """Repeat the last seasonal cycle for P50; ±1.28σ residual band.

        For seasonality m and horizon h:
            P50[i] = train[len(train) - m + (i mod m)]   for i in [0, h)
            sigma  = std(train[m:] - train[:-m])         (seasonal residuals)
            P10[i] = P50[i] - 1.28 * sigma
            P90[i] = P50[i] + 1.28 * sigma

        Edge cases:
            - If the train series is shorter than ``2*seasonality`` we
              fall back to repeating the last value (m = 1 effectively)
              and using first-difference std for the band.
        """
        train = np.asarray(train, dtype=np.float64)
        n = len(train)
        m = seasonality if n >= 2 * seasonality else 1

        # Last full seasonal cycle — slice from the tail. For m=1 this
        # collapses to ``[train[-1]]`` so the cycle repeat reduces to
        # last-value-carry-forward.
        last_cycle = train[-m:]
        # np.tile guarantees enough length even when horizon > m, then
        # we trim to exactly ``horizon``.
        repeats = int(np.ceil(horizon / m))
        p50 = np.tile(last_cycle, repeats)[:horizon]

        # Residual std from the in-sample seasonal lag. A constant
        # series gives sigma=0; the band collapses to the point
        # forecast in that case (which is the correct, fail-closed
        # behaviour — coverage will be 0 unless the test is also
        # constant).
        diffs = train[m:] - train[:-m] if n > m else np.array([0.0])
        sigma = float(np.std(diffs))

        band = _Z_80 * sigma
        p10 = p50 - band
        p90 = p50 + band

        return Forecast(
            p10=p10.astype(np.float64),
            p50=p50.astype(np.float64),
            p90=p90.astype(np.float64),
        )
