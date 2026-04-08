from __future__ import annotations

import numpy as np

from the_similarity.core.pine_mirror import (
    find_best_match,
    logreturn_zscore,
    scale_match_to_current,
    similarity_score,
)


def test_logreturn_zscore_constant_series_returns_zeroes() -> None:
    values = np.array([100.0, 100.0, 100.0, 100.0])
    result = logreturn_zscore(values)
    assert result.shape == (3,)
    assert np.allclose(result, 0.0)


def test_scale_match_to_current_anchors_last_value() -> None:
    match = np.array([80.0, 100.0, 120.0])
    scaled = scale_match_to_current(match, current_price=240.0)
    assert np.isclose(scaled[-1], 240.0)
    assert np.allclose(scaled, np.array([160.0, 200.0, 240.0]))


def test_similarity_score_prefers_repeated_pattern() -> None:
    query = np.array([100.0, 102.0, 101.0, 104.0, 107.0, 110.0])
    repeated = np.array([50.0, 51.0, 50.5, 52.0, 53.5, 55.0])
    randomish = np.array([100.0, 98.0, 103.0, 97.0, 105.0, 96.0])

    repeated_score = similarity_score(query, repeated)
    random_score = similarity_score(query, randomish)

    assert repeated_score > random_score
    assert repeated_score > 70.0


def test_find_best_match_returns_scaled_projection_from_historical_analogue() -> None:
    motif = np.array([100.0, 103.0, 101.0, 105.0, 108.0, 111.0, 109.0, 114.0])
    future = np.array([116.0, 118.0, 121.0, 125.0])
    filler = np.linspace(90.0, 97.0, 14)
    recent = motif * 1.8

    history = np.concatenate(
        [
            np.linspace(70.0, 82.0, 12),
            motif,
            future,
            filler,
            recent,
        ]
    )

    result = find_best_match(
        history,
        query_length=len(motif),
        forecast_bars=len(future),
        lookback_bars=32,
        stride=1,
        min_separation=8,
        min_scale=1.0,
        scale_step=0.25,
        scale_count=1,
    )

    assert result is not None
    assert result.score > 80.0
    assert result.projected_end_return > 0
    assert np.isclose(result.matched_resampled[-1], recent[-1])
    expected_last_projection = recent[-1] * (future[-1] / motif[-1])
    assert np.isclose(result.projected_prices[-1], expected_last_projection)
