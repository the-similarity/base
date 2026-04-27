"""Tests for the_similarity/methods/tda_matcher.py.

Covers: compute_persistence, persistence_distance, tda_score, and the
end-to-end compare() wrapper. TDA is an optional Tier 2 enrichment method
that uses ripser/persim; tests skip cleanly when those are not installed.
"""

import numpy as np
import pytest

# Guard: skip the whole module if the optional TDA deps are absent.
ripser = pytest.importorskip("ripser")
pytest.importorskip("persim")

# E402: imports below are intentionally deferred until after the dep-check.
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


def _sine_series(n: int = 200, freq: float = 0.05) -> np.ndarray:
    """Pure sine wave — should produce non-trivial H1 loops when embedded."""
    t = np.arange(n, dtype=np.float64)
    return np.sin(2 * np.pi * freq * t)


def _random_walk(n: int = 200, seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return np.cumsum(rng.standard_normal(n))


def _constant_series(n: int = 200) -> np.ndarray:
    return np.ones(n, dtype=np.float64)


# ---------------------------------------------------------------------------
# compute_persistence
# ---------------------------------------------------------------------------


class TestComputePersistence:
    """Tests for TDA persistence diagram computation."""

    def test_returns_dict_with_h0_h1(self):
        """Output must have 'H0' and 'H1' keys."""
        diag = compute_persistence(_sine_series())
        assert "H0" in diag
        assert "H1" in diag

    def test_h0_h1_are_numpy_arrays(self):
        """H0 and H1 must be numpy arrays."""
        diag = compute_persistence(_sine_series())
        assert isinstance(diag["H0"], np.ndarray)
        assert isinstance(diag["H1"], np.ndarray)

    def test_h0_h1_have_two_columns(self):
        """Each diagram entry must be a birth-death pair (shape (n, 2))."""
        diag = compute_persistence(_sine_series())
        if diag["H0"].size > 0:
            assert diag["H0"].shape[1] == 2
        if diag["H1"].size > 0:
            assert diag["H1"].shape[1] == 2

    def test_short_series_returns_empty_diagrams(self):
        """Series shorter than TDA_MIN_WINDOW must return empty (0, 2) arrays."""
        short = np.arange(TDA_MIN_WINDOW - 1, dtype=np.float64)
        diag = compute_persistence(short)
        assert diag["H0"].shape == (0, 2)
        assert diag["H1"].shape == (0, 2)

    def test_constant_series_returns_empty_diagrams(self):
        """A constant series has trivial topology and must return empty diagrams."""
        diag = compute_persistence(_constant_series(100))
        assert diag["H0"].shape == (0, 2)
        assert diag["H1"].shape == (0, 2)

    def test_h0_no_infinite_deaths(self):
        """H0 diagram must have all finite death values (infinite component is filtered)."""
        diag = compute_persistence(_sine_series())
        if diag["H0"].size > 0:
            assert np.all(np.isfinite(diag["H0"][:, 1])), "Infinite H0 deaths found"

    def test_birth_leq_death_in_h0(self):
        """For all finite H0 pairs, birth <= death (topological invariant)."""
        diag = compute_persistence(_sine_series())
        if diag["H0"].size > 0:
            assert np.all(diag["H0"][:, 0] <= diag["H0"][:, 1])

    def test_custom_dim_lag(self):
        """Custom embedding parameters must not raise."""
        diag = compute_persistence(_sine_series(200), dim=3, lag=5)
        assert "H0" in diag and "H1" in diag


# ---------------------------------------------------------------------------
# persistence_distance
# ---------------------------------------------------------------------------


class TestPersistenceDistance:
    """Tests for the Wasserstein-based distance between diagrams."""

    def test_identical_diagrams_near_zero(self):
        """Same persistence diagram should have distance near 0."""
        diag = compute_persistence(_sine_series())
        dist = persistence_distance(diag, diag)
        assert dist < 0.1, f"Expected distance < 0.1 for identical diagrams, got {dist}"

    def test_distance_non_negative(self):
        """Distance must always be >= 0."""
        diag_a = compute_persistence(_sine_series(200, freq=0.05))
        diag_b = compute_persistence(_random_walk())
        dist = persistence_distance(diag_a, diag_b)
        assert dist >= 0.0, f"Negative distance: {dist}"

    def test_empty_diagrams_zero_distance(self):
        """Both-empty diagrams must give distance 0 without raising."""
        empty = {"H0": np.empty((0, 2)), "H1": np.empty((0, 2))}
        dist = persistence_distance(empty, empty)
        assert dist == 0.0

    def test_different_dynamics_nonzero_distance(self):
        """Sine wave vs random walk should produce a clearly non-zero distance."""
        diag_sine = compute_persistence(_sine_series())
        diag_walk = compute_persistence(_random_walk())
        dist = persistence_distance(diag_sine, diag_walk)
        assert dist > 0.0, "Expected non-zero distance between different dynamics"


# ---------------------------------------------------------------------------
# tda_score
# ---------------------------------------------------------------------------


class TestTdaScore:
    """Tests for the tda_score() distance → similarity mapping."""

    def test_zero_distance_gives_one(self):
        """Distance 0 must map to score 1.0."""
        assert tda_score(0.0) == pytest.approx(1.0)

    def test_score_in_unit_interval(self):
        """Score must be in [0, 1] for any non-negative distance."""
        for dist in [0.0, 0.1, 0.5, 1.0, 5.0, 100.0]:
            s = tda_score(dist)
            assert 0.0 <= s <= 1.0, f"Score {s} out of [0, 1] for distance {dist}"

    def test_score_monotonically_decreasing(self):
        """Larger distance must give smaller score."""
        scores = [tda_score(d) for d in [0.0, 1.0, 5.0, 10.0]]
        assert scores == sorted(scores, reverse=True), (
            f"Scores not monotonically decreasing: {scores}"
        )

    def test_exponential_decay_formula(self):
        """tda_score(d) == exp(-2 * d) by implementation."""
        for d in [0.0, 0.5, 1.0, 2.0]:
            expected = float(np.exp(-2 * d))
            assert tda_score(d) == pytest.approx(expected, rel=1e-9)


# ---------------------------------------------------------------------------
# compare (end-to-end)
# ---------------------------------------------------------------------------


class TestCompare:
    """End-to-end tests for the compare() wrapper."""

    def test_short_series_returns_zero(self):
        """Either series shorter than TDA_MIN_WINDOW must return 0.0."""
        short = np.arange(TDA_MIN_WINDOW - 1, dtype=np.float64)
        assert compare(short, _sine_series()) == 0.0
        assert compare(_sine_series(), short) == 0.0

    def test_constant_both_returns_zero(self):
        """Two constant series produce trivial topology — result is 0.0."""
        c = _constant_series(200)
        score = compare(c, c)
        assert score == 0.0

    def test_score_in_unit_interval(self):
        """compare() must return a value in [0, 1]."""
        pairs = [
            (_sine_series(), _sine_series()),
            (_sine_series(), _random_walk()),
            (_random_walk(seed=0), _random_walk(seed=1)),
        ]
        for a, b in pairs:
            s = compare(a, b)
            assert 0.0 <= s <= 1.0, f"Score {s} out of [0, 1]"

    def test_identical_series_higher_score(self):
        """Same series should score higher than a clearly different one."""
        sig = _sine_series()
        walk = _random_walk()
        score_same = compare(sig, sig)
        score_diff = compare(sig, walk)
        assert score_same >= score_diff, (
            f"Identical ({score_same}) should score >= different ({score_diff})"
        )

    def test_list_inputs_accepted(self):
        """compare() must accept plain Python lists (coerced via np.asarray)."""
        sig = _sine_series().tolist()
        score = compare(sig, sig)
        assert 0.0 <= score <= 1.0

    def test_2d_input_flattened(self):
        """compare() calls .ravel() internally, so a column vector must work."""
        sig = _sine_series().reshape(-1, 1)
        score = compare(sig, sig)
        assert 0.0 <= score <= 1.0

    def test_custom_embedding_params(self):
        """Custom dim and lag values must not raise and must return valid score."""
        sig = _sine_series(250)
        score = compare(sig, sig, dim=3, lag=5)
        assert 0.0 <= score <= 1.0
