"""Tests for the FeatureStore caching layer."""
import tempfile
import numpy as np
import pytest

from the_similarity.core.feature_store import FeatureStore, dataset_hash, params_hash


class TestDatasetHash:
    def test_deterministic(self):
        arr = np.arange(1000, dtype=np.float64)
        assert dataset_hash(arr) == dataset_hash(arr)

    def test_detects_changes(self):
        arr1 = np.arange(1000, dtype=np.float64)
        arr2 = arr1.copy()
        arr2[500] = 999.0  # change a value that's sampled (every 100th)
        assert dataset_hash(arr1) != dataset_hash(arr2)

    def test_different_lengths(self):
        arr1 = np.arange(100, dtype=np.float64)
        arr2 = np.arange(200, dtype=np.float64)
        assert dataset_hash(arr1) != dataset_hash(arr2)

    def test_empty_array(self):
        h = dataset_hash(np.array([], dtype=np.float64))
        assert isinstance(h, str)
        assert len(h) > 0


class TestParamsHash:
    def test_same_params_same_hash(self):
        h1 = params_hash("koopman", dim=8, lag=3)
        h2 = params_hash("koopman", dim=8, lag=3)
        assert h1 == h2

    def test_different_params_different_hash(self):
        h1 = params_hash("koopman", dim=8, lag=3)
        h2 = params_hash("koopman", dim=10, lag=3)
        assert h1 != h2

    def test_different_methods_different_hash(self):
        h1 = params_hash("koopman", dim=8)
        h2 = params_hash("wavelet", dim=8)
        assert h1 != h2


class TestFeatureStore:
    def test_miss_then_hit(self):
        with tempfile.NamedTemporaryFile(suffix=".db") as f:
            store = FeatureStore(f.name)
            call_count = 0

            def compute():
                nonlocal call_count
                call_count += 1
                return 0.85

            # First call: MISS -> compute
            result1 = store.get_or_compute("abc", 100, 60, "koopman", "xyz", compute)
            assert result1 == 0.85
            assert call_count == 1

            # Second call: HIT -> no compute
            result2 = store.get_or_compute("abc", 100, 60, "koopman", "xyz", compute)
            assert result2 == 0.85
            assert call_count == 1  # not called again

    def test_different_keys_no_collision(self):
        with tempfile.NamedTemporaryFile(suffix=".db") as f:
            store = FeatureStore(f.name)
            r1 = store.get_or_compute("abc", 100, 60, "koopman", "xyz", lambda: 0.85)
            r2 = store.get_or_compute("abc", 200, 60, "koopman", "xyz", lambda: 0.42)
            assert r1 == 0.85
            assert r2 == 0.42

    def test_size(self):
        with tempfile.NamedTemporaryFile(suffix=".db") as f:
            store = FeatureStore(f.name)
            assert store.size == 0
            store.get_or_compute("a", 0, 60, "m", "p", lambda: 1.0)
            assert store.size == 1
            store.get_or_compute("a", 1, 60, "m", "p", lambda: 2.0)
            assert store.size == 2

    def test_clear(self):
        with tempfile.NamedTemporaryFile(suffix=".db") as f:
            store = FeatureStore(f.name)
            store.get_or_compute("a", 0, 60, "m", "p", lambda: 1.0)
            assert store.size == 1
            store.clear()
            assert store.size == 0

    def test_caches_numpy_arrays(self):
        with tempfile.NamedTemporaryFile(suffix=".db") as f:
            store = FeatureStore(f.name)
            arr = np.array([1.0, 2.0, 3.0])
            result = store.get_or_compute("a", 0, 60, "m", "p", lambda: arr)
            np.testing.assert_array_equal(result, arr)

            # Read from cache
            cached = store.get_or_compute("a", 0, 60, "m", "p", lambda: None)
            np.testing.assert_array_equal(cached, arr)

    def test_corrupt_db_falls_through(self, tmp_path):
        db_path = tmp_path / "test.db"
        store = FeatureStore(db_path)
        store.get_or_compute("a", 0, 60, "m", "p", lambda: 42)

        # Corrupt the database file
        with open(db_path, "wb") as f:
            f.write(b"THIS IS NOT A SQLITE DATABASE")

        # Should warn and fall through to compute
        with pytest.warns(RuntimeWarning):
            result = store.get_or_compute("a", 0, 60, "m", "p", lambda: 99)
        assert result == 99


@pytest.mark.slow
class TestFeatureStoreIntegration:
    def test_search_with_feature_store(self):
        """search() with FeatureStore should produce same results."""
        import tempfile
        from the_similarity.api import search
        from the_similarity.config import Config

        history = 100 + np.cumsum(np.random.RandomState(42).randn(500) * 0.5)
        query = history[200:260]
        config = Config(
            active_methods=["dtw", "pearson_warped", "koopman"],
            tier1_candidates=50,
            tier2_candidates=5,
            stride=5,
        )

        # Without cache
        r1 = search(query=query, history=history, top_k=3, config=config)

        # With cache
        with tempfile.NamedTemporaryFile(suffix=".db") as f:
            store = FeatureStore(f.name)
            r2 = search(query=query, history=history, top_k=3, config=config, feature_store=store)

            # Results should be identical
            assert len(r1.matches) == len(r2.matches)
            for m1, m2 in zip(r1.matches, r2.matches):
                assert m1.start_idx == m2.start_idx
                assert abs(m1.confidence_score - m2.confidence_score) < 1e-6

            # Cache should have entries
            assert store.size > 0

            # Second call should use cache (same results)
            r3 = search(query=query, history=history, top_k=3, config=config, feature_store=store)
            assert len(r2.matches) == len(r3.matches)
