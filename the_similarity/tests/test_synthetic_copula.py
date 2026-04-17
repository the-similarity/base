"""Tests for the Gaussian copula synthetic generator.

Covers protocol compliance, determinism, correlation preservation, shape
correctness, and edge cases (single column, constant column, NaN column).
"""

from __future__ import annotations

import numpy as np
import pytest

from the_similarity.synthetic.contracts import (
    GeneratorProtocol,
    Provenance,
    SyntheticDataset,
)
from the_similarity.synthetic.copula import GaussianCopulaGenerator


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_dataset(
    data: np.ndarray,
    columns: list[str] | None = None,
    source_id: str = "test",
) -> SyntheticDataset:
    """Helper to wrap a numpy array as a SyntheticDataset with provenance."""
    return SyntheticDataset(
        data=data,
        columns=columns,
        provenance=Provenance(
            source_id=source_id,
            generator_name="real",
            generator_version="0",
            seed=0,
            created_at="2026-01-01T00:00:00+00:00",
        ),
    )


def _correlated_dataset(
    n: int = 500, seed: int = 0
) -> tuple[SyntheticDataset, np.ndarray]:
    """Build a 3-column dataset with known correlation structure.

    Column A ~ N(0, 1)
    Column B = 0.8 * A + noise  (high positive correlation with A)
    Column C = -0.5 * A + noise (moderate negative correlation with A)

    Returns the dataset and the empirical correlation matrix of the source.
    """
    rng = np.random.default_rng(seed)
    a = rng.standard_normal(n)
    b = 0.8 * a + 0.6 * rng.standard_normal(n)
    c = -0.5 * a + 0.866 * rng.standard_normal(n)
    data = np.column_stack([a, b, c])
    ds = _make_dataset(data, columns=["A", "B", "C"])
    real_corr = np.corrcoef(data, rowvar=False)
    return ds, real_corr


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestProtocolCompliance:
    """GaussianCopulaGenerator satisfies GeneratorProtocol."""

    def test_isinstance_check(self) -> None:
        gen = GaussianCopulaGenerator()
        assert isinstance(gen, GeneratorProtocol)

    def test_has_required_attributes(self) -> None:
        gen = GaussianCopulaGenerator()
        assert gen.name == "gaussian_copula"
        assert isinstance(gen.version, str)


class TestDeterminism:
    """Same seed must produce bit-identical output."""

    def test_same_seed_same_output(self) -> None:
        ds, _ = _correlated_dataset()
        gen1 = GaussianCopulaGenerator()
        gen1.fit(ds)
        out1 = gen1.sample(100, seed=42)

        gen2 = GaussianCopulaGenerator()
        gen2.fit(ds)
        out2 = gen2.sample(100, seed=42)

        np.testing.assert_array_equal(out1.data, out2.data)

    def test_different_seed_different_output(self) -> None:
        ds, _ = _correlated_dataset()
        gen = GaussianCopulaGenerator()
        gen.fit(ds)
        out1 = gen.sample(100, seed=42)
        out2 = gen.sample(100, seed=99)
        # Extremely unlikely to be identical with different seeds.
        assert not np.array_equal(out1.data, out2.data)


class TestCorrelationPreservation:
    """Synthetic correlation matrix should be close to the real one."""

    def test_correlation_within_tolerance(self) -> None:
        ds, real_corr = _correlated_dataset(n=2000, seed=7)
        gen = GaussianCopulaGenerator()
        gen.fit(ds)
        synth = gen.sample(2000, seed=42)
        synth_corr = np.corrcoef(synth.data, rowvar=False)
        # Element-wise difference should be within 0.15.
        diff = np.abs(real_corr - synth_corr)
        assert np.all(diff < 0.15), (
            f"Max correlation difference {diff.max():.4f} exceeds tolerance 0.15.\n"
            f"Real corr:\n{real_corr}\nSynth corr:\n{synth_corr}"
        )


class TestShapePreservation:
    """Output must have the requested row count and original column count."""

    def test_correct_shape(self) -> None:
        ds, _ = _correlated_dataset(n=200)
        gen = GaussianCopulaGenerator()
        gen.fit(ds)
        for n_out in [10, 50, 500]:
            synth = gen.sample(n_out, seed=0)
            assert synth.data.shape == (n_out, 3)

    def test_columns_preserved(self) -> None:
        ds, _ = _correlated_dataset()
        gen = GaussianCopulaGenerator()
        gen.fit(ds)
        synth = gen.sample(50, seed=0)
        assert synth.columns == ["A", "B", "C"]

    def test_provenance_populated(self) -> None:
        ds, _ = _correlated_dataset()
        gen = GaussianCopulaGenerator()
        gen.fit(ds)
        synth = gen.sample(50, seed=7)
        assert synth.provenance is not None
        assert synth.provenance.generator_name == "gaussian_copula"
        assert synth.provenance.seed == 7


class TestEdgeCases:
    """Single column, constant column, NaN column."""

    def test_single_column(self) -> None:
        """Single-column input degenerates to marginal resampling."""
        rng = np.random.default_rng(0)
        data = rng.standard_normal(200).reshape(-1, 1)
        ds = _make_dataset(data, columns=["X"])
        gen = GaussianCopulaGenerator()
        gen.fit(ds)
        synth = gen.sample(100, seed=42)
        assert synth.data.shape == (100, 1)
        # Values should be within the range of the original data (inverse CDF
        # clamps to observed min/max).
        assert synth.data.min() >= data.min() - 1e-6
        assert synth.data.max() <= data.max() + 1e-6

    def test_single_column_no_names(self) -> None:
        """Single column with no column names returns 1-D array."""
        rng = np.random.default_rng(0)
        data = rng.standard_normal(200)
        ds = _make_dataset(data)
        gen = GaussianCopulaGenerator()
        gen.fit(ds)
        synth = gen.sample(100, seed=42)
        # Should be squeezed to 1-D when no column names were given.
        assert synth.data.ndim == 1
        assert len(synth.data) == 100

    def test_constant_column(self) -> None:
        """Constant columns are reproduced as constants."""
        rng = np.random.default_rng(0)
        normal = rng.standard_normal(200)
        const = np.full(200, 42.0)
        data = np.column_stack([normal, const])
        ds = _make_dataset(data, columns=["var", "const"])
        gen = GaussianCopulaGenerator()
        gen.fit(ds)
        synth = gen.sample(100, seed=0)
        # The constant column must remain exactly 42.0.
        np.testing.assert_array_equal(synth.data[:, 1], 42.0)
        # The variable column should have variation.
        assert synth.data[:, 0].std() > 0

    def test_nan_column_raises(self) -> None:
        """NaN in any column should raise ValueError at fit time."""
        data = np.array([[1.0, 2.0], [3.0, np.nan], [5.0, 6.0]])
        ds = _make_dataset(data, columns=["ok", "bad"])
        gen = GaussianCopulaGenerator()
        with pytest.raises(ValueError, match="NaN"):
            gen.fit(ds)

    def test_sample_before_fit_raises(self) -> None:
        gen = GaussianCopulaGenerator()
        with pytest.raises(RuntimeError, match="fit"):
            gen.sample(10, seed=0)
