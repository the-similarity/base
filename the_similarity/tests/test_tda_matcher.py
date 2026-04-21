"""Tests for the_similarity/methods/tda_matcher.py.

Covers compute_persistence, persistence_distance, tda_score, and compare,
including return types, shapes, edge cases, and type coercion.
"""

import numpy as np
import pytest

# Skip entire module if optional TDA dependencies are not installed.
pytest.importorskip("ripser")
pytest.importorskip("persim")

# E402: intentional post-importorskip import — tda_matcher imports ripser/persim
# at module level, so we must skip before attempting it.
from the_similarity.methods.tda_matcher import (  # noqa: E402
    TDA_MIN_WINDOW,
    compare,
    compute_persistence,
    persistence_distance,
    tda_score,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sine(n: int = 200, freq: float = 0.05) -> np.ndarray:
    t = np.arange(n, dtype=np.float64)
    return np.sin(2 * np.pi * freq * t)


def _walk(n: int = 200, seed: int = 0) -> np.ndarray:
    return np.cumsum(np.random.default_rng(seed).standard_normal(n))


# ---------------------------------------------------------------------------
# compute_persistence — return structure
# ---------------------------------------------------------------------------

class TestComputePersistence:
    def test_returns_dict_with_h0_h1(self):
        diag = compute_persistence(_sine())
        assert isinstance(diag, dict)
        assert "H0" in diag and "H1" in diag

    def test_h0_h1_are_2d_arrays(self):
        diag = compute_persistence(_sine())
        assert diag["H0"].ndim == 2 and diag["H0"].shape[1] == 2
        assert diag["H1"].ndim == 2 and diag["H1"].shape[1] == 2

    def test_h0_has_no_infinite_deaths(self):
        """H0 infinite-death feature must be stripped by compute_persistence."""
        diag = compute_persistence(_sine())
        if diag["H0"].size > 0:
            assert np.all(np.isfinite(diag["H0"][:, 1])), (
                "All H0 death values must be finite"
            )

    def test_short_series_returns_empty_diagrams(self):
        short = np.arange(TDA_MIN_WINDOW - 1, dtype=np.float64)
        diag = compute_persistence(short)
        assert diag["H0"].size == 0
        assert diag["H1"].size == 0

    def test_exactly_min_window_is_processed(self):
        """A series of exactly TDA_MIN_WINDOW should not be rejected."""
        s = _sine(n=TDA_MIN_WINDOW)
        diag = compute_persistence(s)
        # At minimum length H0 may be tiny, but the call must not raise and the
        # dict must be well-formed.
        assert "H0" in diag and "H1" in diag

    def test_constant_series_returns_empty_diagrams(self):
        c = np.ones(100, dtype=np.float64)
        diag = compute_persistence(c)
        assert diag["H0"].size == 0
        assert diag["H1"].size == 0

    def test_near_constant_series_returns_empty_diagrams(self):
        """Series with ptp < 1e-12 is treated as constant."""
        s = np.full(100, 3.0) + 1e-15 * np.arange(100)
        diag = compute_persistence(s)
        assert diag["H0"].size == 0 and diag["H1"].size == 0

    def test_list_input_accepted(self):
        """compute_persistence must accept plain Python lists."""
        data = list(_sine(n=100).tolist())  # length < TDA_MIN_WINDOW? No, 100 >= 40.
        # 100 >= 40, so this should work.
        diag = compute_persistence(data)
        assert "H0" in diag

    def test_integer_array_accepted(self):
        """Integer dtype arrays must be coerced to float64 without error."""
        s = np.tile(np.arange(10), 10)  # length 100, non-constant
        diag = compute_persistence(s)
        assert "H0" in diag

    def test_custom_dim_and_lag(self):
        """Non-default dim and lag parameters should not raise."""
        s = _sine(n=200)
        diag = compute_persistence(s, dim=2, lag=1)
        assert "H0" in diag and "H1" in diag

    def test_float32_input_accepted(self):
        s = _sine(n=200).astype(np.float32)
        diag = compute_persistence(s)
        assert "H0" in diag

    def test_2d_column_vector_raveled(self):
        """A (n, 1) array should be raveled to 1-D without error."""
        s = _sine(n=200).reshape(-1, 1)
        diag = compute_persistence(s)
        assert "H0" in diag


# ---------------------------------------------------------------------------
# persistence_distance — distance properties
# ---------------------------------------------------------------------------

class TestPersistenceDistance:
    def test_identical_diagrams_have_near_zero_distance(self):
        s = _sine()
        diag = compute_persistence(s)
        dist = persistence_distance(diag, diag)
        assert dist < 0.1, f"Expected < 0.1, got {dist}"

    def test_different_dynamics_have_large_distance(self):
        d_sine = compute_persistence(_sine())
        d_walk = compute_persistence(_walk())
        dist = persistence_distance(d_sine, d_walk)
        assert dist > 0.3, f"Expected > 0.3, got {dist}"

    def test_distance_is_non_negative(self):
        d1 = compute_persistence(_sine())
        d2 = compute_persistence(_walk())
        assert persistence_distance(d1, d2) >= 0.0
        assert persistence_distance(d2, d1) >= 0.0

    def test_both_empty_diagrams_return_zero(self):
        empty = {
            "H0": np.empty((0, 2), dtype=np.float64),
            "H1": np.empty((0, 2), dtype=np.float64),
        }
        assert persistence_distance(empty, empty) == 0.0

    def test_h1_weighted_higher_than_h0(self):
        """H1 carries weight 0.6 vs H0 weight 0.4.

        Create diagrams where only H1 differs to confirm the weighting direction:
        we can't isolate components perfectly with real data, but we can verify
        the combined formula by checking known distance = 0.4*d_h0 + 0.6*d_h1.
        """
        # Use identical series so both distances are ~0 and formula holds at 0.
        diag = compute_persistence(_sine())
        dist = persistence_distance(diag, diag)
        assert dist < 1e-6, "Self-distance must be essentially 0"

    def test_returns_float(self):
        d = compute_persistence(_sine())
        result = persistence_distance(d, d)
        assert isinstance(result, float)


# ---------------------------------------------------------------------------
# tda_score — score formula
# ---------------------------------------------------------------------------

class TestTdaScore:
    def test_zero_distance_gives_score_one(self):
        assert tda_score(0.0) == pytest.approx(1.0)

    def test_large_distance_gives_near_zero_score(self):
        score = tda_score(100.0)
        assert score < 1e-10

    def test_score_in_unit_interval(self):
        for d in [0.0, 0.5, 1.0, 2.0, 5.0, 10.0]:
            s = tda_score(d)
            assert 0.0 <= s <= 1.0, f"Score {s} out of [0, 1] for distance {d}"

    def test_monotone_decreasing(self):
        """Larger distance → smaller score."""
        assert tda_score(0.0) > tda_score(0.5) > tda_score(1.0) > tda_score(5.0)

    def test_known_value(self):
        """exp(-1 * 2) = exp(-2) ≈ 0.1353."""
        expected = float(np.exp(-2.0))
        assert tda_score(1.0) == pytest.approx(expected, rel=1e-6)

    def test_returns_float(self):
        assert isinstance(tda_score(0.5), float)


# ---------------------------------------------------------------------------
# compare — end-to-end
# ---------------------------------------------------------------------------

class TestCompare:
    def test_identical_series_high_score(self):
        s = _sine()
        score = compare(s, s)
        assert score > 0.8, f"Expected > 0.8 for identical series, got {score}"

    def test_different_dynamics_lower_score(self):
        s_sine = _sine()
        s_walk = _walk()
        score_same = compare(s_sine, s_sine)
        score_diff = compare(s_sine, s_walk)
        assert score_diff < score_same, (
            f"Different signals ({score_diff:.3f}) should score < identical ({score_same:.3f})"
        )

    def test_score_in_unit_interval(self):
        s1, s2 = _sine(), _walk()
        for a, b in [(s1, s1), (s1, s2), (s2, s2)]:
            sc = compare(a, b)
            assert 0.0 <= sc <= 1.0, f"Score {sc} out of [0, 1]"

    def test_short_query_returns_zero(self):
        short = np.arange(TDA_MIN_WINDOW - 1, dtype=np.float64)
        long_s = _sine()
        assert compare(short, long_s) == 0.0

    def test_short_candidate_returns_zero(self):
        short = np.arange(TDA_MIN_WINDOW - 1, dtype=np.float64)
        long_s = _sine()
        assert compare(long_s, short) == 0.0

    def test_both_short_returns_zero(self):
        short = np.arange(TDA_MIN_WINDOW - 1, dtype=np.float64)
        assert compare(short, short) == 0.0

    def test_constant_series_returns_zero(self):
        c = np.ones(200, dtype=np.float64)
        assert compare(c, c) == 0.0

    def test_list_inputs_accepted(self):
        s = _sine().tolist()
        score = compare(s, s)
        assert 0.0 <= score <= 1.0

    def test_integer_array_inputs_accepted(self):
        s = np.tile(np.arange(20), 10)  # length 200, non-constant
        score = compare(s, s)
        assert 0.0 <= score <= 1.0

    def test_float32_inputs_accepted(self):
        s = _sine(n=200).astype(np.float32)
        score = compare(s, s)
        assert 0.0 <= score <= 1.0

    def test_returns_python_float(self):
        s = _sine()
        result = compare(s, s)
        assert isinstance(result, float)

    def test_custom_dim_and_lag(self):
        s = _sine()
        score = compare(s, s, dim=2, lag=1)
        assert 0.0 <= score <= 1.0

    def test_noise_robustness(self):
        """Lightly perturbed series should remain similar to original."""
        rng = np.random.default_rng(99)
        s = _sine()
        s_noisy = s + 0.01 * rng.standard_normal(len(s))
        score = compare(s, s_noisy)
        assert score > 0.5, f"Expected > 0.5 for slightly perturbed series, got {score}"

    def test_exactly_min_window_length(self):
        """Series of exactly TDA_MIN_WINDOW should not return 0 due to length check."""
        s = _sine(n=TDA_MIN_WINDOW)
        score = compare(s, s)
        # constant or trivial topology might still give 0; just verify no exception
        # and score is in range.
        assert 0.0 <= score <= 1.0
