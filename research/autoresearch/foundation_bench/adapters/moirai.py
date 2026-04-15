"""Moirai adapter (Salesforce, masked-encoder foundation model).

Attempts to load ``Salesforce/moirai-1.0-R-small`` via the ``uni2ts``
package. If import fails, emits an AR(1) Gaussian cone labelled with
``fallback_reason``. Moirai's real output is a parametric mixture; in
offline mode the parametric AR(1) cone is the closer structural proxy.

The adapter keeps ``patch_size`` and ``num_samples`` visible in the
metadata even in fallback mode so the ledger artefacts document the
configuration that WOULD be used with real weights.
"""
from __future__ import annotations

from typing import Sequence

import numpy as np

from research.autoresearch.foundation_bench.adapters.base import (
    ForecastResult,
    ar1_cone,
)


class MoiraiAdapter:
    name = "moirai"

    def __init__(
        self,
        num_samples: int = 20,
        patch_size: int = 32,
        ctx_len: int = 5000,
        seed: int = 0,
    ):
        self.num_samples = int(num_samples)
        self.patch_size = int(patch_size)
        self.ctx_len = int(ctx_len)
        self.seed = int(seed)
        self._model = None
        self._load_error: str | None = None

        try:  # pragma: no cover — optional heavy dep
            from uni2ts.model.moirai import MoiraiForecast  # type: ignore[import]

            self._model = MoiraiForecast
        except Exception as err:  # noqa: BLE001
            self._load_error = f"uni2ts/moirai import failed: {err.__class__.__name__}: {err}"

    def predict_quantiles(
        self,
        history: np.ndarray,
        forward_bars: int,
        percentiles: Sequence[int],
    ) -> ForecastResult:
        if self._model is None:
            quantiles = ar1_cone(
                history[-self.ctx_len :],
                forward_bars=forward_bars,
                percentiles=percentiles,
                seed=self.seed,
            )
            return ForecastResult(
                quantiles=quantiles,
                point_forecast=quantiles[50] if 50 in quantiles else None,
                fallback_reason=self._load_error
                or "moirai weights not available in this environment",
                metadata={
                    "adapter": self.name,
                    "mode": "synthetic_fallback",
                    "cone": "ar1_gaussian",
                    "patch_size": self.patch_size,
                    "num_samples": self.num_samples,
                    "ctx_len_used": min(len(history), self.ctx_len),
                },
            )
        raise NotImplementedError(  # pragma: no cover
            "Real Moirai inference path stubbed — wire MoiraiForecast.predict here."
        )
