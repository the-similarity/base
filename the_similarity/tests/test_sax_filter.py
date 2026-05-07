"""Tests for the_similarity/methods/sax_filter.py.

Covers the full SAX pipeline: PAA downsampling, breakpoint tables,
sax_transform, MINDIST computation, and sax_score. The MINDIST lower-bound
guarantee is the critical invariant that prevents false dismissals in the
Tier 1 pre-filter.
"""

import numpy as np
import pytest

from the_similarity.methods.sax_filter import (
    _breakpoints,
    _build_dist_table,
    _get_dist_table,
    _paa,
    sax_mindist,
    sax_score,
    sax_transform,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _znorm(series: np.ndarray) -> np.ndarray:
    """Z-normalize a series to zero mean and unit std."""
    mu = series.mean()
    sigma = series.std()
    if sigma < 1e-12:
        return series - mu
    return (series - mu) / sigma


def _random_series(n: int = 64, seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return _znorm(rng.standard_normal(n))


# ---------------------------------------------------------------------------
# _breakpoints
# ---------------------------------------------------------------------------


class TestBreakpoints:
    """Tests for the equiprobable Gaussian breakpoints helper."""

    def test_length_is_alphabet_size_minus_one(self):
        """There are (alphabet_size - 1) interior breakpoints."""
        for a in (4, 8, 12):
            bps = _breakpoints(a)
            assert len(bps) == a - 1, f"Expected {a - 1} breakpoints for size {a}"

    def test_breakpoints_sorted_ascending(self):
        """Breakpoints must be strictly increasing (they partition the Gaussian)."""
        for a in (4, 8, 16):
            bps = _breakpoints(a)
            assert np.all(np.diff(bps) > 0), f"Breakpoints not sorted for size {a}"

    def test_breakpoints_symmetric_around_zero(self):
        """Gaussian breakpoints are symmetric: bps[i] == -bps[-(i+1)]."""
        bps = _breakpoints(8)
        for i in range(len(bps) // 2):
            assert bps[i] == pytest.approx(-bps[-(i + 1)], rel=1e-9)


# ---------------------------------------------------------------------------
# _paa
# ---------------------------------------------------------------------------


class TestPaa:
    """Tests for Piecewise Aggregate Approximation."""

    def test_output_length(self):
        """_paa must return an array of length n_segments."""
        series = np.arange(64, dtype=np.float64)
        paa = _paa(series, n_segments=8)
        assert len(paa) == 8

    def test_paa_preserves_mean(self):
        """PAA of constant series should equal that constant."""
        series = np.full(50, 3.7)
        paa = _paa(series, n_segments=5)
        np.testing.assert_allclose(paa, 3.7, atol=1e-12)

    def test_paa_when_segments_exceed_length(self):
        """When n_segments >= n, _paa should return a copy of the series."""
        series = np.array([1.0, 2.0, 3.0])
        paa = _paa(series, n_segments=3)
        np.testing.assert_array_equal(paa, series)

    def test_paa_when_segments_equal_length(self):
        """n_segments == n should be a no-op."""
        series = np.array([1.0, 2.0, 3.0, 4.0])
        paa = _paa(series, n_segments=4)
        np.testing.assert_array_equal(paa, series)


# ---------------------------------------------------------------------------
# _build_dist_table / _get_dist_table
# ---------------------------------------------------------------------------


class TestDistTable:
    """Tests for the symbol-to-symbol lookup table."""

    def test_table_shape(self):
        """Table must be (alphabet_size, alphabet_size)."""
        for a in (4, 8):
            table = _build_dist_table(a)
            assert table.shape == (a, a), f"Expected ({a},{a}), got {table.shape}"

    def test_table_non_negative(self):
        """All distances in the table must be >= 0."""
        table = _build_dist_table(8)
        assert np.all(table >= 0.0)

    def test_diagonal_zero(self):
        """Same symbol must have distance 0."""
        table = _build_dist_table(8)
        assert np.all(np.diag(table) == 0.0)

    def test_adjacent_symbols_zero(self):
        """Adjacent symbols (|i - j| = 1) must have distance 0."""
        table = _build_dist_table(8)
        for i in range(7):
            assert table[i, i + 1] == 0.0, f"Expected 0 for adjacent ({i}, {i + 1})"
            assert table[i + 1, i] == 0.0

    def test_table_symmetric(self):
        """Distance table must be symmetric."""
        table = _build_dist_table(8)
        np.testing.assert_array_equal(table, table.T)

    def test_cache_returns_same_object(self):
        """_get_dist_table should return the cached instance for repeated calls."""
        t1 = _get_dist_table(8)
        t2 = _get_dist_table(8)
        assert t1 is t2, "Repeated calls should return the same cached object"


# ---------------------------------------------------------------------------
# sax_transform
# ---------------------------------------------------------------------------


class TestSaxTransform:
    """Tests for sax_transform()."""

    def test_output_shape(self):
        """Output must have length n_segments."""
        series = _random_series(128)
        result = sax_transform(series, n_segments=16, alphabet_size=8)
        assert result.shape == (16,)

    def test_output_dtype(self):
        """Output dtype must be int8."""
        series = _random_series(64)
        result = sax_transform(series, n_segments=8, alphabet_size=4)
        assert result.dtype == np.int8

    def test_values_in_alphabet_range(self):
        """All symbol values must be in [0, alphabet_size - 1]."""
        for alphabet_size in (4, 8, 12):
            series = _random_series(64)
            result = sax_transform(series, n_segments=8, alphabet_size=alphabet_size)
            assert result.min() >= 0
            assert result.max() < alphabet_size

    def test_identical_series_same_sax(self):
        """The same input series must produce the same SAX representation."""
        series = _random_series(100)
        sax_a = sax_transform(series, n_segments=16, alphabet_size=8)
        sax_b = sax_transform(series.copy(), n_segments=16, alphabet_size=8)
        np.testing.assert_array_equal(sax_a, sax_b)

    def test_different_n_segments(self):
        """Different n_segments values must produce output of the correct length."""
        series = _random_series(128)
        for n_seg in (8, 16, 32):
            result = sax_transform(series, n_segments=n_seg, alphabet_size=8)
            assert result.shape == (n_seg,)


# ---------------------------------------------------------------------------
# sax_mindist
# ---------------------------------------------------------------------------


class TestSaxMindist:
    """Tests for the MINDIST lower-bound guarantee."""

    def test_identical_sax_zero_mindist(self):
        """Same SAX representation must have MINDIST = 0."""
        series = _random_series(64)
        sax = sax_transform(series, n_segments=8, alphabet_size=8)
        assert sax_mindist(sax, sax, original_length=64, alphabet_size=8) == 0.0

    def test_mindist_non_negative(self):
        """MINDIST must always be >= 0."""
        rng = np.random.default_rng(50)
        for _ in range(30):
            a = _znorm(rng.standard_normal(64))
            b = _znorm(rng.standard_normal(64))
            sax_a = sax_transform(a, n_segments=8, alphabet_size=8)
            sax_b = sax_transform(b, n_segments=8, alphabet_size=8)
            md = sax_mindist(sax_a, sax_b, original_length=64, alphabet_size=8)
            assert md >= 0.0, f"Negative MINDIST {md}"

    def test_mindist_lower_bounds_euclidean(self):
        """MINDIST must never exceed the true Euclidean distance (no false dismissals)."""
        rng = np.random.default_rng(77)
        n, n_segments = 64, 8
        for _ in range(50):
            a = _znorm(rng.standard_normal(n))
            b = _znorm(rng.standard_normal(n))
            sax_a = sax_transform(a, n_segments=n_segments, alphabet_size=8)
            sax_b = sax_transform(b, n_segments=n_segments, alphabet_size=8)
            md = sax_mindist(sax_a, sax_b, original_length=n, alphabet_size=8)
            euclid = float(np.linalg.norm(a - b))
            assert md <= euclid + 1e-9, (
                f"MINDIST {md} exceeded Euclidean {euclid} (false dismissal!)"
            )

    def test_mindist_symmetric(self):
        """MINDIST(A, B) must equal MINDIST(B, A)."""
        rng = np.random.default_rng(33)
        a = _znorm(rng.standard_normal(64))
        b = _znorm(rng.standard_normal(64))
        sax_a = sax_transform(a, n_segments=8, alphabet_size=8)
        sax_b = sax_transform(b, n_segments=8, alphabet_size=8)
        md_ab = sax_mindist(sax_a, sax_b, original_length=64, alphabet_size=8)
        md_ba = sax_mindist(sax_b, sax_a, original_length=64, alphabet_size=8)
        assert md_ab == pytest.approx(md_ba, rel=1e-9)

    def test_alphabet_size_4_mindist(self):
        """MINDIST must work correctly for a non-default alphabet_size."""
        rng = np.random.default_rng(88)
        a = _znorm(rng.standard_normal(64))
        b = _znorm(rng.standard_normal(64))
        sax_a = sax_transform(a, n_segments=8, alphabet_size=4)
        sax_b = sax_transform(b, n_segments=8, alphabet_size=4)
        md = sax_mindist(sax_a, sax_b, original_length=64, alphabet_size=4)
        assert md >= 0.0


# ---------------------------------------------------------------------------
# sax_score
# ---------------------------------------------------------------------------


class TestSaxScore:
    """Tests for the sax_score() MINDIST → similarity conversion."""

    def test_zero_mindist_gives_score_one(self):
        """MINDIST 0 must map to score 1.0."""
        assert sax_score(0.0, 100) == pytest.approx(1.0)

    def test_score_in_unit_interval(self):
        """Score must be in [0, 1] for any non-negative MINDIST."""
        for mindist in [0.0, 0.5, 1.0, 5.0, 50.0, 500.0]:
            s = sax_score(mindist, 100)
            assert 0.0 <= s <= 1.0, f"Score {s} out of [0, 1] for mindist {mindist}"

    def test_score_decreases_with_mindist(self):
        """Larger MINDIST must produce smaller score."""
        scores = [sax_score(md, 100) for md in [0.0, 1.0, 5.0, 20.0]]
        assert scores == sorted(scores, reverse=True), (
            f"Scores not monotonically decreasing: {scores}"
        )

    def test_window_size_normalization(self):
        """Fixed MINDIST should produce lower score for a shorter window
        because the normalized distance is larger."""
        s_short = sax_score(5.0, 20)
        s_long = sax_score(5.0, 200)
        assert s_short < s_long

    def test_window_size_zero_guard(self):
        """window_size=0 should not raise (clamped to 1 inside the function)."""
        s = sax_score(1.0, 0)
        assert 0.0 <= s <= 1.0
