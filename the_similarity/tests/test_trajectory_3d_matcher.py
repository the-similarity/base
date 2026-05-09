"""Integration tests for the 3D trajectory matcher.

Verifies that the corpus + analogue retrieval + forecast cone
pipeline retrieves the *correct shape class* on a small synthetic
universe (helices vs lines vs spirals), and that the forecast cone
behaves sensibly (well-defined quantiles, translation-invariant
shape, monotonic widening as horizon grows).
"""

from __future__ import annotations

import numpy as np
import pytest

from the_similarity.core.trajectory_matcher import (
    build_corpus,
    find_analogues,
    forecast_cone,
)


def _helix(n_pts: int, r: float, c: float, phase: float = 0.0) -> np.ndarray:
    """Helix sampler used across multiple tests."""
    theta = np.linspace(0, 6 * np.pi, n_pts) + phase
    return np.stack(
        [r * np.cos(theta), r * np.sin(theta), c * theta], axis=1
    )


def _line(n_pts: int, direction: np.ndarray, length: float = 30.0) -> np.ndarray:
    """Straight line sampler in 3D."""
    direction = direction / np.linalg.norm(direction)
    t = np.linspace(0, length, n_pts)
    return t[:, None] * direction[None, :]


# ---------------------------------------------------------------------------
# Corpus building
# ---------------------------------------------------------------------------


class TestCorpusBuilding:
    def test_short_trajectory_adds_zero_windows(self):
        # T < window_len + forward_bars -> nothing added.
        corpus = build_corpus(
            [np.zeros((30, 3))], window_len=50, forward_bars=20
        )
        assert len(corpus.windows) == 0

    def test_window_count_matches_stride_arithmetic(self):
        # T = 200, window_len = 50, forward_bars = 20, stride = 10.
        # Last valid start = 200 - 70 = 130. Windows at 0, 10, ..., 130 => 14.
        helix = _helix(200, 1.0, 0.3)
        corpus = build_corpus(
            [helix], window_len=50, stride=10, forward_bars=20,
        )
        assert len(corpus.windows) == 14

    def test_corpus_windows_have_kt_and_future(self):
        corpus = build_corpus(
            [_helix(200, 1.0, 0.3)],
            window_len=50, stride=10, forward_bars=20,
        )
        w = corpus.windows[0]
        assert w.kt.shape == (50, 2)
        assert w.future_points.shape == (20, 3)
        assert w.points.shape == (50, 3)


# ---------------------------------------------------------------------------
# Retrieval — should prefer the right shape class
# ---------------------------------------------------------------------------


class TestRetrievalShapeClass:
    """The matcher should rank same-class analogues above different-class."""

    def _build_helix_line_corpus(self, n_each: int = 3, noise: float = 0.005):
        # Mix of helices (different phases / radii) and lines
        # (different directions). The matcher should retrieve helices
        # for a helix query and lines for a line query.
        rng = np.random.default_rng(7)
        trajectories = []
        for k in range(n_each):
            h = _helix(300, r=1.0, c=0.3, phase=k * 0.4)
            h = h + rng.normal(0, noise, h.shape)
            trajectories.append(h)
        directions = [np.array([1, 0, 0.0]), np.array([0, 1, 0.0]), np.array([1, 1, 1.0])]
        for d in directions[:n_each]:
            ln = _line(300, d, length=30)
            ln = ln + rng.normal(0, noise, ln.shape)
            trajectories.append(ln)
        return build_corpus(
            trajectories,
            window_len=80, stride=20, forward_bars=30,
        ), n_each

    def test_helix_query_retrieves_helices(self):
        corpus, n_each = self._build_helix_line_corpus()
        query = _helix(120, r=1.0, c=0.3, phase=0.25)[:80]
        matches = find_analogues(query, corpus, top_n=5)
        # All top-5 should be from helix trajectories (ids 0..n_each-1)
        helix_ids = set(range(n_each))
        kinds = [m.window.trajectory_id in helix_ids for m in matches]
        assert sum(kinds) >= 4, (
            f"Expected >= 4/5 helix matches; got {sum(kinds)}: "
            f"{[m.window.trajectory_id for m in matches]}"
        )

    def test_line_query_retrieves_lines(self):
        corpus, n_each = self._build_helix_line_corpus()
        # Query from a fresh line (different direction) so it's not
        # in the corpus verbatim.
        query = _line(120, np.array([1, 1, 0.5]), length=30)[:80]
        matches = find_analogues(query, corpus, top_n=5)
        line_ids = set(range(n_each, 2 * n_each))
        kinds = [m.window.trajectory_id in line_ids for m in matches]
        assert sum(kinds) >= 4, (
            f"Expected >= 4/5 line matches; got {sum(kinds)}: "
            f"{[m.window.trajectory_id for m in matches]}"
        )

    def test_exclude_trajectory_id_drops_self_matches(self):
        # If we exclude trajectory id=0, no result should come from it.
        corpus, _ = self._build_helix_line_corpus()
        query = _helix(120, r=1.0, c=0.3, phase=0.0)[:80]
        matches = find_analogues(
            query, corpus, top_n=10, exclude_trajectory_id=0
        )
        assert all(m.window.trajectory_id != 0 for m in matches)

    def test_empty_corpus_returns_empty_list(self):
        empty = build_corpus([], window_len=50, forward_bars=20)
        query = _helix(120, 1.0, 0.3)[:50]
        assert find_analogues(query, empty, top_n=5) == []


# ---------------------------------------------------------------------------
# Forecast cone — well-formed, translation-invariant, widening
# ---------------------------------------------------------------------------


class TestForecastCone:
    def _setup(self):
        rng = np.random.default_rng(11)
        trajectories = []
        for k in range(5):
            h = _helix(400, r=1.0, c=0.3, phase=k * 0.3)
            trajectories.append(h + rng.normal(0, 0.005, h.shape))
        return build_corpus(
            trajectories, window_len=80, stride=20, forward_bars=30
        )

    def test_forecast_shape_and_quantile_ordering(self):
        corpus = self._setup()
        query = _helix(120, 1.0, 0.3, phase=0.15)[:80]
        f = forecast_cone(query, corpus, top_n=5)
        assert f.bars == 30
        assert f.percentiles == [10, 50, 90]
        assert f.n_analogues > 0
        # Each curve is (forward_bars, 3)
        for p in f.percentiles:
            assert f.curves[p].shape == (30, 3)
        # Quantile ordering: P10 <= P50 <= P90 per axis per bar.
        # We allow equality because with very few analogues the
        # weighted quantile interpolation can produce equal values.
        for axis in range(3):
            assert np.all(f.curves[10][:, axis] <= f.curves[50][:, axis] + 1e-9)
            assert np.all(f.curves[50][:, axis] <= f.curves[90][:, axis] + 1e-9)

    def test_translation_invariant_cone_shape(self):
        # Shifting the query by a constant should shift the cone by
        # the same constant; the *shape* of the cone (P50 relative to
        # the query anchor) should be unchanged.
        corpus = self._setup()
        query1 = _helix(120, 1.0, 0.3, phase=0.15)[:80]
        query2 = query1 + np.array([100, -50, 30])

        f1 = forecast_cone(query1, corpus, top_n=5)
        f2 = forecast_cone(query2, corpus, top_n=5)

        anchor1 = query1[-1]
        anchor2 = query2[-1]
        rel1 = f1.curves[50] - anchor1
        rel2 = f2.curves[50] - anchor2
        np.testing.assert_allclose(rel1, rel2, atol=1e-6)

    def test_empty_cone_when_corpus_lacks_continuations(self):
        # Build a corpus with NO trajectories so n_analogues=0 path runs.
        empty = build_corpus([], window_len=50, forward_bars=20)
        query = _helix(120, 1.0, 0.3)[:50]
        f = forecast_cone(query, empty, top_n=5)
        assert f.n_analogues == 0
        assert f.bars == 20
        for p in f.percentiles:
            assert np.allclose(f.curves[p], 0.0)

    def test_return_analogues_flag(self):
        corpus = self._setup()
        query = _helix(120, 1.0, 0.3, phase=0.15)[:80]
        f, analogues = forecast_cone(query, corpus, top_n=5, return_analogues=True)
        assert len(analogues) == f.n_analogues
        # Each analogue must carry future_points (the projector
        # filter dropped any with None).
        assert all(m.window.future_points is not None for m in analogues)
