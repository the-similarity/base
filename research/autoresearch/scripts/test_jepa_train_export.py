"""Tests for the JEPA train-and-export pipeline.

Uses tiny synthetic data (random walk) with minimal epochs to keep tests
fast while verifying the full pipeline: train -> save -> load -> retrieve.

All tests use ``tmp_path`` fixtures to avoid polluting the repo with artifacts.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest

# Add the scripts directory to the path so imports resolve
sys.path.insert(0, str(Path(__file__).resolve().parent))

from jepa_data_spec import build_jepa_dataset_from_array, temporal_split
from jepa_train_and_export import (
    embedding_retrieval_fn,
    load_embeddings,
    train_and_export_from_array,
)


def _synthetic_prices(n: int = 500, seed: int = 42) -> np.ndarray:
    """Generate a synthetic random-walk price series for testing.

    Returns a 1-D array of length ``n`` with positive values resembling
    a geometric random walk.
    """
    rng = np.random.RandomState(seed)
    returns = rng.randn(n) * 0.02  # ~2% daily vol
    prices = 100.0 * np.exp(np.cumsum(returns))
    return prices


class TestTrainAndExport:
    """Verify the end-to-end train_and_export_from_array pipeline."""

    def test_train_and_export_creates_artifacts(self, tmp_path: Path) -> None:
        """Pipeline should create encoder.pt, embeddings.npz, and metadata.json."""
        prices = _synthetic_prices(300, seed=7)
        result = train_and_export_from_array(
            prices,
            tmp_path,
            window_size=20,
            stride=5,
            latent_dim=16,
            epochs=2,
            batch_size=16,
            seed=7,
            verbose=False,
        )

        # All three artifact files must exist
        assert (tmp_path / "encoder.pt").exists(), "encoder.pt missing"
        assert (tmp_path / "embeddings.npz").exists(), "embeddings.npz missing"
        assert (tmp_path / "metadata.json").exists(), "metadata.json missing"

        # Result dict has expected keys
        assert result["n_windows"] > 0
        assert result["latent_dim"] == 16
        assert result["final_loss"] is not None

    def test_embeddings_shape(self, tmp_path: Path) -> None:
        """Exported embeddings should have shape (n_windows, latent_dim)."""
        prices = _synthetic_prices(200, seed=11)
        result = train_and_export_from_array(
            prices,
            tmp_path,
            window_size=15,
            stride=3,
            latent_dim=8,
            epochs=2,
            batch_size=8,
            seed=11,
            verbose=False,
        )

        data = np.load(tmp_path / "embeddings.npz")
        embeddings = data["embeddings"]

        # Shape must match (n_windows, latent_dim)
        assert embeddings.shape[0] == result["n_windows"]
        assert embeddings.shape[1] == 8  # latent_dim

        # Split indices should cover all windows
        train_idx = data["split_train"]
        val_idx = data["split_val"]
        test_idx = data["split_test"]
        total_split = len(train_idx) + len(val_idx) + len(test_idx)
        assert total_split == result["n_windows"]


class TestLoadEmbeddings:
    """Verify round-trip: export then load."""

    def test_load_round_trip(self, tmp_path: Path) -> None:
        """load_embeddings should recover the same data that was exported."""
        prices = _synthetic_prices(250, seed=21)
        train_and_export_from_array(
            prices,
            tmp_path,
            window_size=20,
            stride=5,
            latent_dim=16,
            epochs=2,
            batch_size=16,
            seed=21,
            verbose=False,
        )

        loaded = load_embeddings(tmp_path)

        # Check keys
        assert "embeddings" in loaded
        assert "offsets" in loaded
        assert "split_train" in loaded
        assert "split_val" in loaded
        assert "split_test" in loaded
        assert "metadata" in loaded

        # Metadata should have dataset and training info
        meta = loaded["metadata"]
        assert meta["latent_dim"] == 16
        assert meta["window_size"] == 20
        assert len(meta["loss_history"]) == 2  # 2 epochs

        # Embeddings shape consistency
        assert loaded["embeddings"].shape[0] == meta["n_windows"]
        assert loaded["embeddings"].shape[1] == meta["latent_dim"]

    def test_load_missing_dir_raises(self, tmp_path: Path) -> None:
        """load_embeddings should raise FileNotFoundError for missing artifacts."""
        with pytest.raises(FileNotFoundError):
            load_embeddings(tmp_path / "nonexistent")


class TestEmbeddingRetrievalFn:
    """Verify the cosine-similarity retrieval function."""

    def test_returns_k_results(self) -> None:
        """Retrieval function should return exactly k neighbors."""
        rng = np.random.RandomState(99)
        # 50 embeddings of dimension 8
        embeddings = rng.randn(50, 8).astype(np.float32)
        k = 5

        retrieve = embedding_retrieval_fn(embeddings, k=k)
        neighbors = retrieve(0)

        assert len(neighbors) == k
        # Query index should not be in its own results
        assert 0 not in neighbors

    def test_returns_fewer_than_k_if_not_enough(self) -> None:
        """If there are fewer candidates than k, return all available."""
        rng = np.random.RandomState(100)
        embeddings = rng.randn(3, 4).astype(np.float32)
        k = 10

        retrieve = embedding_retrieval_fn(embeddings, k=k)
        neighbors = retrieve(0)

        # Only 2 other embeddings available (excluding query)
        assert len(neighbors) == 2
        assert 0 not in neighbors

    def test_candidate_mask_restricts_search(self) -> None:
        """When a candidate_mask is provided, results stay within the mask."""
        rng = np.random.RandomState(101)
        embeddings = rng.randn(20, 4).astype(np.float32)
        # Only allow indices 0-9 as candidates
        mask = np.zeros(20, dtype=bool)
        mask[:10] = True

        retrieve = embedding_retrieval_fn(embeddings, k=5, candidate_mask=mask)
        # Query from outside the mask
        neighbors = retrieve(15)

        assert len(neighbors) == 5
        # All results should be within the masked indices
        assert all(n < 10 for n in neighbors)

    def test_similar_embeddings_rank_higher(self) -> None:
        """Cosine retrieval should rank truly similar vectors first."""
        # Create a clear structure: first 5 embeddings cluster together
        embeddings = np.zeros((10, 4), dtype=np.float32)
        embeddings[:5] = np.array([1, 0, 0, 0])  # cluster A
        embeddings[5:] = np.array([0, 1, 0, 0])   # cluster B
        # Add tiny noise to avoid exact ties
        rng = np.random.RandomState(102)
        embeddings += rng.randn(10, 4).astype(np.float32) * 0.01

        retrieve = embedding_retrieval_fn(embeddings, k=4)
        neighbors = retrieve(0)

        # Query 0 is in cluster A, so its neighbors should be from cluster A
        assert all(n < 5 for n in neighbors), (
            f"Expected cluster-A neighbors, got {neighbors}"
        )


class TestDataSpec:
    """Verify data spec helpers used by the pipeline."""

    def test_build_from_array_shape(self) -> None:
        """build_jepa_dataset_from_array should produce correct shapes."""
        prices = _synthetic_prices(150, seed=33)
        ds = build_jepa_dataset_from_array(prices, window_size=20, stride=5)

        assert ds.windows.ndim == 3
        assert ds.windows.shape[1] == 1  # single channel
        assert ds.windows.shape[2] == 20  # window_size
        assert len(ds.window_offsets) == ds.windows.shape[0]

    def test_temporal_split_covers_all(self) -> None:
        """temporal_split indices should partition [0, n) completely."""
        splits = temporal_split(100)
        all_idx = np.concatenate([splits.train_idx, splits.val_idx, splits.test_idx])
        assert len(all_idx) == 100
        assert np.array_equal(np.sort(all_idx), np.arange(100))

    def test_temporal_split_is_ordered(self) -> None:
        """Train indices should all come before val, which come before test."""
        splits = temporal_split(100)
        assert splits.train_idx[-1] < splits.val_idx[0]
        assert splits.val_idx[-1] < splits.test_idx[0]


class TestEndToEndWithRetrieval:
    """Integration: train, export, load, and run retrieval."""

    def test_full_pipeline(self, tmp_path: Path) -> None:
        """Full cycle: train -> export -> load -> retrieve -> get results."""
        prices = _synthetic_prices(300, seed=55)

        # Train and export
        train_and_export_from_array(
            prices,
            tmp_path,
            window_size=20,
            stride=5,
            latent_dim=16,
            epochs=2,
            batch_size=16,
            seed=55,
            verbose=False,
        )

        # Load
        loaded = load_embeddings(tmp_path)
        embeddings = loaded["embeddings"]
        test_idx = loaded["split_test"]

        # Build retrieval function restricted to training set
        train_mask = np.zeros(len(embeddings), dtype=bool)
        train_mask[loaded["split_train"]] = True
        retrieve = embedding_retrieval_fn(embeddings, k=5, candidate_mask=train_mask)

        # Run retrieval on test queries
        for qidx in test_idx[:3]:  # test a few queries
            neighbors = retrieve(int(qidx))
            assert len(neighbors) > 0, f"No neighbors for query {qidx}"
            assert len(neighbors) <= 5
            # All neighbors should be from the training set
            assert all(train_mask[n] for n in neighbors)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
