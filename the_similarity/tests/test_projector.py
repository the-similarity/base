import numpy as np

from the_similarity.core.projector import _weighted_quantile, project
from the_similarity.core.scorer import MatchResult


def _make_match(start: int, end: int, score: float) -> MatchResult:
    return MatchResult(start_idx=start, end_idx=end, confidence_score=score)


def test_basic_projection():
    # History: 0..199, matches at [0:50] and [50:100], project 50 bars
    history = np.arange(200, dtype=np.float64)
    matches = [
        _make_match(0, 50, score=80.0),
        _make_match(50, 100, score=60.0),
    ]
    fc = project(matches, history, forward_bars=50)
    assert fc.bars == 50
    assert fc.all_paths.shape == (2, 50)
    assert 50 in fc.curves
    assert fc.percentiles == [10, 25, 50, 75, 90]


def test_no_future_data():
    history = np.arange(100, dtype=np.float64)
    matches = [_make_match(0, 80, score=90.0)]
    fc = project(matches, history, forward_bars=50)
    # Only 20 bars available after match, need 50 => no valid paths
    assert fc.all_paths.shape[0] == 0


def test_empty_matches():
    history = np.arange(200, dtype=np.float64)
    fc = project([], history, forward_bars=50)
    assert fc.all_paths.shape[0] == 0
    assert len(fc.curves[50]) == 50


def test_zero_confidence_weights_fall_back_to_uniform():
    history = np.arange(200, dtype=np.float64)
    matches = [
        _make_match(0, 50, score=0.0),
        _make_match(50, 100, score=0.0),
    ]
    fc = project(matches, history, forward_bars=20)
    assert fc.all_paths.shape == (2, 20)
    assert np.allclose(fc.weights, np.array([0.5, 0.5]))


def test_weighted_quantile_interpolates():
    values = np.array([0.0, 1.0], dtype=np.float64)
    weights = np.array([0.5, 0.5], dtype=np.float64)
    assert _weighted_quantile(values, weights, 0.5) == 0.5


def test_projection_percentiles_remain_ordered():
    history = np.arange(200, dtype=np.float64)
    matches = [
        _make_match(0, 50, score=80.0),
        _make_match(50, 100, score=60.0),
        _make_match(80, 130, score=40.0),
    ]
    fc = project(matches, history, forward_bars=20, percentiles=[10, 50, 90])
    assert np.all(fc.curves[10] <= fc.curves[50])
    assert np.all(fc.curves[50] <= fc.curves[90])
