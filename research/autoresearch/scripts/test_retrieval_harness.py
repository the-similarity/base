"""Tests for the retrieval evaluation harness.

Covers metric computation on known inputs, mock retrieval functions,
report generation, and walk-forward evaluation logic.  All tests are
self-contained (no production data or engine imports required).
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import numpy as np
import pytest

from research.autoresearch.scripts.retrieval_harness import (
    ComparisonReport,
    QueryMetrics,
    RetrievalHarness,
    RetrievalResult,
    WalkForwardReport,
    _jaccard,
    _rank_lifts,
    _recall_at_k,
    _spearman_on_shared,
)


# ---------------------------------------------------------------------------
# Fixtures — deterministic mock retrieval functions
# ---------------------------------------------------------------------------

def _make_mock_retriever(offsets_and_scores: list[tuple[int, float]]):
    """Return a RetrievalFn that always returns the same fixed results.

    Ignores query and history; simply returns the canned results trimmed
    to k.
    """
    def retriever(query: np.ndarray, history: np.ndarray, k: int) -> list[RetrievalResult]:
        return [
            RetrievalResult(offset=o, score=s)
            for o, s in offsets_and_scores[:k]
        ]
    return retriever


@pytest.fixture
def identical_retrievers():
    """Two retrievers that return the exact same results."""
    results = [(10, 0.9), (20, 0.8), (30, 0.7), (40, 0.6), (50, 0.5)]
    return _make_mock_retriever(results), _make_mock_retriever(results)


@pytest.fixture
def disjoint_retrievers():
    """Two retrievers with zero overlap in offsets."""
    baseline = [(10, 0.9), (20, 0.8), (30, 0.7)]
    experimental = [(100, 0.95), (200, 0.85), (300, 0.75)]
    return _make_mock_retriever(baseline), _make_mock_retriever(experimental)


@pytest.fixture
def partial_overlap_retrievers():
    """Two retrievers sharing some but not all offsets, in different order."""
    # Shared offsets: 10, 30.  Baseline-only: 20.  Experimental-only: 40.
    baseline = [(10, 0.9), (20, 0.8), (30, 0.7)]
    experimental = [(30, 0.95), (10, 0.85), (40, 0.75)]
    return _make_mock_retriever(baseline), _make_mock_retriever(experimental)


@pytest.fixture
def synthetic_dataset():
    """A simple synthetic dataset (500 points of random-walk prices)."""
    rng = np.random.default_rng(42)
    returns = rng.normal(0, 0.01, 500)
    prices = 100 * np.exp(np.cumsum(returns))
    return prices


# ---------------------------------------------------------------------------
# Unit tests — metric helpers
# ---------------------------------------------------------------------------

class TestJaccard:
    def test_identical_sets(self):
        assert _jaccard({1, 2, 3}, {1, 2, 3}) == 1.0

    def test_disjoint_sets(self):
        assert _jaccard({1, 2}, {3, 4}) == 0.0

    def test_partial_overlap(self):
        # |{1,2,3} ∩ {2,3,4}| = 2, |{1,2,3} ∪ {2,3,4}| = 4
        assert _jaccard({1, 2, 3}, {2, 3, 4}) == pytest.approx(0.5)

    def test_both_empty(self):
        assert _jaccard(set(), set()) == 1.0

    def test_one_empty(self):
        assert _jaccard({1}, set()) == 0.0


class TestSpearmanOnShared:
    def test_identical_rankings(self):
        results = [RetrievalResult(i * 10, 1.0 - i * 0.1) for i in range(5)]
        rho, pval = _spearman_on_shared(results, results)
        assert rho == pytest.approx(1.0, abs=1e-10)

    def test_reversed_rankings(self):
        baseline = [RetrievalResult(i * 10, 1.0 - i * 0.1) for i in range(5)]
        experimental = list(reversed(baseline))
        rho, _ = _spearman_on_shared(baseline, experimental)
        assert rho == pytest.approx(-1.0, abs=1e-10)

    def test_no_shared_offsets(self):
        baseline = [RetrievalResult(10, 0.9), RetrievalResult(20, 0.8)]
        experimental = [RetrievalResult(30, 0.9), RetrievalResult(40, 0.8)]
        rho, pval = _spearman_on_shared(baseline, experimental)
        assert rho == 0.0
        assert pval == 1.0

    def test_single_shared_offset(self):
        baseline = [RetrievalResult(10, 0.9), RetrievalResult(20, 0.8)]
        experimental = [RetrievalResult(10, 0.95), RetrievalResult(30, 0.8)]
        rho, pval = _spearman_on_shared(baseline, experimental)
        # Only 1 shared offset — not enough for correlation
        assert rho == 0.0
        assert pval == 1.0


class TestRankLifts:
    def test_identical_results(self):
        results = [RetrievalResult(i * 10, 1.0 - i * 0.1) for i in range(3)]
        lifts = _rank_lifts(results, results)
        # Same rank in both → lift = 0 for all
        assert all(v == 0 for v in lifts.values())

    def test_promoted_result(self):
        baseline = [RetrievalResult(10, 0.9), RetrievalResult(20, 0.8), RetrievalResult(30, 0.7)]
        experimental = [RetrievalResult(30, 0.95), RetrievalResult(10, 0.85), RetrievalResult(20, 0.75)]
        lifts = _rank_lifts(baseline, experimental)
        # offset 30: baseline rank 3, experimental rank 1 → lift = 3-1 = +2
        assert lifts[30] == 2
        # offset 10: baseline rank 1, experimental rank 2 → lift = 1-2 = -1
        assert lifts[10] == -1
        # offset 20: baseline rank 2, experimental rank 3 → lift = 2-3 = -1
        assert lifts[20] == -1

    def test_new_result_not_in_baseline(self):
        baseline = [RetrievalResult(10, 0.9)]
        experimental = [RetrievalResult(99, 0.95), RetrievalResult(10, 0.85)]
        lifts = _rank_lifts(baseline, experimental)
        # offset 99: not in baseline → baseline rank = 2 (len + 1), exp rank = 1 → lift = 1
        assert lifts[99] == 1
        # offset 10: baseline rank 1, exp rank 2 → lift = -1
        assert lifts[10] == -1


class TestRecallAtK:
    def test_perfect_recall(self):
        results = [RetrievalResult(i * 10, 1.0 - i * 0.1) for i in range(3)]
        assert _recall_at_k(results, results) == 1.0

    def test_zero_recall(self):
        baseline = [RetrievalResult(10, 0.9), RetrievalResult(20, 0.8)]
        experimental = [RetrievalResult(30, 0.9), RetrievalResult(40, 0.8)]
        assert _recall_at_k(baseline, experimental) == 0.0

    def test_partial_recall(self):
        baseline = [RetrievalResult(10, 0.9), RetrievalResult(20, 0.8)]
        experimental = [RetrievalResult(10, 0.95), RetrievalResult(30, 0.8)]
        assert _recall_at_k(baseline, experimental) == pytest.approx(0.5)

    def test_empty_baseline(self):
        assert _recall_at_k([], [RetrievalResult(10, 0.9)]) == 1.0


# ---------------------------------------------------------------------------
# Integration tests — RetrievalHarness
# ---------------------------------------------------------------------------

class TestRunComparison:
    def test_identical_retrievers_perfect_metrics(self, identical_retrievers, synthetic_dataset):
        baseline_fn, experimental_fn = identical_retrievers
        harness = RetrievalHarness(baseline_fn, experimental_fn)
        query_windows = [(50, 110), (100, 160), (200, 260)]
        report = harness.run_comparison(synthetic_dataset, query_windows, k=5)

        assert report.aggregate_top_k_overlap == pytest.approx(1.0)
        assert report.aggregate_rank_correlation == pytest.approx(1.0, abs=1e-10)
        assert report.aggregate_recall_at_k == pytest.approx(1.0)
        assert report.mean_rank_lift == pytest.approx(0.0)
        assert len(report.per_query) == 3

    def test_disjoint_retrievers_zero_overlap(self, disjoint_retrievers, synthetic_dataset):
        baseline_fn, experimental_fn = disjoint_retrievers
        harness = RetrievalHarness(baseline_fn, experimental_fn)
        query_windows = [(50, 110)]
        report = harness.run_comparison(synthetic_dataset, query_windows, k=3)

        assert report.aggregate_top_k_overlap == pytest.approx(0.0)
        assert report.aggregate_recall_at_k == pytest.approx(0.0)

    def test_partial_overlap_metrics(self, partial_overlap_retrievers, synthetic_dataset):
        baseline_fn, experimental_fn = partial_overlap_retrievers
        harness = RetrievalHarness(baseline_fn, experimental_fn)
        query_windows = [(50, 110)]
        report = harness.run_comparison(synthetic_dataset, query_windows, k=3)

        # 2 shared out of 4 total distinct = 0.5
        assert report.aggregate_top_k_overlap == pytest.approx(0.5)
        # 2 of 3 baseline offsets recalled
        assert report.aggregate_recall_at_k == pytest.approx(2.0 / 3.0)

    def test_rejects_empty_query_windows(self, identical_retrievers, synthetic_dataset):
        baseline_fn, experimental_fn = identical_retrievers
        harness = RetrievalHarness(baseline_fn, experimental_fn)
        with pytest.raises(ValueError, match="query_windows must not be empty"):
            harness.run_comparison(synthetic_dataset, [], k=5)

    def test_rejects_non_1d_dataset(self, identical_retrievers):
        baseline_fn, experimental_fn = identical_retrievers
        harness = RetrievalHarness(baseline_fn, experimental_fn)
        with pytest.raises(ValueError, match="1-D"):
            harness.run_comparison(np.zeros((10, 2)), [(0, 5)], k=5)


class TestCompareWalkForward:
    def test_runs_without_error(self, identical_retrievers, synthetic_dataset):
        baseline_fn, experimental_fn = identical_retrievers
        harness = RetrievalHarness(baseline_fn, experimental_fn)
        report = harness.compare_walk_forward(
            synthetic_dataset, k=5, window_size=30, forward_bars=10, n_trials=5, seed=42,
        )
        assert len(report.per_query) == 5
        assert report.baseline_mean_abs_forward >= 0
        assert report.experimental_mean_abs_forward >= 0

    def test_no_lookahead_enforced(self, synthetic_dataset):
        """Verify that retrievers only see history before the query window."""
        seen_history_lengths: list[int] = []

        def tracking_retriever(query, history, k):
            seen_history_lengths.append(len(history))
            return [RetrievalResult(offset=0, score=1.0)]

        harness = RetrievalHarness(tracking_retriever, tracking_retriever)
        report = harness.compare_walk_forward(
            synthetic_dataset, k=1, window_size=30, forward_bars=10, n_trials=3, seed=42,
        )
        # Each call should see history shorter than full dataset
        # (history = dataset[:query_start], and query_start >= 3*window_size = 90)
        for length in seen_history_lengths:
            assert length < len(synthetic_dataset)
            assert length >= 3 * 30  # min_lookback

    def test_rejects_short_dataset(self, identical_retrievers):
        baseline_fn, experimental_fn = identical_retrievers
        harness = RetrievalHarness(baseline_fn, experimental_fn)
        short_data = np.ones(50)
        with pytest.raises(ValueError, match="too short"):
            harness.compare_walk_forward(short_data, window_size=30, forward_bars=30)


class TestGenerateReport:
    def test_writes_json(self, identical_retrievers, synthetic_dataset):
        baseline_fn, experimental_fn = identical_retrievers
        harness = RetrievalHarness(baseline_fn, experimental_fn)
        harness.run_comparison(synthetic_dataset, [(50, 110)], k=5)

        with tempfile.TemporaryDirectory() as tmpdir:
            out = harness.generate_report(Path(tmpdir) / "out.json")
            assert out.exists()
            data = json.loads(out.read_text())
            assert "comparison" in data
            assert data["comparison"]["aggregate"]["top_k_overlap"] == pytest.approx(1.0)

    def test_writes_walk_forward_report(self, identical_retrievers, synthetic_dataset):
        baseline_fn, experimental_fn = identical_retrievers
        harness = RetrievalHarness(baseline_fn, experimental_fn)
        harness.compare_walk_forward(
            synthetic_dataset, k=5, window_size=30, forward_bars=10, n_trials=3, seed=42,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            out = harness.generate_report(Path(tmpdir) / "wf.json")
            data = json.loads(out.read_text())
            assert "walk_forward" in data
            assert len(data["walk_forward"]["per_query"]) == 3

    def test_writes_combined_report(self, identical_retrievers, synthetic_dataset):
        baseline_fn, experimental_fn = identical_retrievers
        harness = RetrievalHarness(baseline_fn, experimental_fn)
        harness.run_comparison(synthetic_dataset, [(50, 110)], k=5)
        harness.compare_walk_forward(
            synthetic_dataset, k=5, window_size=30, forward_bars=10, n_trials=2, seed=42,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            out = harness.generate_report(Path(tmpdir) / "combined.json")
            data = json.loads(out.read_text())
            assert "comparison" in data
            assert "walk_forward" in data

    def test_raises_if_nothing_run(self, identical_retrievers):
        baseline_fn, experimental_fn = identical_retrievers
        harness = RetrievalHarness(baseline_fn, experimental_fn)
        with pytest.raises(RuntimeError, match="No results"):
            harness.generate_report("/tmp/nope.json")

    def test_creates_parent_directories(self, identical_retrievers, synthetic_dataset):
        baseline_fn, experimental_fn = identical_retrievers
        harness = RetrievalHarness(baseline_fn, experimental_fn)
        harness.run_comparison(synthetic_dataset, [(50, 110)], k=5)

        with tempfile.TemporaryDirectory() as tmpdir:
            deep_path = Path(tmpdir) / "a" / "b" / "c" / "report.json"
            out = harness.generate_report(deep_path)
            assert out.exists()


# ---------------------------------------------------------------------------
# Report serialization
# ---------------------------------------------------------------------------

class TestReportSerialization:
    def test_comparison_report_to_dict_roundtrip(self):
        qm = QueryMetrics(
            query_index=0,
            top_k_overlap=0.5,
            rank_correlation=0.8,
            rank_correlation_pvalue=0.01,
            recall_at_k=0.6,
            rank_lifts={"10": 2, "20": -1},
            baseline_offsets=[10, 20, 30],
            experimental_offsets=[10, 30, 40],
        )
        report = ComparisonReport(
            per_query=[qm],
            aggregate_top_k_overlap=0.5,
            aggregate_rank_correlation=0.8,
            aggregate_recall_at_k=0.6,
            mean_rank_lift=0.5,
        )
        d = report.to_dict()
        # Verify JSON-serializability
        s = json.dumps(d)
        loaded = json.loads(s)
        assert loaded["aggregate"]["top_k_overlap"] == 0.5
        assert len(loaded["per_query"]) == 1

    def test_walk_forward_report_to_dict(self):
        report = WalkForwardReport(
            per_query=[],
            baseline_mean_abs_forward=0.01,
            experimental_mean_abs_forward=0.02,
        )
        d = report.to_dict()
        s = json.dumps(d)
        loaded = json.loads(s)
        assert loaded["aggregate"]["baseline_mean_abs_forward"] == 0.01
