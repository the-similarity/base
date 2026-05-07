"""Tests for the_similarity/methods/matrix_profile_filter.py.

Covers the pure-numpy MASS implementation: sliding dot product, distance
profile computation, per-position score conversion, and the full profile
→ score array transform.
"""

import numpy as np
import pytest

from the_similarity.methods.matrix_profile_filter import (
    _sliding_dot_product,
    mp_score,
    mp_score_profile,
    query_profile,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_history_with_pattern(
    n: int = 500,
    m: int = 40,
    embed_pos: int = 200,
    seed: int = 42,
) -> tuple[np.ndarray, np.ndarray]:
    """Return (history, pattern) with the pattern embedded at embed_pos."""
    rng = np.random.default_rng(seed)
    history = rng.standard_normal(n)
    pattern = np.sin(np.linspace(0, 4 * np.pi, m))
    history[embed_pos : embed_pos + m] = pattern
    return history, pattern


# ---------------------------------------------------------------------------
# _sliding_dot_product
# ---------------------------------------------------------------------------


class TestSlidingDotProduct:
    """Low-level tests for the FFT-based sliding dot product."""

    def test_output_length(self):
        """Output length must be len(ts) - len(query) + 1."""
        n, m = 200, 30
        rng = np.random.default_rng(0)
        ts = rng.standard_normal(n)
        q = rng.standard_normal(m)
        out = _sliding_dot_product(q, ts)
        assert len(out) == n - m + 1, f"Expected {n - m + 1}, got {len(out)}"

    def test_exact_dot_at_known_position(self):
        """At position where ts matches query exactly, dot product should be
        maximised and close to np.dot(query, query)."""
        rng = np.random.default_rng(1)
        n = 100
        ts = rng.standard_normal(n)
        q = ts[30:50].copy()  # take slice, embed it back

        out = _sliding_dot_product(q, ts)
        # Position 30 corresponds to index 30 in the output
        expected = float(np.dot(q, q))
        assert abs(out[30] - expected) < 1e-6, (
            f"Dot at embed position: expected {expected}, got {out[30]}"
        )

    def test_output_is_numpy_array(self):
        """Return type must be numpy ndarray."""
        rng = np.random.default_rng(2)
        out = _sliding_dot_product(rng.standard_normal(10), rng.standard_normal(50))
        assert isinstance(out, np.ndarray)


# ---------------------------------------------------------------------------
# query_profile
# ---------------------------------------------------------------------------


class TestQueryProfile:
    """Tests for the full z-normalized distance profile."""

    def test_output_length(self):
        """Distance profile length must be len(history) - len(query) + 1."""
        rng = np.random.default_rng(5)
        history = rng.standard_normal(300)
        query = rng.standard_normal(40)
        distances = query_profile(history, query)
        assert len(distances) == 300 - 40 + 1

    def test_distances_non_negative(self):
        """All distances must be >= 0 (clamped internally)."""
        rng = np.random.default_rng(6)
        history = rng.standard_normal(200)
        query = rng.standard_normal(30)
        distances = query_profile(history, query)
        assert np.all(distances >= 0.0), f"Negative distances found: {distances.min()}"

    def test_embedded_pattern_has_minimum_distance(self):
        """The position where a pattern is embedded should have the smallest distance."""
        history, pattern = _make_history_with_pattern(
            n=500, m=40, embed_pos=200, seed=42
        )
        distances = query_profile(history, pattern)
        best_pos = int(np.argmin(distances))
        assert best_pos == 200, f"Expected minimum at position 200, got {best_pos}"

    def test_self_distance_near_zero(self):
        """Extracting the embedded subsequence and querying against the history
        that contains it should yield a near-zero distance at that position."""
        rng = np.random.default_rng(7)
        history = rng.standard_normal(300)
        m = 40
        # Use a slice from the history as the query
        pos = 100
        query = history[pos : pos + m].copy()
        distances = query_profile(history, query)
        assert distances[pos] < 0.05, (
            f"Self-distance expected near 0, got {distances[pos]}"
        )

    def test_list_inputs_accepted(self):
        """query_profile should accept plain Python lists (converted via np.asarray)."""
        rng = np.random.default_rng(8)
        history = rng.standard_normal(100).tolist()
        query = rng.standard_normal(15).tolist()
        distances = query_profile(history, query)
        assert len(distances) == 100 - 15 + 1

    def test_constant_query_does_not_raise(self):
        """A constant (zero-std) query should not raise — std is clamped to 1e-10."""
        rng = np.random.default_rng(9)
        history = rng.standard_normal(100)
        query = np.ones(20)
        distances = query_profile(history, query)
        assert len(distances) == 100 - 20 + 1
        assert np.all(np.isfinite(distances))


# ---------------------------------------------------------------------------
# mp_score
# ---------------------------------------------------------------------------


class TestMpScore:
    """Tests for mp_score() — scalar distance → scalar similarity."""

    def test_zero_distance_gives_score_one(self):
        """Distance 0 must yield score 1.0."""
        assert mp_score(0.0, 40) == pytest.approx(1.0)

    def test_score_in_unit_interval(self):
        """Score must always be in [0, 1]."""
        for distance in [0.0, 0.5, 1.0, 5.0, 20.0, 100.0]:
            s = mp_score(distance, 40)
            assert 0.0 <= s <= 1.0, f"Score {s} out of [0, 1] for distance {distance}"

    def test_score_decreases_with_distance(self):
        """Larger distance must produce a smaller score."""
        scores = [mp_score(d, 40) for d in [0.0, 1.0, 5.0, 20.0]]
        assert scores == sorted(scores, reverse=True), (
            f"Scores not monotonically decreasing: {scores}"
        )

    def test_sqrt_window_normalization(self):
        """Score uses sqrt(window_size) denominator, so a larger window should
        produce a higher score for the same raw distance."""
        # distance / sqrt(window) is smaller for larger windows
        s_small = mp_score(5.0, 16)
        s_large = mp_score(5.0, 256)
        assert s_small < s_large, (
            f"Larger window should give higher score; small={s_small}, large={s_large}"
        )


# ---------------------------------------------------------------------------
# mp_score_profile
# ---------------------------------------------------------------------------


class TestMpScoreProfile:
    """Tests for mp_score_profile() — distance array → score array."""

    def test_output_shape_preserved(self):
        """Output length must equal input length."""
        rng = np.random.default_rng(10)
        distances = np.abs(rng.standard_normal(200))
        scores = mp_score_profile(distances, window_size=40)
        assert len(scores) == 200

    def test_scores_in_unit_interval(self):
        """All scores must be in [0, 1]."""
        rng = np.random.default_rng(11)
        distances = np.abs(rng.standard_normal(100))
        scores = mp_score_profile(distances, window_size=30)
        assert scores.min() >= 0.0
        assert scores.max() <= 1.0

    def test_zero_distances_give_score_one(self):
        """Zero distance entries must map to score exactly 1.0."""
        distances = np.array([0.0, 1.0, 0.0, 2.0])
        scores = mp_score_profile(distances, window_size=40)
        assert scores[0] == pytest.approx(1.0)
        assert scores[2] == pytest.approx(1.0)

    def test_ordering_preserved(self):
        """Position with the smallest distance must have the largest score."""
        rng = np.random.default_rng(12)
        distances = np.abs(rng.standard_normal(150))
        scores = mp_score_profile(distances, window_size=40)
        best_score_pos = int(np.argmax(scores))
        best_dist_pos = int(np.argmin(distances))
        assert best_score_pos == best_dist_pos, (
            f"Best score at {best_score_pos}, best distance at {best_dist_pos}"
        )

    def test_end_to_end_ranking(self):
        """Top-ranked position by score profile must match embedded pattern position."""
        history, pattern = _make_history_with_pattern(
            n=500, m=40, embed_pos=200, seed=42
        )
        distances = query_profile(history, pattern)
        scores = mp_score_profile(distances, window_size=len(pattern))
        best_pos = int(np.argmax(scores))
        assert best_pos == 200, f"Expected best score at position 200, got {best_pos}"
