"""Tests for the_similarity/methods/dtw_matcher.py.

Covers DTW distance computation, score conversion, batch processing,
and candidate ranking. Uses the Sakoe-Chiba band constraint throughout
to mirror real pipeline usage.
"""

import numpy as np
import pytest

from the_similarity.methods.dtw_matcher import (
    batch_dtw_scores,
    dtw_distance,
    dtw_score,
    rank_candidates,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _sine(n: int = 80, freq: float = 0.1, seed: int = 0) -> np.ndarray:
    """Return a sine-wave series of length n with tiny noise."""
    rng = np.random.default_rng(seed)
    t = np.arange(n, dtype=np.float64)
    return np.sin(2 * np.pi * freq * t) + 1e-6 * rng.standard_normal(n)


def _random_walk(n: int = 80, seed: int = 99) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return np.cumsum(rng.standard_normal(n))


# ---------------------------------------------------------------------------
# dtw_distance
# ---------------------------------------------------------------------------


class TestDtwDistance:
    """Unit tests for dtw_distance()."""

    def test_identical_series_zero_distance(self):
        """Two identical series must produce distance exactly 0."""
        series = _sine(80)
        dist = dtw_distance(series, series)
        assert dist == 0.0, f"Identical series should have distance 0, got {dist}"

    def test_distance_non_negative(self):
        """DTW distance must always be >= 0."""
        a = _sine(60, seed=1)
        b = _random_walk(60, seed=2)
        dist = dtw_distance(a, b)
        assert dist >= 0.0, f"Distance must be non-negative, got {dist}"

    def test_similar_series_lower_distance_than_different(self):
        """Segments from the same process should be closer than unrelated signals."""
        base = _sine(200, seed=0)
        seg_a = base[:80]
        seg_b = base[40:120]  # overlapping, same dynamics
        unrelated = _random_walk(80, seed=77)

        dist_similar = dtw_distance(seg_a, seg_b)
        dist_different = dtw_distance(seg_a, unrelated)
        assert dist_similar < dist_different, (
            f"Expected dist_similar ({dist_similar}) < dist_different ({dist_different})"
        )

    def test_sakoe_chiba_radius_accepted(self):
        """Passing sakoe_chiba_radius should not raise and returns a non-negative float."""
        a = _sine(50, seed=0)
        b = _sine(50, seed=1)
        dist = dtw_distance(a, b, sakoe_chiba_radius=5)
        assert isinstance(dist, float)
        assert dist >= 0.0

    def test_float32_input_handled(self):
        """float32 inputs should be coerced to float64 without error."""
        a = _sine(40).astype(np.float32)
        b = _sine(40, seed=3).astype(np.float32)
        # dtaidistance requires float64 — the function must handle the cast
        dist = dtw_distance(a, b)
        assert dist >= 0.0


# ---------------------------------------------------------------------------
# dtw_score
# ---------------------------------------------------------------------------


class TestDtwScore:
    """Unit tests for dtw_score()."""

    def test_zero_distance_gives_score_one(self):
        """Distance = 0 should produce score exactly 1.0."""
        assert dtw_score(0.0, 100) == 1.0

    def test_score_in_unit_interval(self):
        """Score must always be in [0, 1] for arbitrary distances."""
        for dist in [0.0, 0.1, 1.0, 10.0, 100.0, 1_000.0]:
            s = dtw_score(dist, 80)
            assert 0.0 <= s <= 1.0, f"Score {s} out of [0, 1] for distance {dist}"

    def test_score_decreases_with_distance(self):
        """Score must be strictly decreasing as distance increases."""
        scores = [dtw_score(d, 80) for d in [0.0, 1.0, 5.0, 20.0]]
        assert scores == sorted(scores, reverse=True), (
            f"Scores not monotonically decreasing: {scores}"
        )

    def test_window_size_normalization(self):
        """A fixed distance should produce different scores for different window sizes
        because the score is normalized by window_size."""
        # Longer window → smaller normalized distance → higher score
        s_short = dtw_score(10.0, 20)
        s_long = dtw_score(10.0, 200)
        assert s_short < s_long, (
            "Score should be lower for short windows (distance/window is larger)"
        )

    def test_window_size_zero_guard(self):
        """window_size=0 must not raise ZeroDivisionError (clamped to 1)."""
        # The implementation uses max(window_size, 1), so 0 is safe
        s = dtw_score(1.0, 0)
        assert 0.0 <= s <= 1.0


# ---------------------------------------------------------------------------
# batch_dtw_scores
# ---------------------------------------------------------------------------


class TestBatchDtwScores:
    """Unit tests for batch_dtw_scores()."""

    def test_empty_candidates_returns_empty_list(self):
        """Empty candidates list must return []."""
        query = np.ones(20)
        result = batch_dtw_scores(query, [])
        assert result == [], f"Expected [], got {result}"

    def test_single_candidate_matches_sequential(self):
        """Single-candidate batch must match sequential dtw_score."""
        query = _sine(50, seed=0)
        cand = _sine(50, seed=1)
        batch = batch_dtw_scores(query, [cand])
        seq_dist = dtw_distance(query, cand)
        seq_score = dtw_score(seq_dist, len(query))
        assert abs(batch[0] - seq_score) < 1e-9, (
            f"Batch {batch[0]} != sequential {seq_score}"
        )

    def test_all_scores_in_unit_interval(self):
        """Every score returned by batch must be in [0, 1]."""
        rng = np.random.default_rng(12)
        query = rng.standard_normal(60)
        candidates = [rng.standard_normal(60) for _ in range(15)]
        scores = batch_dtw_scores(query, candidates)
        assert len(scores) == 15
        for s in scores:
            assert 0.0 <= s <= 1.0, f"Score {s} out of [0, 1]"

    def test_batch_returns_one_score_per_candidate(self):
        """Output length must equal number of candidates."""
        rng = np.random.default_rng(7)
        query = rng.standard_normal(40)
        candidates = [rng.standard_normal(40) for _ in range(10)]
        scores = batch_dtw_scores(query, candidates)
        assert len(scores) == 10

    def test_batch_with_sakoe_chiba(self):
        """Batch with Sakoe-Chiba radius must not raise and must return valid scores."""
        rng = np.random.default_rng(22)
        query = rng.standard_normal(50)
        candidates = [rng.standard_normal(50) for _ in range(5)]
        scores = batch_dtw_scores(query, candidates, sakoe_chiba_radius=5)
        assert len(scores) == 5
        for s in scores:
            assert 0.0 <= s <= 1.0

    def test_identical_candidate_scores_highest(self):
        """Batch should score the identical candidate highest."""
        query = _sine(60, seed=0)
        identical = query.copy()
        different1 = _random_walk(60, seed=10)
        different2 = _random_walk(60, seed=20)
        scores = batch_dtw_scores(query, [different1, identical, different2])
        # Index 1 is the identical candidate
        assert scores[1] == max(scores), (
            f"Expected identical candidate to score highest; scores={scores}"
        )


# ---------------------------------------------------------------------------
# rank_candidates
# ---------------------------------------------------------------------------


class TestRankCandidates:
    """Unit tests for rank_candidates()."""

    def test_rank_identical_first(self):
        """Identical candidate should appear as rank 0 (highest score)."""
        query = _sine(40, seed=0)
        candidates = np.vstack([
            _random_walk(40, seed=1),
            _random_walk(40, seed=2),
            query.copy(),  # identical — should rank first
        ])
        ranked = rank_candidates(query, candidates)
        assert ranked[0][0] == 2, (
            f"Expected identical candidate (index 2) at rank 0; got {ranked[0][0]}"
        )
        assert ranked[0][2] == pytest.approx(1.0, abs=1e-9), (
            f"Expected perfect score for identical candidate; got {ranked[0][2]}"
        )

    def test_rank_output_format(self):
        """Each element must be a 3-tuple: (index, distance, score)."""
        query = _sine(40, seed=0)
        candidates = np.vstack([_random_walk(40, seed=k) for k in range(5)])
        ranked = rank_candidates(query, candidates)
        assert len(ranked) == 5
        for elem in ranked:
            idx, dist, score = elem
            assert isinstance(idx, int)
            assert dist >= 0.0
            assert 0.0 <= score <= 1.0

    def test_rank_sorted_by_score_descending(self):
        """Results must be ordered from highest to lowest score."""
        rng = np.random.default_rng(5)
        query = rng.standard_normal(50)
        candidates = np.vstack([rng.standard_normal(50) for _ in range(8)])
        ranked = rank_candidates(query, candidates)
        scores = [r[2] for r in ranked]
        assert scores == sorted(scores, reverse=True), (
            f"Scores not sorted descending: {scores}"
        )

    def test_rank_all_candidates_preserved(self):
        """All input candidates must appear in the output exactly once."""
        rng = np.random.default_rng(6)
        query = rng.standard_normal(40)
        n = 12
        candidates = np.vstack([rng.standard_normal(40) for _ in range(n)])
        ranked = rank_candidates(query, candidates)
        assert len(ranked) == n
        indices = sorted(r[0] for r in ranked)
        assert indices == list(range(n))

    def test_rank_with_sakoe_chiba(self):
        """rank_candidates should work with Sakoe-Chiba band constraint."""
        query = _sine(50, seed=0)
        candidates = np.vstack([_random_walk(50, seed=k) for k in range(4)])
        ranked = rank_candidates(query, candidates, sakoe_chiba_radius=5)
        assert len(ranked) == 4
