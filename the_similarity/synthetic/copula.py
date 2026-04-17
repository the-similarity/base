"""Gaussian copula synthetic generator.

Generates synthetic time-series data that preserves the cross-column
dependency structure of the real dataset by fitting a Gaussian copula. The
approach:

1. **Fit** — transform each column to uniform marginals via the empirical CDF,
   then compute the Pearson correlation matrix of the Gaussian-quantile-
   transformed uniform values. This correlation matrix encodes the copula.

2. **Sample** — draw from a multivariate normal with the fitted copula
   correlation, map back through the standard normal CDF to get uniform
   samples, then invert each column's empirical CDF to produce synthetic
   values in the original marginal distribution.

This separates dependency modelling (copula) from marginal modelling (empirical
CDF), which is the canonical advantage over block bootstrap: the bootstrap
preserves within-block correlation but cannot generate new dependency
combinations, while the copula can produce previously unseen joint realisations
that are still consistent with the observed dependency structure.

Invariants
----------
- Determinism: identical ``(fit_input, seed)`` produces bit-identical samples.
  Achieved via ``numpy.random.default_rng(seed)`` — no global RNG state.
- Constant columns are detected at fit time and reproduced as constants in
  the output (no NaN, no crash).
- Single-column inputs degenerate to marginal resampling (the copula
  correlation matrix is trivially ``[[1]]``).
- NaN columns raise at fit time — caller must clean before fitting.

Dependencies: numpy, scipy (scipy.stats.norm, scipy.interpolate.interp1d).
"""

from __future__ import annotations

from typing import Any, Optional

import numpy as np
from scipy import stats
from scipy.interpolate import interp1d

from the_similarity.synthetic.contracts import (
    GeneratorProtocol,
    Provenance,
    SyntheticDataset,
    iso_now,
)

# Semantic version for this generator. Bump whenever the sampling algorithm
# would produce a different sequence for the same seed.
_COPULA_VERSION = "0.1.0"


def _coerce_to_ndarray(data: Any) -> tuple[np.ndarray, Optional[list[str]]]:
    """Return ``(array, columns)`` from either a numpy array or a DataFrame.

    Mirrors the helper in ``copies.py`` — duplicated intentionally to keep
    this module import-independent from sibling generators, avoiding circular
    or unnecessary coupling.
    """
    if hasattr(data, "values") and hasattr(data, "columns"):
        arr = np.asarray(data.values, dtype=float)
        cols = [str(c) for c in list(data.columns)]
    else:
        arr = np.asarray(data, dtype=float)
        cols = None
    if arr.ndim == 1:
        arr = arr.reshape(-1, 1)
    return arr, cols


def _empirical_cdf(col: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Compute the empirical CDF for a single column.

    Returns ``(sorted_values, cdf_values)`` where ``cdf_values`` are in
    ``(0, 1)`` (exclusive on both sides). We use ``rank / (n + 1)`` (Weibull
    plotting position) rather than ``rank / n`` to avoid mapping any real
    observation to exactly 0 or 1, which would produce infinite values when
    passed through the inverse normal CDF.

    The returned arrays are deduplicated on the value axis (unique sorted
    values) so ``interp1d`` can build a monotone interpolant without
    duplicate-x errors.
    """
    n = len(col)
    sorted_vals = np.sort(col)
    # Weibull plotting positions: i / (n + 1) for i in 1..n
    raw_cdf = np.arange(1, n + 1, dtype=float) / (n + 1)

    # Deduplicate: for repeated values, keep the *maximum* CDF value
    # (right-continuous convention consistent with the standard ECDF).
    # np.unique returns sorted unique values. For each unique value, the CDF
    # is the maximum rank among all occurrences.
    unique_vals, _inverse = np.unique(sorted_vals, return_inverse=True)
    # For each unique value u, cdf(u) = max(raw_cdf[j] for j where sorted_vals[j] == u).
    # Since sorted_vals is sorted and raw_cdf is monotone, the last occurrence
    # of each unique value has the highest CDF.
    unique_cdf = np.empty(len(unique_vals), dtype=float)
    for i, u in enumerate(unique_vals):
        mask = sorted_vals == u
        unique_cdf[i] = raw_cdf[mask][-1]

    return unique_vals, unique_cdf


class GaussianCopulaGenerator:
    """Gaussian copula generator for synthetic time-series data.

    Implements :class:`GeneratorProtocol`. Fits a Gaussian copula to the real
    dataset by extracting marginal empirical CDFs and a correlation matrix in
    the Gaussian-quantile space. Sampling draws from a multivariate normal
    with the fitted correlation and maps through inverse marginals.

    Parameters
    ----------
    (none — hyperparameter-free for v0.1.0; marginals are always empirical
    and the copula family is always Gaussian.)

    Edge cases
    ----------
    - **Single column**: the correlation matrix is ``[[1]]``, so sampling
      degenerates to marginal resampling via inverse CDF — correct behavior.
    - **Constant columns**: detected at fit time. In sampling, constant
      columns are filled with the constant value (no CDF inversion needed
      since the CDF is degenerate).
    - **NaN columns**: raise ``ValueError`` at fit time. Caller must impute
      or drop before fitting.
    """

    name: str = "gaussian_copula"
    version: str = _COPULA_VERSION

    def __init__(self) -> None:
        # Populated by fit()
        self._n_cols: int = 0
        self._columns: Optional[list[str]] = None
        self._source_id: str = "unknown"

        # Per-column inverse CDF interpolators (None for constant columns).
        self._inverse_cdfs: list[Optional[interp1d]] = []
        # Boolean mask: True for columns that are constant.
        self._constant_mask: np.ndarray = np.array([], dtype=bool)
        # Constant values for constant columns.
        self._constant_values: np.ndarray = np.array([], dtype=float)
        # Copula correlation matrix (only for non-constant columns).
        self._corr: np.ndarray = np.array([])
        # Indices of non-constant columns in the original column ordering.
        self._active_cols: np.ndarray = np.array([], dtype=int)
        self._fitted: bool = False

    def fit(self, real: SyntheticDataset) -> None:
        """Fit marginal CDFs and the copula correlation matrix.

        Steps:
        1. Coerce input to a 2-D float array ``(T, N)``.
        2. Detect constant and NaN columns.
        3. For each non-constant column, compute the empirical CDF and build
           an ``interp1d`` inverse CDF (maps uniform -> original scale).
        4. Transform non-constant columns to uniform via the empirical CDF,
           then to Gaussian via ``norm.ppf``.
        5. Compute the Pearson correlation of the Gaussian-transformed data —
           this is the copula correlation matrix.
        """
        arr, cols = _coerce_to_ndarray(real.data)
        T, N = arr.shape

        # --- NaN check (fail-fast) ---
        nan_cols = np.where(np.any(np.isnan(arr), axis=0))[0]
        if len(nan_cols) > 0:
            raise ValueError(
                f"NaN values found in column(s) {nan_cols.tolist()}. "
                "Clean or impute before fitting."
            )

        self._n_cols = N
        self._columns = real.columns if real.columns is not None else cols
        if real.provenance is not None:
            self._source_id = real.provenance.source_id

        # --- Detect constant columns ---
        col_std = np.std(arr, axis=0)
        self._constant_mask = col_std == 0.0
        self._constant_values = arr[0, :].copy()  # first row suffices for constants

        # Active (non-constant) column indices
        self._active_cols = np.where(~self._constant_mask)[0]
        n_active = len(self._active_cols)

        # --- Build per-column inverse CDFs ---
        self._inverse_cdfs = [None] * N
        # Gaussian-quantile-transformed data for active columns (for correlation)
        gaussian_data = np.empty((T, n_active), dtype=float)

        for idx_in_active, col_idx in enumerate(self._active_cols):
            col = arr[:, col_idx]
            sorted_vals, cdf_vals = _empirical_cdf(col)

            # Inverse CDF: maps uniform (0, 1) -> original scale.
            # `bounds_error=False` + `fill_value` handles values at the
            # boundaries by clamping to the observed range.
            inv_cdf = interp1d(
                cdf_vals,
                sorted_vals,
                kind="linear",
                bounds_error=False,
                fill_value=(sorted_vals[0], sorted_vals[-1]),
            )
            self._inverse_cdfs[col_idx] = inv_cdf

            # Transform this column to uniform via the empirical CDF.
            # For each data point, its uniform value = ECDF(x).
            # We use the forward CDF interpolator for this.
            fwd_cdf = interp1d(
                sorted_vals,
                cdf_vals,
                kind="linear",
                bounds_error=False,
                fill_value=(cdf_vals[0], cdf_vals[-1]),
            )
            uniform_col = fwd_cdf(col)

            # Clamp to avoid infinities in norm.ppf at exactly 0 or 1.
            # Weibull plotting positions already avoid this, but floating-point
            # interpolation can produce boundary values.
            eps = 1e-10
            uniform_col = np.clip(uniform_col, eps, 1.0 - eps)

            # Transform to Gaussian quantile space.
            gaussian_data[:, idx_in_active] = stats.norm.ppf(uniform_col)

        # --- Copula correlation matrix ---
        if n_active <= 1:
            # Single active column (or zero): correlation is trivially [[1]]
            # or empty. Multivariate normal with a 1x1 identity is just N(0,1).
            self._corr = np.eye(max(n_active, 1))
        else:
            self._corr = np.corrcoef(gaussian_data, rowvar=False)
            # Ensure the correlation matrix is positive semi-definite (it should
            # be by construction, but floating-point edge cases exist). Nearest
            # PSD via eigenvalue clamping.
            self._corr = _nearest_psd(self._corr)

        self._fitted = True

    def sample(self, n: int, seed: int) -> SyntheticDataset:
        """Draw ``n`` synthetic rows deterministic in ``seed``.

        Steps:
        1. Draw ``n`` samples from ``N(0, corr)`` for the active columns.
        2. Map through ``norm.cdf`` to get uniform marginals.
        3. Map through each column's inverse empirical CDF.
        4. Fill constant columns with their constant value.
        """
        if not self._fitted:
            raise RuntimeError("Generator.fit(real) must be called before sample()")
        if n < 1:
            raise ValueError(f"n must be >= 1, got {n}")

        rng = np.random.default_rng(seed)
        n_active = len(self._active_cols)
        out = np.empty((n, self._n_cols), dtype=float)

        if n_active > 0:
            # Draw from multivariate normal with the copula correlation.
            # np.random.Generator.multivariate_normal is deterministic given
            # the Generator state, which is seeded above.
            gaussian_samples = rng.multivariate_normal(
                mean=np.zeros(n_active),
                cov=self._corr,
                size=n,
            )

            # Map to uniform via the standard normal CDF.
            uniform_samples = stats.norm.cdf(gaussian_samples)

            # Map each active column through its inverse empirical CDF.
            for idx_in_active, col_idx in enumerate(self._active_cols):
                inv_cdf = self._inverse_cdfs[col_idx]
                out[:, col_idx] = inv_cdf(uniform_samples[:, idx_in_active])

        # Fill constant columns.
        for col_idx in range(self._n_cols):
            if self._constant_mask[col_idx]:
                out[:, col_idx] = self._constant_values[col_idx]

        # Squeeze to 1-D if the input was univariate and had no column names.
        if out.shape[1] == 1 and self._columns is None:
            out = out.reshape(-1)

        provenance = Provenance(
            source_id=self._source_id,
            generator_name=self.name,
            generator_version=self.version,
            seed=int(seed),
            created_at=iso_now(),
            params={"n": int(n)},
        )
        return SyntheticDataset(
            data=out,
            index=None,
            columns=self._columns,
            provenance=provenance,
        )


def _nearest_psd(mat: np.ndarray) -> np.ndarray:
    """Project a symmetric matrix to the nearest positive semi-definite matrix.

    Uses eigenvalue clamping: decompose, floor negative eigenvalues to a small
    positive epsilon, recompose. This is cheaper than the Higham alternating
    projection and sufficient for correlation matrices that are already
    near-PSD (floating-point noise is the only source of non-PSD-ness here).

    The output has unit diagonal (correlation matrix convention) enforced
    after the projection.
    """
    eigvals, eigvecs = np.linalg.eigh(mat)
    # Clamp negative eigenvalues to a small positive value.
    eigvals = np.maximum(eigvals, 1e-10)
    psd = eigvecs @ np.diag(eigvals) @ eigvecs.T
    # Re-symmetrize (floating-point) and enforce unit diagonal.
    psd = (psd + psd.T) / 2.0
    d = np.sqrt(np.diag(psd))
    psd = psd / np.outer(d, d)
    return psd


# Runtime protocol check — catches signature drift at import time.
assert isinstance(GaussianCopulaGenerator(), GeneratorProtocol)


__all__ = ["GaussianCopulaGenerator"]
