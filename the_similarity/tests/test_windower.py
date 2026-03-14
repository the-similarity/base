import numpy as np
import pytest

from the_similarity.core.windower import sliding_windows, window_indices, multi_scale_indices


def test_basic_sliding():
    s = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    windows = sliding_windows(s, window_size=3)
    assert windows.shape == (3, 3)
    np.testing.assert_array_equal(windows[0], [1, 2, 3])
    np.testing.assert_array_equal(windows[1], [2, 3, 4])
    np.testing.assert_array_equal(windows[2], [3, 4, 5])


def test_stride():
    s = np.arange(10, dtype=np.float64)
    windows = sliding_windows(s, window_size=3, stride=2)
    assert windows.shape == (4, 3)
    np.testing.assert_array_equal(windows[0], [0, 1, 2])
    np.testing.assert_array_equal(windows[1], [2, 3, 4])


def test_window_too_large():
    s = np.array([1.0, 2.0])
    with pytest.raises(ValueError, match="window_size"):
        sliding_windows(s, window_size=5)


def test_window_indices():
    indices = window_indices(10, window_size=3, stride=2)
    assert indices[0] == (0, 3)
    assert indices[1] == (2, 5)
    assert len(indices) == 4


def test_full_window():
    s = np.array([1.0, 2.0, 3.0])
    windows = sliding_windows(s, window_size=3)
    assert windows.shape == (1, 3)


def test_multi_scale_indices():
    results = multi_scale_indices(100, base_window_size=20, scales=[0.5, 1.0, 2.0])
    sizes = set(r.window_size for r in results)
    assert 10 in sizes   # 0.5x
    assert 20 in sizes   # 1.0x
    assert 40 in sizes   # 2.0x


def test_multi_scale_skips_too_large():
    # Scale 2.0 would need 40 bars, but series is only 30
    results = multi_scale_indices(30, base_window_size=20, scales=[1.0, 2.0])
    sizes = set(r.window_size for r in results)
    assert 20 in sizes
    assert 40 not in sizes


def test_multi_scale_records_scale():
    results = multi_scale_indices(100, base_window_size=20, scales=[0.5, 1.0])
    half_scale = [r for r in results if r.scale == 0.5]
    full_scale = [r for r in results if r.scale == 1.0]
    assert len(half_scale) > 0
    assert len(full_scale) > 0
    assert half_scale[0].window_size == 10
