"""SQLite-backed feature cache for expensive method computations.

Caches results of Tier 2 methods (Bempedelis, Koopman, Wavelet, EMD, TDA)
and MASS profile to avoid redundant computation during backtesting.

Architecture:
    ┌─────────────────────────────────────────────┐
    │              FeatureStore                     │
    │                                               │
    │  get_or_compute(key, compute_fn) -> result    │
    │    ├── HIT  → deserialize → return            │
    │    └── MISS → compute → serialize → store     │
    │                                               │
    │  Key: (dataset_hash, window_start,            │
    │        window_length, method, params_hash)    │
    │                                               │
    │  Backend: SQLite (process-safe)               │
    │  Serialization: pickle                        │
    └─────────────────────────────────────────────┘

Caching Lifecycle and Strict Invariants:
- Advisory Fallback: The cache is ADVISORY. It strictly fails-open on SQlite 
  locks or corruption, falling through to recompute `compute_fn()` and raising a 
  `RuntimeWarning`.
- Invalidation Strategy: Keys are composite `(dataset_hash:start:len:method:params_hash)`. 
  Mutating dataset contents (captured via sparse hash), configuration, or the target 
  window length naturally orphans old records.
- Concurrency: Uses SQLite WAL (`PRAGMA journal_mode=WAL`). This guarantees 
  non-blocking safe reads for concurrent processes (via `ProcessPoolExecutor`).
- Serialization: Pickling is mandatory because tier-2 methods yield arbitrary 
  object graphs (e.g. `numpy` structural spectra or custom dataclasses). JSON 
  would permanently strip shape and class metadata.
"""
from __future__ import annotations

import hashlib
import pickle
import sqlite3
import time
import warnings
from pathlib import Path
from typing import Any, Callable, TypeVar

import numpy as np
from numpy.typing import NDArray

T = TypeVar("T")


def dataset_hash(history: NDArray[np.float64]) -> str:
    """Compute a sparse hash of a history array.

    Uses O(n/100) sampling: length + first + last + every 100th value.
    Catches real data changes with negligible false positives.

    Why sparse sampling instead of full hash:
    - A 10,000-element float64 array is 80KB. SHA-256 over that for every
      cache lookup would dominate the cost of cheap Tier 2 methods.
    - Sampling every 100th element covers ~100 points, which is enough to
      detect: dataset swaps, data refreshes, truncation, and corruption.
    - The 16-hex-char truncation gives 64 bits of collision resistance,
      which is more than sufficient for cache keys.
    """
    h = hashlib.sha256()
    # Include array length — catches truncation and padding
    h.update(str(len(history)).encode())
    if len(history) > 0:
        # First and last values catch most common data mutations
        h.update(history[0].tobytes())
        h.update(history[-1].tobytes())
        # Sparse interior sampling catches mid-series changes
        for i in range(0, len(history), 100):
            h.update(history[i].tobytes())
    return h.hexdigest()[:16]


def params_hash(method: str, **kwargs) -> str:
    """Hash method-specific parameters for cache key differentiation.

    Different config values (e.g., sax_n_segments=16 vs 32) produce
    different hashes, ensuring config changes auto-invalidate cache.
    """
    h = hashlib.sha256()
    h.update(method.encode())
    for key in sorted(kwargs.keys()):
        h.update(f"{key}={kwargs[key]}".encode())
    return h.hexdigest()[:12]


class FeatureStore:
    """SQLite-backed cache for expensive feature computations.

    Thread-safe and process-safe (uses SQLite WAL mode).
    Designed for use with ProcessPoolExecutor in the backtester.

    Usage:
        store = FeatureStore("/tmp/similarity_cache.db")
        score = store.get_or_compute(
            dataset_hash="abc123",
            window_start=100,
            window_length=60,
            method="koopman",
            params_hash="def456",
            compute_fn=lambda: koopman_match(query, candidate),
        )
    """

    def __init__(self, db_path: str | Path):
        self._db_path = str(db_path)
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        """Create a new connection per call (safe for multi-process use).

        Why a new connection each time (not pooled):
        - SQLite connections are NOT safely shareable across processes.
        - ProcessPoolExecutor workers each need their own connection.
        - A 10ms connection overhead is negligible vs. Tier 2 compute time.
        """
        conn = sqlite3.connect(self._db_path, timeout=10)
        # WAL (Write-Ahead Logging) mode allows concurrent readers and a
        # single writer, which is critical for multi-process backtesting.
        conn.execute("PRAGMA journal_mode=WAL")
        # NORMAL synchronous mode trades a tiny crash-safety margin for
        # ~2× write speed. Cache data is non-critical and can be rebuilt.
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    def _ensure_schema(self) -> None:
        """Create the features table if it doesn't exist."""
        conn = self._connect()
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS features (
                    cache_key TEXT PRIMARY KEY,
                    value BLOB NOT NULL,
                    created_at REAL NOT NULL
                )
            """)
            conn.commit()
        finally:
            conn.close()

    def _make_key(
        self,
        dataset_hash: str,
        window_start: int,
        window_length: int,
        method: str,
        params_hash: str,
    ) -> str:
        return f"{dataset_hash}:{window_start}:{window_length}:{method}:{params_hash}"

    def get_or_compute(
        self,
        dataset_hash: str,
        window_start: int,
        window_length: int,
        method: str,
        params_hash: str,
        compute_fn: Callable[[], T],
    ) -> T:
        """Get cached result or compute and store it.

        If the cache is corrupt or unreadable, falls through to
        compute_fn() with a warning (cache is advisory, not critical).

        Args:
            dataset_hash: Hash of the history array.
            window_start: Start index of the window.
            window_length: Length of the window.
            method: Method name (e.g., "koopman", "bempedelis").
            params_hash: Hash of method-specific parameters.
            compute_fn: Callable that computes the result if not cached.

        Returns:
            The cached or computed result.
        """
        key = self._make_key(dataset_hash, window_start, window_length, method, params_hash)

        # Try to read from cache
        try:
            conn = self._connect()
            try:
                row = conn.execute(
                    "SELECT value FROM features WHERE cache_key = ?", (key,)
                ).fetchone()
                if row is not None:
                    return pickle.loads(row[0])
            finally:
                conn.close()
        except (sqlite3.DatabaseError, pickle.UnpicklingError, Exception) as exc:
            warnings.warn(
                f"FeatureStore read failed for {method}@{window_start}: {exc}",
                RuntimeWarning,
                stacklevel=2,
            )

        # Cache miss — compute
        result = compute_fn()

        # Store in cache
        try:
            conn = self._connect()
            try:
                conn.execute(
                    "INSERT OR REPLACE INTO features (cache_key, value, created_at) VALUES (?, ?, ?)",
                    (key, pickle.dumps(result), time.time()),
                )
                conn.commit()
            finally:
                conn.close()
        except (sqlite3.DatabaseError, Exception) as exc:
            warnings.warn(
                f"FeatureStore write failed for {method}@{window_start}: {exc}",
                RuntimeWarning,
                stacklevel=2,
            )

        return result

    @property
    def size(self) -> int:
        """Number of cached entries."""
        try:
            conn = self._connect()
            try:
                row = conn.execute("SELECT COUNT(*) FROM features").fetchone()
                return row[0] if row else 0
            finally:
                conn.close()
        except sqlite3.DatabaseError:
            return 0

    def clear(self) -> None:
        """Delete all cached entries."""
        conn = self._connect()
        try:
            conn.execute("DELETE FROM features")
            conn.commit()
        finally:
            conn.close()
