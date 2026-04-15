"""Tests for the block-bootstrap copies generators.

Covers determinism (same seed → identical output), provenance completeness,
protocol conformance, shape/column handling for univariate + multiseries,
and the regime-aware variant's fallback bookkeeping.
"""
from __future__ import annotations

import numpy as np
import pytest

from the_similarity.synthetic import (
    GeneratorProtocol,
    Provenance,
    SyntheticDataset,
    iso_now,
)
from the_similarity.synthetic.copies import (
    BlockBootstrapGenerator,
    RegimeBlockBootstrapGenerator,
)


def _make_real(n: int = 500, d: int = 1, seed: int = 0) -> SyntheticDataset:
    rng = np.random.default_rng(seed)
    arr = rng.standard_normal((n, d)).cumsum(axis=0)
    if d == 1:
        arr = arr.reshape(-1)
    cols = [f"s{i}" for i in range(d)] if d > 1 else None
    return SyntheticDataset(
        data=arr,
        columns=cols,
        provenance=Provenance(
            source_id="unit-test",
            generator_name="real",
            generator_version="1.0.0",
            seed=seed,
            created_at=iso_now(),
        ),
    )


# ---------------------------------------------------------------------------
# Protocol conformance
# ---------------------------------------------------------------------------


def test_block_bootstrap_satisfies_protocol():
    assert isinstance(BlockBootstrapGenerator(block_len=5), GeneratorProtocol)


def test_regime_block_bootstrap_satisfies_protocol():
    assert isinstance(
        RegimeBlockBootstrapGenerator(block_len=5, vol_window=5),
        GeneratorProtocol,
    )


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


def test_block_bootstrap_is_deterministic_under_same_seed():
    real = _make_real()
    gen = BlockBootstrapGenerator(block_len=20)
    gen.fit(real)
    a = gen.sample(200, seed=42)
    b = gen.sample(200, seed=42)
    assert np.array_equal(a.data, b.data)


def test_block_bootstrap_different_seeds_differ():
    real = _make_real()
    gen = BlockBootstrapGenerator(block_len=20)
    gen.fit(real)
    a = gen.sample(200, seed=1)
    b = gen.sample(200, seed=2)
    assert not np.array_equal(a.data, b.data)


def test_regime_block_bootstrap_is_deterministic_under_same_seed():
    real = _make_real()
    gen = RegimeBlockBootstrapGenerator(block_len=15, vol_window=10)
    gen.fit(real)
    a = gen.sample(150, seed=99)
    b = gen.sample(150, seed=99)
    assert np.array_equal(a.data, b.data)


# ---------------------------------------------------------------------------
# Shape / columns
# ---------------------------------------------------------------------------


def test_univariate_output_is_1d():
    real = _make_real(n=300, d=1)
    gen = BlockBootstrapGenerator(block_len=10)
    gen.fit(real)
    out = gen.sample(75, seed=0)
    assert out.data.ndim == 1
    assert out.data.shape[0] == 75


def test_multiseries_preserves_columns_and_shape():
    real = _make_real(n=400, d=4)
    gen = BlockBootstrapGenerator(block_len=10)
    gen.fit(real)
    out = gen.sample(120, seed=0)
    assert out.data.shape == (120, 4)
    assert out.columns == ["s0", "s1", "s2", "s3"]


def test_sample_values_come_from_real_series():
    real = _make_real(n=200, d=1)
    real_arr = np.asarray(real.data)
    gen = BlockBootstrapGenerator(block_len=25)
    gen.fit(real)
    out = gen.sample(100, seed=7)
    # Every synthetic value must be present in the real series — block
    # bootstrap is a pure resampling operation, no interpolation.
    assert np.all(np.isin(out.data, real_arr))


# ---------------------------------------------------------------------------
# Provenance
# ---------------------------------------------------------------------------


def test_block_bootstrap_provenance_is_complete():
    real = _make_real()
    gen = BlockBootstrapGenerator(block_len=12)
    gen.fit(real)
    out = gen.sample(80, seed=314)
    p = out.provenance
    assert p is not None
    assert p.generator_name == "block_bootstrap"
    assert p.generator_version == "0.1.0"
    assert p.seed == 314
    assert p.source_id == "unit-test"
    assert p.params == {"block_len": 12, "n": 80}
    assert p.created_at  # non-empty ISO string


def test_regime_bootstrap_provenance_records_params():
    real = _make_real()
    gen = RegimeBlockBootstrapGenerator(
        block_len=10, vol_window=15, vol_quantile=0.6
    )
    gen.fit(real)
    out = gen.sample(50, seed=2)
    assert out.provenance is not None
    params = out.provenance.params
    assert params["block_len"] == 10
    assert params["vol_window"] == 15
    assert params["vol_quantile"] == 0.6
    assert params["method"] == "rolling_vol"
    assert "regime_fallback" in params


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def test_block_len_must_be_positive():
    with pytest.raises(ValueError):
        BlockBootstrapGenerator(block_len=0)


def test_sample_before_fit_raises():
    gen = BlockBootstrapGenerator(block_len=5)
    with pytest.raises(RuntimeError):
        gen.sample(10, seed=0)


def test_block_len_larger_than_series_raises():
    real = _make_real(n=10)
    gen = BlockBootstrapGenerator(block_len=50)
    with pytest.raises(ValueError):
        gen.fit(real)


def test_regime_rejects_unknown_method():
    with pytest.raises(ValueError):
        RegimeBlockBootstrapGenerator(block_len=5, method="kmeans_returns")


def test_regime_rejects_bad_quantile():
    with pytest.raises(ValueError):
        RegimeBlockBootstrapGenerator(block_len=5, vol_quantile=1.5)
