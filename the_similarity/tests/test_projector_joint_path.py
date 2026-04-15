"""Tests for the joint-path projector (projector-v2 lane)."""

from __future__ import annotations

import numpy as np

from the_similarity.core.projector import project as baseline_project
from the_similarity.core.projector_joint_path import JointPathState, project
from the_similarity.core.scorer import MatchResult


def _make_match(start: int, end: int, score: float) -> MatchResult:
    return MatchResult(start_idx=start, end_idx=end, confidence_score=score)


# ---------------------------------------------------------------------------
# Signature / shape parity
# ---------------------------------------------------------------------------


def test_signature_parity_with_baseline():
    history = np.arange(400, dtype=np.float64)
    matches = [_make_match(i, i + 40, score=1.0) for i in range(0, 240, 40)]
    fc = project(
        matches,
        history,
        forward_bars=30,
        percentiles=[10, 25, 50, 75, 90],
        n_paths=200,
    )
    assert fc.bars == 30
    assert fc.percentiles == [10, 25, 50, 75, 90]
    for p in [10, 25, 50, 75, 90]:
        assert p in fc.curves
        assert len(fc.curves[p]) == 30


def test_diagnostic_state():
    history = np.arange(400, dtype=np.float64)
    matches = [_make_match(i, i + 40, score=1.0) for i in range(0, 200, 40)]
    fc = project(matches, history, forward_bars=30, n_paths=250, seed=7)
    state: JointPathState = getattr(fc, "joint_path")
    assert isinstance(state, JointPathState)
    assert state.n_simulated_paths == 250
    assert state.n_base_paths >= 1
    assert state.seed == 7


# ---------------------------------------------------------------------------
# Determinism and cone structure
# ---------------------------------------------------------------------------


def test_deterministic_with_seed():
    history = np.arange(400, dtype=np.float64)
    matches = [_make_match(i, i + 40, score=1.0) for i in range(0, 200, 40)]
    fc_a = project(matches, history, forward_bars=30, n_paths=300, seed=123)
    fc_b = project(matches, history, forward_bars=30, n_paths=300, seed=123)
    for p in [10, 25, 50, 75, 90]:
        np.testing.assert_allclose(fc_a.curves[p], fc_b.curves[p])


def test_percentile_monotonicity():
    history = np.arange(400, dtype=np.float64)
    matches = [_make_match(i, i + 40, score=1.0) for i in range(0, 200, 40)]
    fc = project(matches, history, forward_bars=30, n_paths=500, seed=42)
    assert np.all(fc.curves[10] <= fc.curves[25] + 1e-9)
    assert np.all(fc.curves[25] <= fc.curves[50] + 1e-9)
    assert np.all(fc.curves[50] <= fc.curves[75] + 1e-9)
    assert np.all(fc.curves[75] <= fc.curves[90] + 1e-9)


def test_different_seeds_produce_different_samples():
    history = np.arange(400, dtype=np.float64)
    matches = [_make_match(i, i + 40, score=1.0) for i in range(0, 200, 40)]
    fc_a = project(matches, history, forward_bars=30, n_paths=300, seed=1)
    fc_b = project(matches, history, forward_bars=30, n_paths=300, seed=2)
    # Without variance guarantees, at least one of the outer curves must differ.
    diff_10 = np.max(np.abs(fc_a.curves[10] - fc_b.curves[10]))
    diff_90 = np.max(np.abs(fc_a.curves[90] - fc_b.curves[90]))
    assert diff_10 + diff_90 > 0.0


# ---------------------------------------------------------------------------
# Joint structure property
# ---------------------------------------------------------------------------


def test_paths_preserve_row_correlation():
    """Per-path correlation across bars must be non-trivial.

    Bar-wise independent sampling (a strawman) would produce paths
    whose adjacent-bar correlation is ~0. Our joint sampler preserves
    correlation because we (a) resample whole paths and (b) use a
    per-path scalar noise term.
    """
    # Build matches whose forward windows are strongly mean-trended so
    # the empirical joint distribution has high adjacent-bar correlation.
    # We synthesise a history where each window is a linear ramp with
    # slope sampled from a wide distribution.
    rng = np.random.default_rng(0)
    history = rng.normal(100, 5, size=500).astype(np.float64)
    # Overwrite the "forward" region of each match with a strongly trended
    # path so the empirical correlation is high.
    matches = []
    for i, start in enumerate(range(0, 300, 40)):
        slope = (i - 4) * 0.5
        forward_start = start + 40
        history[forward_start : forward_start + 30] = history[forward_start - 1] + slope * np.arange(1, 31)
        matches.append(_make_match(start, start + 40, score=1.0))

    fc = project(matches, history, forward_bars=30, n_paths=500, seed=42)
    # Correlation between bar 0 and bar 29 across simulated paths.
    sample = fc.all_paths  # (500, 30)
    corr = float(np.corrcoef(sample[:, 0], sample[:, -1])[0, 1])
    # With independent per-bar sampling this would be ~0. Joint sampling
    # produces a clearly positive correlation when the source paths
    # themselves are correlated.
    assert corr > 0.2, f"joint correlation too low: {corr}"


# ---------------------------------------------------------------------------
# Fail-closed behaviour
# ---------------------------------------------------------------------------


def test_no_matches_returns_baseline_shape():
    history = np.arange(80, dtype=np.float64)
    matches = [_make_match(0, 79, score=1.0)]  # not enough forward history
    fc = project(matches, history, forward_bars=50, n_paths=100, seed=0)
    # Should be shaped like baseline empty cone.
    assert fc.all_paths.shape[0] in (0, 100)
    state: JointPathState = getattr(fc, "joint_path")
    # Either fell back (n_simulated_paths==0) OR simulated zero-matched paths
    # if the baseline extracted any — but with forward_bars>available we
    # expect the fall-back path.
    baseline_fc = baseline_project(matches, history, forward_bars=50)
    if baseline_fc.all_paths.shape[0] == 0:
        assert state.n_simulated_paths == 0
