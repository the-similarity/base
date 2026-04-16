"""Realism-first synthetic generators — block bootstrap family.

This module implements the *copies* tier of synthetic generation: methods that
resample contiguous chunks of the real series so that local autocorrelation,
volatility clustering, and marginal distributions are preserved by
construction. They are the simplest high-fidelity baseline and the reference
against which more sophisticated generators (GANs, diffusion, copulas) must
earn their complexity.

Generators implemented
----------------------
- :class:`BlockBootstrapGenerator` — classic moving-block bootstrap. Picks
  random start indices into the real series and concatenates fixed-length
  blocks until ``n`` timesteps are produced.
- :class:`RegimeBlockBootstrapGenerator` — regime-aware variant. Tags each
  real timestep with a regime label (rolling-volatility threshold by default)
  and resamples blocks *within the same regime*. Preserves coarse
  volatility-regime duration structure that a plain block bootstrap smears.

Invariants
----------
- Determinism: identical ``(fit_input, block_len, regime_params, seed)`` must
  yield bit-identical samples. Achieved via
  :func:`numpy.random.default_rng(seed)` — no global RNG state is touched.
- Provenance is mandatory. Every returned :class:`SyntheticDataset` carries
  the generator name, version, seed, and a JSON-serialisable param snapshot.
- Univariate by default; multi-series only when it drops out of numpy
  broadcasting. We keep the block column-aligned (same timesteps across
  series) to preserve cross-series correlation within each block.
- :meth:`fit` stores the real series as-is; generators here are
  non-parametric, so "fitting" is effectively caching.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any, Optional

import numpy as np

from the_similarity.synthetic.contracts import (
    GeneratorProtocol,
    Provenance,
    SyntheticDataset,
    iso_now,
)


# Semantic version shared by both generators in this file. Bump whenever the
# sampling algorithm would produce a different sequence for the same seed.
_COPIES_VERSION = "0.1.0"


def _coerce_to_ndarray(data: Any) -> tuple[np.ndarray, Optional[list[str]]]:
    """Return ``(array, columns)`` from either a numpy array or a DataFrame.

    We avoid a hard pandas import at module load; if the caller handed us a
    DataFrame we detect it via duck typing and extract columns. 1-D arrays
    are reshaped to ``(T, 1)`` so downstream code can assume 2-D.
    """
    # DataFrame duck-type: has ``.values`` and ``.columns``.
    if hasattr(data, "values") and hasattr(data, "columns"):
        arr = np.asarray(data.values)
        cols = [str(c) for c in list(data.columns)]
    else:
        arr = np.asarray(data)
        cols = None
    if arr.ndim == 1:
        arr = arr.reshape(-1, 1)
    return arr, cols


def _sample_block_starts(
    rng: np.random.Generator,
    series_len: int,
    block_len: int,
    n_blocks: int,
    allowed_starts: Optional[np.ndarray] = None,
) -> np.ndarray:
    """Draw ``n_blocks`` block start indices with replacement.

    When ``allowed_starts`` is ``None`` starts are uniform over
    ``[0, series_len - block_len]`` (moving-block bootstrap). When supplied,
    starts are sampled from that explicit pool — used by the regime-aware
    variant to constrain starts to a given regime.
    """
    if allowed_starts is None:
        max_start = series_len - block_len
        if max_start < 0:
            raise ValueError(
                f"block_len={block_len} exceeds series length {series_len}"
            )
        return rng.integers(low=0, high=max_start + 1, size=n_blocks)
    if len(allowed_starts) == 0:
        raise ValueError("allowed_starts is empty — no valid blocks to sample")
    # ``rng.choice`` with an explicit array samples with replacement by default.
    return rng.choice(allowed_starts, size=n_blocks, replace=True)


def _assemble_blocks(
    source: np.ndarray,
    starts: np.ndarray,
    block_len: int,
    n_rows: int,
) -> np.ndarray:
    """Concatenate blocks from ``source`` and trim to exactly ``n_rows``."""
    chunks = [source[s : s + block_len] for s in starts]
    stacked = np.concatenate(chunks, axis=0)
    return stacked[:n_rows]


class BlockBootstrapGenerator:
    """Moving-block bootstrap generator.

    Implements :class:`GeneratorProtocol`. Stores the real series at
    :meth:`fit`; at :meth:`sample` draws ``ceil(n / block_len)`` block start
    indices uniformly at random and concatenates the corresponding blocks,
    trimming to exactly ``n`` timesteps.

    Parameters
    ----------
    block_len:
        Length of each resampled block. Larger blocks preserve more
        autocorrelation but reduce variety; typical range 5–40 for daily
        financial series. Must be ``>= 1`` and ``<= len(real)``.
    """

    name: str = "block_bootstrap"
    version: str = _COPIES_VERSION

    def __init__(self, block_len: int = 20) -> None:
        if block_len < 1:
            raise ValueError(f"block_len must be >= 1, got {block_len}")
        self.block_len = int(block_len)
        # Populated by fit(); kept private because mutation would break
        # determinism of subsequent sample() calls.
        self._real_array: Optional[np.ndarray] = None
        self._columns: Optional[list[str]] = None
        self._source_id: str = "unknown"

    def fit(self, real: SyntheticDataset) -> None:
        """Cache the real series. Non-parametric — no training step."""
        arr, cols = _coerce_to_ndarray(real.data)
        if arr.shape[0] < self.block_len:
            raise ValueError(
                f"real series has {arr.shape[0]} rows, needs >= block_len="
                f"{self.block_len}"
            )
        self._real_array = arr
        # Prefer explicit columns from the dataset, else fall back to those
        # derived from the DataFrame, else None.
        self._columns = real.columns if real.columns is not None else cols
        if real.provenance is not None:
            self._source_id = real.provenance.source_id

    def sample(self, n: int, seed: int) -> SyntheticDataset:
        """Draw ``n`` synthetic timesteps deterministic in ``seed``."""
        if self._real_array is None:
            raise RuntimeError("Generator.fit(real) must be called before sample()")
        if n < 1:
            raise ValueError(f"n must be >= 1, got {n}")
        rng = np.random.default_rng(seed)
        n_blocks = int(np.ceil(n / self.block_len))
        starts = _sample_block_starts(
            rng, self._real_array.shape[0], self.block_len, n_blocks
        )
        out = _assemble_blocks(self._real_array, starts, self.block_len, n)
        # Squeeze back to 1-D if the input was 1-D single-series, so callers
        # get what they put in.
        if out.shape[1] == 1 and self._columns is None:
            out = out.reshape(-1)
        provenance = Provenance(
            source_id=self._source_id,
            generator_name=self.name,
            generator_version=self.version,
            seed=int(seed),
            created_at=iso_now(),
            params={"block_len": self.block_len, "n": int(n)},
        )
        return SyntheticDataset(
            data=out,
            index=None,
            columns=self._columns,
            provenance=provenance,
        )


class RegimeBlockBootstrapGenerator:
    """Regime-aware block bootstrap.

    Tags each real timestep with a discrete regime label, then resamples
    blocks whose *entire span* falls inside a single regime. This preserves
    regime-duration statistics that a plain block bootstrap smears by mixing
    low-vol and high-vol days inside the same block.

    Regime detection
    ----------------
    Default method is ``"rolling_vol"``: compute rolling standard deviation
    over ``vol_window`` of the first-differenced first series, then threshold
    at the ``vol_quantile`` quantile → two regimes (calm / turbulent).
    Method ``"kmeans_returns"`` is reserved for a later revision.

    Parameters
    ----------
    block_len:
        Same meaning as :class:`BlockBootstrapGenerator`.
    vol_window:
        Rolling window for the volatility estimate. Must be ``>= 2``.
    vol_quantile:
        Quantile of the rolling-vol series used as the calm/turbulent cut.
        Must be in ``(0, 1)``. 0.5 → median split.
    method:
        Regime-detection method name. Only ``"rolling_vol"`` is implemented
        in v0.1.0 — other values raise ``ValueError``.

    Fallback
    --------
    If a regime has fewer valid block starts than requested for that regime,
    we degrade gracefully to sampling across all starts (warning-free but the
    provenance ``params`` records ``regime_fallback=True``).
    """

    name: str = "regime_block_bootstrap"
    version: str = _COPIES_VERSION

    def __init__(
        self,
        block_len: int = 20,
        vol_window: int = 20,
        vol_quantile: float = 0.5,
        method: str = "rolling_vol",
    ) -> None:
        if block_len < 1:
            raise ValueError(f"block_len must be >= 1, got {block_len}")
        if vol_window < 2:
            raise ValueError(f"vol_window must be >= 2, got {vol_window}")
        if not (0.0 < vol_quantile < 1.0):
            raise ValueError(f"vol_quantile must be in (0, 1), got {vol_quantile}")
        if method != "rolling_vol":
            raise ValueError(
                f"unsupported regime method {method!r}; only 'rolling_vol' "
                "is implemented in v0.1.0"
            )
        self.block_len = int(block_len)
        self.vol_window = int(vol_window)
        self.vol_quantile = float(vol_quantile)
        self.method = method
        self._real_array: Optional[np.ndarray] = None
        self._columns: Optional[list[str]] = None
        self._source_id: str = "unknown"
        # Per-regime arrays of valid block start indices, populated at fit().
        self._regime_starts: dict[int, np.ndarray] = {}

    def _tag_regimes(self, arr: np.ndarray) -> np.ndarray:
        """Return an int array of regime labels aligned with ``arr``.

        Uses the first series (column 0) as the volatility proxy — adequate
        for univariate and common-driver multi-series cases. Edge NaNs from
        the rolling window get the calm label (0).
        """
        series = arr[:, 0].astype(float)
        diffs = np.diff(series, prepend=series[0])
        # Rolling std via a cumulative trick: std over a window of length w
        # is sqrt(E[x^2] - E[x]^2) computed from cumsum and cumsum of squares.
        w = self.vol_window
        n = len(diffs)
        # Pad with zeros at the start so the first w-1 values fall back to
        # partial-window std (still well-defined) rather than NaN.
        csum = np.cumsum(diffs)
        csum2 = np.cumsum(diffs * diffs)
        roll_mean = np.empty(n, dtype=float)
        roll_var = np.empty(n, dtype=float)
        for i in range(n):
            lo = max(0, i - w + 1)
            count = i - lo + 1
            s = csum[i] - (csum[lo - 1] if lo > 0 else 0.0)
            s2 = csum2[i] - (csum2[lo - 1] if lo > 0 else 0.0)
            mean = s / count
            var = max(s2 / count - mean * mean, 0.0)
            roll_mean[i] = mean
            roll_var[i] = var
        vol = np.sqrt(roll_var)
        cutoff = np.quantile(vol, self.vol_quantile)
        # Regime 0 = calm (vol below cutoff), 1 = turbulent (vol >= cutoff).
        return (vol >= cutoff).astype(int)

    def fit(self, real: SyntheticDataset) -> None:
        arr, cols = _coerce_to_ndarray(real.data)
        if arr.shape[0] < self.block_len:
            raise ValueError(
                f"real series has {arr.shape[0]} rows, needs >= block_len="
                f"{self.block_len}"
            )
        self._real_array = arr
        self._columns = real.columns if real.columns is not None else cols
        if real.provenance is not None:
            self._source_id = real.provenance.source_id
        labels = self._tag_regimes(arr)
        # A start index ``s`` is valid for regime ``r`` iff every label in
        # ``labels[s : s + block_len]`` equals ``r``. Compute via strided view
        # comparison without scipy.
        n = arr.shape[0]
        self._regime_starts = {}
        max_start = n - self.block_len
        if max_start < 0:
            raise ValueError("series shorter than block_len after fit")
        for r in np.unique(labels):
            valid: list[int] = []
            for s in range(max_start + 1):
                if np.all(labels[s : s + self.block_len] == r):
                    valid.append(s)
            self._regime_starts[int(r)] = np.asarray(valid, dtype=int)
        self._labels = labels  # retained for sampling-time regime selection

    def sample(self, n: int, seed: int) -> SyntheticDataset:
        if self._real_array is None:
            raise RuntimeError("Generator.fit(real) must be called before sample()")
        if n < 1:
            raise ValueError(f"n must be >= 1, got {n}")
        rng = np.random.default_rng(seed)
        n_blocks = int(np.ceil(n / self.block_len))
        # Regime weights proportional to their share of the real timeline —
        # keeps the marginal regime mixture roughly faithful.
        labels = self._labels
        regimes, counts = np.unique(labels, return_counts=True)
        probs = counts / counts.sum()
        chosen_regimes = rng.choice(regimes, size=n_blocks, replace=True, p=probs)
        fallback_used = False
        starts = np.empty(n_blocks, dtype=int)
        for i, r in enumerate(chosen_regimes):
            pool = self._regime_starts.get(int(r), np.asarray([], dtype=int))
            if len(pool) == 0:
                # Degrade to a plain-bootstrap start — rare, but possible
                # when a regime is shorter than block_len contiguously.
                fallback_used = True
                starts[i] = rng.integers(
                    low=0, high=self._real_array.shape[0] - self.block_len + 1
                )
            else:
                starts[i] = int(rng.choice(pool))
        out = _assemble_blocks(self._real_array, starts, self.block_len, n)
        if out.shape[1] == 1 and self._columns is None:
            out = out.reshape(-1)
        provenance = Provenance(
            source_id=self._source_id,
            generator_name=self.name,
            generator_version=self.version,
            seed=int(seed),
            created_at=iso_now(),
            params={
                "block_len": self.block_len,
                "vol_window": self.vol_window,
                "vol_quantile": self.vol_quantile,
                "method": self.method,
                "n": int(n),
                "regime_fallback": bool(fallback_used),
            },
        )
        return SyntheticDataset(
            data=out,
            index=None,
            columns=self._columns,
            provenance=provenance,
        )


# Runtime-check convenience: assert both generators satisfy the Protocol at
# import time. Cheap (attribute checks) and catches signature drift early.
assert isinstance(BlockBootstrapGenerator(block_len=1), GeneratorProtocol)
assert isinstance(
    RegimeBlockBootstrapGenerator(block_len=1, vol_window=2),
    GeneratorProtocol,
)


__all__ = [
    "BlockBootstrapGenerator",
    "RegimeBlockBootstrapGenerator",
]
