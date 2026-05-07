"""Tests for synthetic generator comparison and promotion logic.

Covers:
- ComparisonResult ranking and best() semantics
- compare_generators with 2 generators produces ranked results
- Promotion creates a DatasetSpec in the registry
- get_promoted retrieves the promoted dataset
- list_promoted returns all promoted datasets
- Edge cases: empty comparison, error handling, re-promotion
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from the_similarity.synthetic.comparison import (
    ComparisonResult,
    GeneratorResult,
    compare_generators,
    _rank_results,
)
from the_similarity.synthetic.promotion import (
    get_promoted,
    list_promoted,
    promote_run,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def source_array() -> np.ndarray:
    """Deterministic 200-point source series for comparison tests.

    Length 200 is sufficient for both generators (block_len=20 default)
    and the utility scorecard's lag-based regression (needs >= LAGS+2).
    """
    rng = np.random.default_rng(123)
    return rng.standard_normal(200)


@pytest.fixture
def registry_db(tmp_path: Path):
    """Fresh in-memory-equivalent SQLite registry in a temp dir.

    Returns a :class:`RunRegistry` instance that writes to a temp file.
    Cleaned up automatically by pytest's tmp_path fixture.
    """
    from the_similarity.platform.registry import RunRegistry

    db_path = tmp_path / "test_registry.db"
    return RunRegistry(str(db_path))


# ---------------------------------------------------------------------------
# Ranking tests
# ---------------------------------------------------------------------------


class TestRankResults:
    """Unit tests for the _rank_results sorting function."""

    def test_ranks_by_fidelity_descending(self):
        """Higher fidelity should rank first."""
        results = [
            GeneratorResult(generator_name="low", fidelity_score=0.3, utility_gap=0.1),
            GeneratorResult(generator_name="high", fidelity_score=0.9, utility_gap=0.1),
        ]
        ranked = _rank_results(results)
        assert ranked[0].generator_name == "high"
        assert ranked[0].overall_rank == 1
        assert ranked[1].generator_name == "low"
        assert ranked[1].overall_rank == 2

    def test_tiebreak_by_utility_gap_ascending(self):
        """When fidelity is equal, lower utility_gap should rank first."""
        results = [
            GeneratorResult(
                generator_name="worse_util", fidelity_score=0.5, utility_gap=0.8
            ),
            GeneratorResult(
                generator_name="better_util", fidelity_score=0.5, utility_gap=0.2
            ),
        ]
        ranked = _rank_results(results)
        assert ranked[0].generator_name == "better_util"
        assert ranked[1].generator_name == "worse_util"

    def test_errors_rank_last(self):
        """Results with errors should always rank after error-free results."""
        results = [
            GeneratorResult(
                generator_name="errored", fidelity_score=0.99, error="boom"
            ),
            GeneratorResult(generator_name="ok", fidelity_score=0.1, utility_gap=0.5),
        ]
        ranked = _rank_results(results)
        assert ranked[0].generator_name == "ok"
        assert ranked[1].generator_name == "errored"


# ---------------------------------------------------------------------------
# ComparisonResult tests
# ---------------------------------------------------------------------------


class TestComparisonResult:
    """Tests for the ComparisonResult dataclass."""

    def test_best_returns_top_ranked(self):
        """best() should return the first result (rank 1)."""
        r1 = GeneratorResult(generator_name="best", fidelity_score=0.9, overall_rank=1)
        r2 = GeneratorResult(generator_name="worst", fidelity_score=0.1, overall_rank=2)
        cr = ComparisonResult(results=[r1, r2])
        assert cr.best().generator_name == "best"

    def test_best_raises_on_empty(self):
        """best() should raise ValueError when results is empty."""
        cr = ComparisonResult(results=[])
        with pytest.raises(ValueError, match="empty"):
            cr.best()

    def test_to_dict_round_trips(self):
        """to_dict should produce a JSON-serializable structure."""
        import json

        r1 = GeneratorResult(generator_name="a", fidelity_score=0.5, overall_rank=1)
        cr = ComparisonResult(results=[r1])
        d = cr.to_dict()
        # Should be JSON-serializable without error.
        json_str = json.dumps(d)
        assert "a" in json_str


# ---------------------------------------------------------------------------
# Integration: compare_generators
# ---------------------------------------------------------------------------


class TestCompareGenerators:
    """Integration tests for compare_generators with real generators."""

    def test_compare_two_generators_produces_ranked_results(self, source_array):
        """Comparing 2 generators should produce 2 ranked results."""
        result = compare_generators(
            source_data=source_array,
            generators=["block_bootstrap", "regime_block_bootstrap"],
            n=100,
            seed=42,
        )
        assert len(result.results) == 2
        # Both should have ranks assigned.
        ranks = {r.overall_rank for r in result.results}
        assert ranks == {1, 2}
        # best() should return rank 1.
        assert result.best().overall_rank == 1

    def test_compare_single_generator(self, source_array):
        """Comparing a single generator should produce 1 result with rank 1."""
        result = compare_generators(
            source_data=source_array,
            generators=["block_bootstrap"],
            n=100,
            seed=42,
        )
        assert len(result.results) == 1
        assert result.best().overall_rank == 1
        assert result.best().generator_name == "block_bootstrap"

    def test_unknown_generator_fails_closed(self, source_array):
        """An unknown generator name should produce an error result, not crash."""
        result = compare_generators(
            source_data=source_array,
            generators=["block_bootstrap", "nonexistent_generator"],
            n=100,
            seed=42,
        )
        assert len(result.results) == 2
        # The unknown generator should have an error and rank last.
        errored = [r for r in result.results if r.error is not None]
        assert len(errored) == 1
        assert errored[0].generator_name == "nonexistent_generator"
        assert errored[0].overall_rank == 2


# ---------------------------------------------------------------------------
# Promotion tests
# ---------------------------------------------------------------------------


class TestPromotion:
    """Tests for the promotion logic with a real SQLite registry."""

    def test_promote_creates_dataset_spec(self, registry_db):
        """promote_run should create a DatasetSpec in the registry."""
        dataset_id = promote_run("run-abc-123", "spy-synthetic", registry_db)
        assert dataset_id == "promoted:spy-synthetic"
        # Verify it exists in the registry.
        datasets = registry_db.list_datasets()
        assert len(datasets) == 1
        assert datasets[0].dataset_id == "promoted:spy-synthetic"
        assert datasets[0].source == "synthetic:run-abc-123"
        assert datasets[0].metadata["promoted"] is True

    def test_get_promoted_retrieves_it(self, registry_db):
        """get_promoted should return the promoted DatasetSpec."""
        promote_run("run-xyz", "my-dataset", registry_db)
        spec = get_promoted("my-dataset", registry_db)
        assert spec is not None
        assert spec.dataset_id == "promoted:my-dataset"
        assert spec.source == "synthetic:run-xyz"

    def test_get_promoted_returns_none_when_missing(self, registry_db):
        """get_promoted should return None when no promoted dataset exists."""
        spec = get_promoted("nonexistent", registry_db)
        assert spec is None

    def test_list_promoted_returns_all(self, registry_db):
        """list_promoted should return all promoted datasets."""
        promote_run("run-1", "dataset-a", registry_db)
        promote_run("run-2", "dataset-b", registry_db)
        promoted = list_promoted(registry_db)
        assert len(promoted) == 2
        names = {s.name for s in promoted}
        assert names == {"dataset-a", "dataset-b"}

    def test_re_promote_updates_existing(self, registry_db):
        """Re-promoting the same dataset name should update the source."""
        promote_run("run-old", "my-data", registry_db)
        promote_run("run-new", "my-data", registry_db)
        spec = get_promoted("my-data", registry_db)
        assert spec is not None
        # Should point to the new run, not the old one.
        assert spec.source == "synthetic:run-new"
        # Should still be only one promoted entry for this name.
        promoted = list_promoted(registry_db)
        assert len(promoted) == 1
