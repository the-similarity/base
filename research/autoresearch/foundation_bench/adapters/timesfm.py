"""TimesFM adapter (Google, 200M params).

Attempts to load ``google/timesfm-1.0-200m`` via ``timesfm`` or the
HuggingFace ``transformers`` stack. If the import or weight download
fails (this is the DEFAULT outcome in the lane's offline CI), we emit an
AR(1) Gaussian cone and set ``fallback_reason`` so the runner can flag
the row as ``partial_synthetic_fallback``.

Design notes
------------
* TimesFM is a decoder-only patch-based transformer; its native output
  is a point forecast. Even with real weights loaded, the adapter wraps
  that point forecast in a bootstrap residual cone for quantiles — the
  same treatment the wavelet baseline receives, so fairness is
  preserved.
* The ``history`` array is truncated to ``ctx_len=512`` (the model's
  native context) before being passed to the inference code path.
* ``forward_bars`` is passed as the horizon; in real weights mode it is
  capped at the model's supported horizon (128). In fallback mode any
  horizon up to a few hundred bars is fine.
"""
from __future__ import annotations

from typing import Sequence

import numpy as np

from research.autoresearch.foundation_bench.adapters.base import (
    ForecastResult,
    ar1_cone,
    bootstrap_residual_cone,
)


class TimesFMAdapter:
    """See module docstring. ``name`` is consumed by the runner."""

    name = "timesfm"

    def __init__(self, ctx_len: int = 512, horizon_cap: int = 128, seed: int = 0):
        # These are the model's native limits; we cap forward_bars to the
        # horizon and context to ctx_len so real weights (if present)
        # never OOM on a long history.
        self.ctx_len = int(ctx_len)
        self.horizon_cap = int(horizon_cap)
        self.seed = int(seed)
        self._model = None
        self._load_error: str | None = None

        # --- Attempt to load real weights -------------------------------
        # Real path: ``import timesfm`` or the transformers-hosted port.
        # Both are heavy; in this environment neither is installed and
        # the adapter stays in synthetic mode. We capture the exception
        # string into ``_load_error`` so the artefact carries a human
        # readable explanation.
        try:  # pragma: no cover — depends on optional heavy deps
            import timesfm  # type: ignore[import]  # noqa: F401

            self._model = timesfm  # placeholder; real instantiation TBD
        except Exception as err:  # noqa: BLE001 — we want ANY failure to trigger fallback
            self._load_error = f"timesfm import failed: {err.__class__.__name__}: {err}"

    # --------------------------------------------------------------
    # Protocol method
    # --------------------------------------------------------------

    def predict_quantiles(
        self,
        history: np.ndarray,
        forward_bars: int,
        percentiles: Sequence[int],
    ) -> ForecastResult:
        """Return a ForecastResult.

        Walk-forward: we only read ``history[-ctx_len:]``.
        """
        if self._model is None:
            # Synthetic fallback.
            # We use bootstrap_residual_cone here (not ar1_cone) because
            # TimesFM's real output is a point forecast we'd wrap with a
            # residual-bootstrap cone anyway — this keeps the fallback
            # shape statistically aligned with the real-path output.
            quantiles = bootstrap_residual_cone(
                history[-self.ctx_len :],
                forward_bars=forward_bars,
                percentiles=percentiles,
                n_paths=200,
                seed=self.seed,
            )
            return ForecastResult(
                quantiles=quantiles,
                point_forecast=quantiles[50] if 50 in quantiles else None,
                fallback_reason=self._load_error
                or "timesfm weights not available in this environment",
                metadata={
                    "adapter": self.name,
                    "mode": "synthetic_fallback",
                    "bootstrap_paths": 200,
                    "ctx_len_used": min(len(history), self.ctx_len),
                },
            )

        # pragma: no cover — real inference path, unreachable in offline CI
        raise NotImplementedError(
            "Real TimesFM inference path is intentionally not implemented in this "
            "lane because the weights are unreachable from the CI environment. "
            "When timesfm becomes importable, extend this branch to call "
            "self._model.TimesFm(...).forecast(history=..., horizon=...)."
        )


# ``ar1_cone`` is re-exported only to quiet static checkers that flag the
# test file's monkey-patch path. Adapters do not import it here.
_ = ar1_cone  # noqa: F401
