import numpy as np
import pandas as pd

import the_similarity
from the_similarity.io.loader import TimeSeries


def test_load_numpy():
    ts = the_similarity.load(np.array([1.0, 2.0, 3.0]))
    assert len(ts) == 3


def test_load_dict():
    ts = the_similarity.load({"values": [1, 2, 3, 4, 5]})
    assert len(ts) == 5
    assert ts.values.dtype == np.float64


def test_load_dataframe():
    df = pd.DataFrame(
        {
            "date": pd.date_range("2020-01-01", periods=100),
            "close": np.random.randn(100).cumsum() + 100,
        }
    )
    ts = the_similarity.load(df)
    assert len(ts) == 100
    assert ts.dates is not None


def test_search_and_project():
    np.random.seed(42)
    pattern = np.sin(np.linspace(0, 2 * np.pi, 30))
    noise = np.random.randn(300) * 0.1
    history = noise.copy()
    history[50:80] = pattern + np.random.randn(30) * 0.01
    history[150:180] = pattern + np.random.randn(30) * 0.01
    history[250:280] = pattern + np.random.randn(30) * 0.01

    ts = the_similarity.load(history)
    query = TimeSeries(values=history[250:280])

    results = the_similarity.search(query=query, history=ts, top_k=5)
    assert len(results.matches) > 0
    assert results.matches[0].confidence_score > 0
    assert results.best is not None
    assert results.best.confidence_score == results.matches[0].confidence_score

    forecast = the_similarity.project(results, ts, forward_bars=10)
    assert forecast.bars == 10


def test_search_summary():
    np.random.seed(42)
    history = np.random.randn(200).cumsum() + 100
    ts = the_similarity.load(history)
    query = TimeSeries(values=history[50:80])

    results = the_similarity.search(query=query, history=ts, top_k=3)
    text = results.summary()
    assert "SearchResults" in text
    assert "dtw=" in text


def test_search_with_structural_methods_and_custom_percentiles():
    np.random.seed(7)
    pattern = np.sin(np.linspace(0, 2 * np.pi, 40))
    history = 100 + np.cumsum(np.random.randn(420) * 0.05)
    history[80:120] = 100 + np.cumsum(pattern * 0.4 + 0.2)
    history[280:320] = history[80:120]

    ts = the_similarity.load(history)
    query = TimeSeries(values=history[280:320])

    results = the_similarity.search(
        query=query,
        history=ts,
        top_k=5,
        active_methods=[
            "dtw",
            "pearson_warped",
            "bempedelis_r2",
            "bempedelis_smoothness",
        ],
        tier1_candidates=50,
        tier2_candidates=10,
    )
    assert results.best is not None
    assert results.best.transform_alpha is not None
    assert results.best.score_breakdown.bempedelis_r2 >= 0

    forecast = the_similarity.project(
        results, ts, forward_bars=12, percentiles=[10, 25, 50, 75, 90]
    )
    assert forecast.percentiles == [10, 25, 50, 75, 90]
    assert 25 in forecast.curves
    assert 75 in forecast.curves


def test_timeseries_slicing():
    dates = pd.date_range("2020-01-01", periods=100)
    values = np.arange(100, dtype=np.float64)
    ts = TimeSeries(values=values, dates=dates.values)

    sliced = ts["2020-02-01":"2020-03-01"]
    assert len(sliced) > 0
    assert len(sliced) < 100
