"""Tests for the synthetic dataset catalog.

Covers the three public functions in :mod:`the_similarity.synthetic.catalog`:
- :func:`register_synthetic_dataset` — file stats + DatasetSpec creation
- :func:`list_catalog` — filtering by synthetic source + promoted flag
- :func:`get_dataset_card` — card assembly with scorecard summary

All tests use an in-memory-ish tmp-path registry and synthetic run
directories with minimal parquet files so the test suite stays fast
(no network, no real data).
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from the_similarity.platform.contracts import DatasetSpec
from the_similarity.platform.registry import RunRegistry
from the_similarity.synthetic.catalog import (
    get_dataset_card,
    list_catalog,
    register_synthetic_dataset,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def registry(tmp_path: Path) -> RunRegistry:
    """Fresh SQLite registry in a temp directory."""
    db_path = tmp_path / "test_registry.db"
    return RunRegistry(db_path)


@pytest.fixture()
def run_dir(tmp_path: Path) -> Path:
    """Create a minimal synthetic run directory with parquet + scorecard."""
    rdir = tmp_path / "runs" / "block_bootstrap-42-20260415-120000"
    rdir.mkdir(parents=True)

    # Write a small synth.parquet (5 rows, 3 columns)
    df_synth = pd.DataFrame(
        np.random.default_rng(42).standard_normal((5, 3)),
        columns=["close", "volume", "returns"],
    )
    df_synth.to_parquet(rdir / "synth.parquet", index=False)

    # Write a small real.parquet
    df_real = pd.DataFrame(
        np.random.default_rng(0).standard_normal((10, 3)),
        columns=["close", "volume", "returns"],
    )
    df_real.to_parquet(rdir / "real.parquet", index=False)

    # Write scorecard.json with fidelity + privacy + utility sections
    scorecard = {
        "passed": True,
        "fidelity": {
            "overall_score": 0.85,
            "passed": True,
            "marginals": {"ks_mean": 0.05},
        },
        "privacy": {
            "overall_score": 0.92,
            "passed": True,
        },
        "utility": {
            "transfer_gap": 0.03,
            "passed": True,
        },
        "dataset": {
            "shape": [5, 3],
            "columns": ["close", "volume", "returns"],
        },
    }
    (rdir / "scorecard.json").write_text(json.dumps(scorecard))

    return rdir


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestRegisterSyntheticDataset:
    """Tests for :func:`register_synthetic_dataset`."""

    def test_registers_with_correct_fields(
        self, registry: RunRegistry, run_dir: Path
    ) -> None:
        """DatasetSpec is created with correct n_rows, n_columns, source."""
        dataset_id = register_synthetic_dataset(
            run_id="abc123",
            name="test-dataset",
            version="v1",
            run_dir=run_dir,
            registry=registry,
        )

        assert dataset_id == "synthetic-abc123"

        # Verify the spec was registered
        datasets = registry.list_datasets()
        assert len(datasets) == 1

        spec = datasets[0]
        assert spec.dataset_id == "synthetic-abc123"
        assert spec.name == "test-dataset"
        assert spec.version == "v1"
        assert spec.source == "synthetic:abc123"
        assert spec.n_rows == 5
        assert spec.n_columns == 3
        # Checksum should be a 64-char hex string
        assert spec.checksum is not None
        assert len(spec.checksum) == 64

    def test_metadata_includes_scorecard_summary(
        self, registry: RunRegistry, run_dir: Path
    ) -> None:
        """Registered metadata embeds scorecard headline metrics."""
        register_synthetic_dataset(
            run_id="abc123",
            name="test-ds",
            version="v1",
            run_dir=run_dir,
            registry=registry,
        )

        spec = registry.list_datasets()[0]
        sc = spec.metadata.get("scorecard_summary", {})
        assert sc["passed"] is True
        assert sc["fidelity_score"] == 0.85
        assert sc["privacy_passed"] is True

    def test_missing_synth_parquet_raises(
        self, registry: RunRegistry, tmp_path: Path
    ) -> None:
        """FileNotFoundError when synth.parquet is missing."""
        empty_dir = tmp_path / "empty_run"
        empty_dir.mkdir()

        with pytest.raises(FileNotFoundError, match="synth.parquet"):
            register_synthetic_dataset(
                run_id="nope",
                name="bad",
                version="v1",
                run_dir=empty_dir,
                registry=registry,
            )

    def test_no_checksum_when_disabled(
        self, registry: RunRegistry, run_dir: Path
    ) -> None:
        """Checksum is None when compute_checksum=False."""
        register_synthetic_dataset(
            run_id="fast",
            name="fast-ds",
            version="v1",
            run_dir=run_dir,
            registry=registry,
            compute_checksum=False,
        )

        spec = registry.list_datasets()[0]
        assert spec.checksum is None


class TestListCatalog:
    """Tests for :func:`list_catalog`."""

    def test_returns_only_synthetic_datasets(
        self, registry: RunRegistry, run_dir: Path
    ) -> None:
        """Non-synthetic datasets are excluded from the catalog listing."""
        # Register one synthetic dataset
        register_synthetic_dataset(
            run_id="syn1",
            name="synth-ds",
            version="v1",
            run_dir=run_dir,
            registry=registry,
        )

        # Register a non-synthetic dataset directly
        non_synth = DatasetSpec(
            dataset_id="real-spy",
            name="SPY daily",
            version="v1",
            source="the-similarity-data/equity/spy.parquet",
        )
        registry.register_dataset(non_synth)

        result = list_catalog(registry)
        assert len(result) == 1
        assert result[0].dataset_id == "synthetic-syn1"

    def test_promoted_only_filter(self, registry: RunRegistry, run_dir: Path) -> None:
        """promoted_only=True filters to datasets with promoted metadata."""
        # Register a non-promoted synthetic dataset
        register_synthetic_dataset(
            run_id="unpromoted",
            name="unpromoted-ds",
            version="v1",
            run_dir=run_dir,
            registry=registry,
        )

        # Register a promoted dataset manually
        promoted = DatasetSpec(
            dataset_id="synthetic-promoted1",
            name="promoted-ds",
            version="v1",
            source="synthetic:promoted1",
            metadata={"promoted": True},
        )
        registry.register_dataset(promoted)

        # Without filter: both
        all_synth = list_catalog(registry)
        assert len(all_synth) == 2

        # With filter: only promoted
        promoted_only = list_catalog(registry, promoted_only=True)
        assert len(promoted_only) == 1
        assert promoted_only[0].dataset_id == "synthetic-promoted1"


class TestGetDatasetCard:
    """Tests for :func:`get_dataset_card`."""

    def test_card_includes_scorecard_summary(
        self, registry: RunRegistry, run_dir: Path
    ) -> None:
        """Dataset card surfaces scorecard metrics from registration metadata."""
        register_synthetic_dataset(
            run_id="card1",
            name="card-ds",
            version="v2",
            run_dir=run_dir,
            registry=registry,
        )

        card = get_dataset_card("synthetic-card1", registry)

        assert card["dataset_id"] == "synthetic-card1"
        assert card["name"] == "card-ds"
        assert card["version"] == "v2"
        assert card["source_run_id"] == "card1"
        assert card["n_rows"] == 5
        assert card["n_columns"] == 3
        assert card["privacy_status"] == "passed"

        sc = card["scorecard_summary"]
        assert sc["fidelity_score"] == 0.85
        assert sc["utility_transfer_gap"] == 0.03

    def test_missing_dataset_raises_keyerror(self, registry: RunRegistry) -> None:
        """KeyError when dataset_id is not in the registry."""
        with pytest.raises(KeyError, match="nonexistent"):
            get_dataset_card("nonexistent", registry)
