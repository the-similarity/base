"""Chronos adapter (Amazon, T5-small probabilistic variant).

Attempts to load ``amazon/chronos-t5-small``. If the ``chronos`` package
or ``transformers`` is unavailable, falls back to a bootstrap residual
cone built from the slice history. Chronos natively returns ``num_samples``
sampled paths, so the residual-bootstrap fallback is a closer proxy to
its real output shape than a parametric AR(1) cone would be.

Licensing: Apache-2.0 weights, Apache-2.0 code. Synthetic fallback has no
licensing implications since it uses only the provided history.
"""
from __future__ import annotations

from typing import Sequence

import numpy as np

from research.autoresearch.foundation_bench.adapters.base import (
    ForecastResult,
    bootstrap_residual_cone,
)


class ChronosAdapter:
    name = "chronos"

    def __init__(self, num_samples: int = 20, ctx_len: int = 512, seed: int = 0):
        self.num_samples = int(num_samples)
        self.ctx_len = int(ctx_len)
        self.seed = int(seed)
        self._pipeline = None
        self._load_error: str | None = None

        try:  # pragma: no cover — optional heavy dep
            from chronos import ChronosPipeline  # type: ignore[import]

            self._pipeline = ChronosPipeline.from_pretrained("amazon/chronos-t5-small")
        except Exception as err:  # noqa: BLE001
            self._load_error = f"chronos import failed: {err.__class__.__name__}: {err}"

    def predict_quantiles(
        self,
        history: np.ndarray,
        forward_bars: int,
        percentiles: Sequence[int],
    ) -> ForecastResult:
        if self._pipeline is None:
            quantiles = bootstrap_residual_cone(
                history[-self.ctx_len :],
                forward_bars=forward_bars,
                percentiles=percentiles,
                # Scale number of bootstrap paths to match the real path's
                # num_samples so fallback uncertainty width is comparable.
                n_paths=max(50, self.num_samples * 10),
                seed=self.seed,
            )
            return ForecastResult(
                quantiles=quantiles,
                point_forecast=quantiles[50] if 50 in quantiles else None,
                fallback_reason=self._load_error
                or "chronos weights not available in this environment",
                metadata={
                    "adapter": self.name,
                    "mode": "synthetic_fallback",
                    "bootstrap_paths": max(50, self.num_samples * 10),
                    "ctx_len_used": min(len(history), self.ctx_len),
                },
            )
        raise NotImplementedError(  # pragma: no cover
            "Real Chronos inference path stubbed — wire ChronosPipeline.predict here."
        )
