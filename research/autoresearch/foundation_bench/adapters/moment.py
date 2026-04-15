"""MOMENT adapter (CMU AutonLab, MIT-licensed foundation model).

Attempts to load ``AutonLab/MOMENT-1-small`` via the ``momentfm`` package.
If unavailable, falls back to a bootstrap residual cone labelled with
``fallback_reason``. MOMENT's real output is a point-forecast head, so
the bootstrap-residual cone structurally mirrors how we would wrap real
weights to emit quantiles.
"""
from __future__ import annotations

from typing import Sequence

import numpy as np

from research.autoresearch.foundation_bench.adapters.base import (
    ForecastResult,
    bootstrap_residual_cone,
)


class MOMENTAdapter:
    name = "moment"

    def __init__(self, ctx_len: int = 512, seed: int = 0):
        self.ctx_len = int(ctx_len)
        self.seed = int(seed)
        self._model = None
        self._load_error: str | None = None

        try:  # pragma: no cover — optional heavy dep
            from momentfm import MOMENTPipeline  # type: ignore[import]

            self._model = MOMENTPipeline.from_pretrained("AutonLab/MOMENT-1-small")
        except Exception as err:  # noqa: BLE001
            self._load_error = f"momentfm import failed: {err.__class__.__name__}: {err}"

    def predict_quantiles(
        self,
        history: np.ndarray,
        forward_bars: int,
        percentiles: Sequence[int],
    ) -> ForecastResult:
        if self._model is None:
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
                or "moment weights not available in this environment",
                metadata={
                    "adapter": self.name,
                    "mode": "synthetic_fallback",
                    "cone": "bootstrap_residual",
                    "ctx_len_used": min(len(history), self.ctx_len),
                },
            )
        raise NotImplementedError(  # pragma: no cover
            "Real MOMENT inference path stubbed — wire MOMENTPipeline.forecast here."
        )
