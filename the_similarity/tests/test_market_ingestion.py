"""Tests for prediction market ingestion — markets, loader, adapter.

Covers:
- ForecastQuestion / MarketPrice / MarketHistory / QuestionSet round-trip
  serialization (to_dict -> from_dict identity).
- Benchmark question set loads without error.
- Price history timestamp ordering.
- Registry adapter creates a RunRecord with correct kind and summary.
- Brier score computation for resolved questions.
- Edge cases: empty prices, unresolved questions.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from the_similarity.events.market_adapter import register_question_set
from the_similarity.events.market_loader import load_questions, save_questions
from the_similarity.events.markets import (
    ForecastQuestion,
    MarketHistory,
    MarketPrice,
    QuestionSet,
)

# Path to the benchmark fixture shipped with the package.
_BENCHMARK_PATH = (
    Path(__file__).resolve().parent.parent
    / "events"
    / "data"
    / "benchmark_questions.json"
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_question(
    qid: str = "test-q-1",
    resolved: bool = True,
    resolution: bool = True,
) -> ForecastQuestion:
    """Factory for a minimal ForecastQuestion."""
    return ForecastQuestion(
        question_id=qid,
        question="Will X happen?",
        category="economics",
        source="polymarket",
        resolution_date="2022-06-01",
        resolved=resolved,
        resolution=resolution if resolved else None,
        metadata={"test": True},
    )


def _make_prices(qid: str = "test-q-1", n: int = 5) -> list[MarketPrice]:
    """Factory for a list of MarketPrice observations with ascending timestamps."""
    return [
        MarketPrice(
            question_id=qid,
            timestamp=f"2022-01-{i + 1:02d}T00:00:00Z",
            probability=0.1 * (i + 1),
            volume=1000.0 * (i + 1),
        )
        for i in range(n)
    ]


# ---------------------------------------------------------------------------
# Round-trip serialization
# ---------------------------------------------------------------------------


class TestRoundTripSerialization:
    """Verify to_dict -> from_dict produces identical objects for every dataclass."""

    def test_forecast_question_round_trip(self) -> None:
        """ForecastQuestion survives a dict round trip."""
        q = _make_question()
        d = q.to_dict()
        q2 = ForecastQuestion.from_dict(d)
        assert q2.question_id == q.question_id
        assert q2.question == q.question
        assert q2.category == q.category
        assert q2.source == q.source
        assert q2.resolution_date == q.resolution_date
        assert q2.resolved == q.resolved
        assert q2.resolution == q.resolution
        assert q2.metadata == q.metadata

    def test_market_price_round_trip(self) -> None:
        """MarketPrice survives a dict round trip."""
        p = MarketPrice(
            question_id="q1",
            timestamp="2022-01-01T00:00:00Z",
            probability=0.75,
            volume=5000.0,
        )
        d = p.to_dict()
        p2 = MarketPrice.from_dict(d)
        assert p2.question_id == p.question_id
        assert p2.timestamp == p.timestamp
        assert p2.probability == p.probability
        assert p2.volume == p.volume

    def test_market_history_round_trip(self) -> None:
        """MarketHistory (question + prices) survives a dict round trip."""
        q = _make_question()
        prices = _make_prices()
        h = MarketHistory(question=q, prices=prices)
        d = h.to_dict()
        h2 = MarketHistory.from_dict(d)
        assert h2.question.question_id == q.question_id
        assert len(h2.prices) == len(prices)
        assert h2.prices[0].timestamp == prices[0].timestamp

    def test_question_set_round_trip(self) -> None:
        """QuestionSet (full hierarchy) survives a dict round trip."""
        q = _make_question()
        prices = _make_prices()
        h = MarketHistory(question=q, prices=prices)
        qs = QuestionSet(questions=[h], name="test-set", version="v1.0")
        d = qs.to_dict()
        qs2 = QuestionSet.from_dict(d)
        assert qs2.name == qs.name
        assert qs2.version == qs.version
        assert len(qs2.questions) == 1
        assert qs2.questions[0].question.question_id == q.question_id


# ---------------------------------------------------------------------------
# Benchmark fixture
# ---------------------------------------------------------------------------


class TestBenchmarkLoad:
    """Verify the shipped benchmark_questions.json loads correctly."""

    def test_benchmark_loads_without_error(self) -> None:
        """load_questions on the benchmark fixture produces a valid QuestionSet."""
        qs = load_questions(_BENCHMARK_PATH)
        assert isinstance(qs, QuestionSet)
        assert qs.name == "benchmark-binary-2022"
        assert len(qs.questions) >= 10  # spec says 10-15

    def test_benchmark_all_questions_have_prices(self) -> None:
        """Every question in the benchmark has at least one price observation."""
        qs = load_questions(_BENCHMARK_PATH)
        for h in qs.questions:
            assert len(h.prices) > 0, f"{h.question.question_id} has no prices"

    def test_benchmark_price_timestamps_ascending(self) -> None:
        """Price histories in the benchmark are sorted by timestamp ascending."""
        qs = load_questions(_BENCHMARK_PATH)
        for h in qs.questions:
            timestamps = [p.timestamp for p in h.prices]
            assert timestamps == sorted(timestamps), (
                f"{h.question.question_id}: prices not sorted by timestamp"
            )


# ---------------------------------------------------------------------------
# Loader save/load round trip
# ---------------------------------------------------------------------------


class TestLoaderRoundTrip:
    """Verify save_questions -> load_questions produces identical data."""

    def test_save_load_round_trip(self, tmp_path: Path) -> None:
        """QuestionSet survives a JSON file round trip."""
        q = _make_question()
        prices = _make_prices()
        h = MarketHistory(question=q, prices=prices)
        qs = QuestionSet(questions=[h], name="round-trip", version="v0.1")

        out_path = tmp_path / "test_qs.json"
        save_questions(qs, out_path)
        qs2 = load_questions(out_path)

        assert qs2.name == qs.name
        assert qs2.version == qs.version
        assert len(qs2.questions) == 1
        assert qs2.questions[0].question.question_id == q.question_id
        assert len(qs2.questions[0].prices) == len(prices)


# ---------------------------------------------------------------------------
# Registry adapter
# ---------------------------------------------------------------------------


class _FakeRegistry:
    """Minimal mock registry that records register_run calls."""

    def __init__(self) -> None:
        self.runs: list = []

    def register_run(self, record) -> str:
        self.runs.append(record)
        return record.run_id


class TestMarketAdapter:
    """Verify register_question_set produces a correct RunRecord."""

    def test_register_creates_run(self) -> None:
        """register_question_set creates a RunRecord with kind=EVENTS."""
        q = _make_question(resolved=True, resolution=True)
        prices = _make_prices()
        h = MarketHistory(question=q, prices=prices)
        qs = QuestionSet(questions=[h], name="adapter-test", version="v1.0")

        registry = _FakeRegistry()
        run_id = register_question_set(qs, registry)

        assert len(registry.runs) == 1
        record = registry.runs[0]
        assert record.run_id == run_id
        assert record.kind.value == "events"
        assert record.pillar == "events"

        # Summary should contain headline fields.
        s = record.summary
        assert s["n_questions"] == 1
        assert s["n_resolved"] == 1
        assert s["mean_brier_score"] is not None
        assert isinstance(s["categories"], list)
        assert "economics" in s["categories"]

    def test_brier_score_perfect_forecast(self) -> None:
        """A price history ending at 1.0 for a True resolution => Brier=0."""
        q = _make_question(resolved=True, resolution=True)
        # Last price = 1.0 => perfect forecast for True outcome.
        prices = [
            MarketPrice(
                question_id="test-q-1",
                timestamp="2022-01-01T00:00:00Z",
                probability=0.5,
            ),
            MarketPrice(
                question_id="test-q-1",
                timestamp="2022-01-02T00:00:00Z",
                probability=1.0,
            ),
        ]
        h = MarketHistory(question=q, prices=prices)
        qs = QuestionSet(questions=[h], name="brier-test", version="v1.0")

        registry = _FakeRegistry()
        register_question_set(qs, registry)

        brier = registry.runs[0].summary["mean_brier_score"]
        assert brier == pytest.approx(0.0)

    def test_unresolved_questions_excluded_from_brier(self) -> None:
        """Unresolved questions produce mean_brier_score=None."""
        q = _make_question(resolved=False)
        prices = _make_prices()
        h = MarketHistory(question=q, prices=prices)
        qs = QuestionSet(questions=[h], name="unresolved-test", version="v1.0")

        registry = _FakeRegistry()
        register_question_set(qs, registry)

        assert registry.runs[0].summary["mean_brier_score"] is None
