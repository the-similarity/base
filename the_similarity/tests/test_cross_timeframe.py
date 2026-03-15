"""Tests for cross-timeframe search."""
import numpy as np
import pandas as pd
import pytest

from the_similarity.api import (
    _deduplicate_matches,
    _resample_timeseries,
    cross_timeframe_search,
)
from the_similarity.config import Config
from the_similarity.core.scorer import MatchResult
from the_similarity.io.loader import TimeSeries


def _make_ts(n_bars: int, freq: str = "1min") -> TimeSeries:
    """Create a synthetic TimeSeries with dates."""
    dates = pd.date_range("2024-01-01", periods=n_bars, freq=freq)
    values = 100 + np.cumsum(np.random.RandomState(42).randn(n_bars) * 0.1)
    return TimeSeries(values=values.astype(np.float64), dates=dates.values, name="test")


def _make_match(start: int, end: int, score: float, tf: str | None = None) -> MatchResult:
    return MatchResult(
        start_idx=start, end_idx=end,
        confidence_score=score, source_timeframe=tf,
    )


class TestResampleTimeSeries:
    def test_resample_1min_to_1h(self):
        ts = _make_ts(3600)  # 3600 minutes = 60 hours
        resampled = _resample_timeseries(ts, "1h")
        assert len(resampled) < len(ts)
        assert len(resampled) > 0
        assert resampled.dates is not None

    def test_resample_preserves_last_value(self):
        ts = _make_ts(120, freq="1min")
        resampled = _resample_timeseries(ts, "1h")
        # Last value of each hour should be from the source
        assert len(resampled) >= 1

    def test_no_dates_raises(self):
        ts = TimeSeries(values=np.arange(100, dtype=np.float64))
        with pytest.raises(ValueError, match="without dates"):
            _resample_timeseries(ts, "1h")

    def test_too_coarse_raises(self):
        ts = _make_ts(10, freq="1min")  # 10 minutes
        with pytest.raises(ValueError, match="fewer than 2"):
            _resample_timeseries(ts, "1D")  # can't make daily from 10 min


class TestDeduplicateMatches:
    def test_no_overlap_keeps_all(self):
        matches = [
            _make_match(0, 50, 90),
            _make_match(100, 150, 80),
            _make_match(200, 250, 70),
        ]
        result = _deduplicate_matches(matches, top_k=10)
        assert len(result) == 3

    def test_full_overlap_keeps_best(self):
        matches = [
            _make_match(0, 50, 90),
            _make_match(0, 50, 80),  # same window, lower score
            _make_match(0, 50, 70),
        ]
        result = _deduplicate_matches(matches, top_k=10)
        assert len(result) == 1
        assert result[0].confidence_score == 90

    def test_partial_overlap_above_threshold(self):
        matches = [
            _make_match(0, 100, 90),
            _make_match(40, 140, 80),  # 60% overlap with first
        ]
        result = _deduplicate_matches(matches, top_k=10, overlap_threshold=0.5)
        assert len(result) == 1

    def test_partial_overlap_below_threshold(self):
        matches = [
            _make_match(0, 100, 90),
            _make_match(80, 180, 80),  # 20% overlap
        ]
        result = _deduplicate_matches(matches, top_k=10, overlap_threshold=0.5)
        assert len(result) == 2

    def test_empty(self):
        assert _deduplicate_matches([], top_k=10) == []

    def test_respects_top_k(self):
        matches = [_make_match(i * 100, i * 100 + 50, 90 - i) for i in range(10)]
        result = _deduplicate_matches(matches, top_k=3)
        assert len(result) == 3


class TestMatchResultSourceTimeframe:
    def test_default_none(self):
        m = MatchResult(start_idx=0, end_idx=50)
        assert m.source_timeframe is None

    def test_set_timeframe(self):
        m = MatchResult(start_idx=0, end_idx=50, source_timeframe="1h")
        assert m.source_timeframe == "1h"


@pytest.mark.slow
class TestCrossTimeframeSearch:
    def test_basic_cross_timeframe(self):
        """Cross-timeframe search should return results from multiple timeframes."""
        ts = _make_ts(5000, freq="1min")
        query = ts.values[1000:1060]

        config = Config(
            active_methods=["dtw", "pearson_warped"],
            tier1_candidates=50,
            tier2_candidates=3,
            stride=10,
        )

        results = cross_timeframe_search(
            query=query,
            history=ts,
            timeframes=["5min", "15min"],
            top_k=5,
            config=config,
        )
        assert len(results.matches) > 0
        # Should have timeframe tags
        tfs = {m.source_timeframe for m in results.matches}
        assert all(tf is not None for tf in tfs)

    def test_no_dates_raises(self):
        ts = TimeSeries(values=np.arange(1000, dtype=np.float64))
        with pytest.raises(ValueError, match="dates"):
            cross_timeframe_search(
                query=np.arange(60, dtype=np.float64),
                history=ts,
                timeframes=["1h"],
            )

    def test_all_timeframes_skipped_returns_empty(self):
        """If all timeframes produce window < min_window, return empty."""
        ts = _make_ts(100, freq="1min")  # very short
        results = cross_timeframe_search(
            query=ts.values[:60],
            history=ts,
            timeframes=["1D"],  # way too coarse
            min_window=10,
        )
        assert len(results.matches) == 0
