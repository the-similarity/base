import numpy as np
import pytest

from the_similarity.core.normalizer import (
    normalize,
    normalize_pair,
    METHOD_NORM_DEFAULTS,
)


def test_zscore_basic():
    s = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    result = normalize(s, "zscore")
    assert abs(result.mean()) < 1e-10
    assert abs(result.std() - 1.0) < 1e-10


def test_zscore_constant():
    s = np.array([5.0, 5.0, 5.0])
    result = normalize(s, "zscore")
    np.testing.assert_array_equal(result, [0.0, 0.0, 0.0])


def test_minmax():
    s = np.array([10.0, 20.0, 30.0])
    result = normalize(s, "minmax")
    np.testing.assert_allclose(result, [0.0, 0.5, 1.0])


def test_minmax_constant():
    s = np.array([7.0, 7.0, 7.0])
    result = normalize(s, "minmax")
    np.testing.assert_array_equal(result, [0.0, 0.0, 0.0])


def test_logreturn():
    s = np.array([100.0, 110.0, 121.0])
    result = normalize(s, "logreturn")
    assert len(result) == 2
    np.testing.assert_allclose(result, np.diff(np.log(s)), atol=1e-10)


def test_logreturn_zscore():
    s = np.array([100.0, 110.0, 105.0, 115.0, 108.0])
    result = normalize(s, "logreturn_zscore")
    # Length reduced by 1 (logreturn), then z-scored
    assert len(result) == 4
    assert abs(result.mean()) < 1e-10
    assert abs(result.std() - 1.0) < 1e-10


def test_raw():
    s = np.array([1.0, 2.0, 3.0])
    result = normalize(s, "raw")
    np.testing.assert_array_equal(result, s)
    # Should be a copy, not a view
    result[0] = 999.0
    assert s[0] == 1.0


def test_unknown_method():
    with pytest.raises(ValueError, match="Unknown"):
        normalize(np.array([1.0, 2.0]), "foobar")


def test_normalize_pair():
    q = np.array([100.0, 110.0, 105.0, 115.0])
    c = np.array([200.0, 220.0, 210.0, 230.0])
    qn, cn = normalize_pair(q, c, "logreturn_zscore")
    # Both should have same length
    assert len(qn) == len(cn) == 3
    # Both z-scored independently
    assert abs(qn.mean()) < 1e-10
    assert abs(cn.mean()) < 1e-10


def test_method_norm_defaults_exist():
    """All key methods should have normalization defaults."""
    required = ["dtw", "pearson", "bempedelis", "koopman", "emd", "tda"]
    for method in required:
        assert method in METHOD_NORM_DEFAULTS
