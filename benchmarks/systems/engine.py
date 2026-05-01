"""The Similarity engine adapter — wraps search() + project() at default config.

Default config means literally ``Config()`` — every method active, every
weight at the value the maintainer ships. The whole reason this
benchmark exists is to give an honest reading of "what does the engine
do out of the box". Tuning here would defeat the experiment.

Three implementation details worth flagging:

1. **Window size**: the engine's search expects a query window. We
   slice the LAST ``min(2 * seasonality, len(train) // 4)`` bars off
   the train series — same heuristic as the matrix-profile adapter, so
   the two analog-retrieval systems get equivalent context budgets.

2. **History argument**: passes the FULL train series so the engine
   has every prior position available as a candidate analog.

3. **Return-space → level-space conversion**: the engine returns
   ``curves[p]`` as cumulative returns relative to the anchor (last
   train bar). Benchmark scoring is in level space (raw observations),
   so we multiply each return back through ``anchor`` and add it to
   ``anchor``: ``level[i] = anchor * (1 + return[i])``. This matches
   what the engine's own viz layer does.
"""

from __future__ import annotations

import numpy as np

from benchmarks.core import Forecast


class TheSimilarity:
    """Default-config engine adapter."""

    name = "engine"

    def forecast(
        self,
        train: np.ndarray,
        horizon: int,
        seasonality: int,
    ) -> Forecast:
        """Run search() + project() with default Config(), then map curves to levels.

        Edge cases:
            - When ``search`` returns zero matches (e.g. train shorter
              than the engine's minimum window), we return a degenerate
              last-value forecast so the runner can still score it. The
              report layer flags it via the resulting MAE.
            - Anchor of zero is impossible for level-space data we
              benchmark on, but we guard against it (anchor → 1.0 to
              avoid division by zero) — defensive belt-and-braces.
        """
        # Lazy imports keep the engine optional for dependents that only
        # want naive + matrix_profile. The engine pulls in scipy,
        # PyWavelets, EMD-signal, etc. — heavy enough that we don't want
        # to pay that import cost just for a Forecast dataclass test.
        from the_similarity.api import project, search
        from the_similarity.config import Config

        train = np.asarray(train, dtype=np.float64)
        n = len(train)
        # Same window-size heuristic as MatrixProfile (~2 seasonal cycles,
        # capped at len/4) so the two retrieval systems get apples-to-
        # apples context budgets. The engine's matcher will refuse very
        # short windows internally.
        window_size = min(2 * seasonality, n // 4)
        if window_size < 4 or n < 2 * window_size + 1:
            return self._degenerate_forecast(train, horizon)

        query = train[-window_size:]
        # Anchor = last bar of the query (== last train obs) — the
        # engine's projector defines returns relative to this.
        anchor = float(train[-1])
        if anchor == 0.0:
            anchor = 1.0  # defensive; level-space benchmark data is never 0

        # DEFAULT CONFIG. Do not pass overrides here — see module docstring.
        cfg = Config()

        try:
            results = search(query=query, history=train, top_k=20, config=cfg)
        except Exception:
            # The engine occasionally raises on degenerate inputs (e.g.
            # constant-prefix series). Fail-closed to a degenerate
            # forecast so the runner records the failure as a NaN-free
            # row instead of a crash.
            return self._degenerate_forecast(train, horizon)

        if not results.matches:
            return self._degenerate_forecast(train, horizon)

        forecast_obj = project(
            matches=results,
            history=train,
            forward_bars=horizon,
            percentiles=[10, 50, 90],
            config=cfg,
        )

        # Convert return-space curves back to level-space. The engine
        # stores ``curves[p]`` as cumulative fractional returns from the
        # anchor: a curve value of 0.05 means "5% above anchor".
        def _to_level(curve: np.ndarray) -> np.ndarray:
            arr = np.asarray(curve, dtype=np.float64)
            if len(arr) < horizon:
                # Pad with the last value if the engine returned fewer
                # bars than asked (rare, but happens when all matches
                # lack enough forward data).
                pad = np.full(horizon - len(arr), arr[-1] if len(arr) > 0 else 0.0)
                arr = np.concatenate([arr, pad])
            return anchor * (1.0 + arr[:horizon])

        p10 = _to_level(forecast_obj.curves.get(10, np.zeros(horizon)))
        p50 = _to_level(forecast_obj.curves.get(50, np.zeros(horizon)))
        p90 = _to_level(forecast_obj.curves.get(90, np.zeros(horizon)))

        # Some engine paths can return reversed cones (P10 > P90) on
        # very small match sets. Sort the trio per-bar so the band is
        # always a valid (low, mid, high) ordering — the metrics
        # (especially coverage) assume P10 ≤ P90.
        stacked = np.stack([p10, p50, p90], axis=0)
        stacked.sort(axis=0)
        p10_sorted, p50_sorted, p90_sorted = stacked[0], stacked[1], stacked[2]

        return Forecast(p10=p10_sorted, p50=p50_sorted, p90=p90_sorted)

    @staticmethod
    def _degenerate_forecast(train: np.ndarray, horizon: int) -> Forecast:
        """Constant last-value fallback when the engine cannot run."""
        last = float(train[-1]) if len(train) > 0 else 0.0
        flat = np.full(horizon, last, dtype=np.float64)
        return Forecast(p10=flat.copy(), p50=flat.copy(), p90=flat.copy())
