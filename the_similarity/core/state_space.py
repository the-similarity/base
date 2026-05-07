"""Shared state-space embedding and indexing for cross-pillar run comparison.

Each pillar (finance, copies, worlds) produces runs with heterogeneous metric
shapes. This module normalizes every run's summary into a fixed-length
:class:`StateVector`, stores them in a :class:`StateIndex` for nearest-neighbor
retrieval, and provides dimensionality reduction helpers for 2D/3D
visualization.

Why this exists
---------------
The platform registry stores raw ``summary`` dicts whose keys and ranges differ
by pillar (finance has ``hit_rate`` in [0, 1]; worlds has ``alive`` in
[0, 10_000]). To compare runs *across* pillars — "which world run behaves
most like this finance run?" — we need a shared numeric representation. The
``StateVector`` is that representation: a unit-hypercube vector where each
dimension is min-max normalized against known reasonable ranges.

Normalization contract
----------------------
Each extractor defines a ``(min, max)`` range per metric. Values outside
the range are clamped (not clipped silently — the clamp *is* the
normalization). Missing keys default to 0.5 (the midpoint), which is a
neutral "no information" signal — it will not pull the vector toward either
extreme in cosine distance.

Memory / performance
--------------------
:class:`StateIndex` is a brute-force numpy implementation (O(n*d) per query).
This is intentional: the registry will hold hundreds to low-thousands of runs,
not millions. External dependencies (faiss, annoy) are avoided to keep the
install lightweight. If the index grows past ~50k vectors, swap the query
implementation for a ball-tree or upgrade to faiss.

Thread safety
-------------
:class:`StateIndex` is **not** thread-safe. The backing list and numpy cache
are mutated by ``add`` / ``add_batch``. Callers must synchronize externally or
instantiate one index per thread.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from numpy.typing import NDArray


# ---------------------------------------------------------------------------
# StateVector — the canonical cross-pillar embedding
# ---------------------------------------------------------------------------


@dataclass
class StateVector:
    """A normalized numeric vector representing one run's summary metrics.

    Attributes
    ----------
    vector : np.ndarray
        1-D float64 array with values in [0, 1]. Length depends on the
        source pillar (finance=5, copies=3, worlds=5).
    source_id : str
        The ``run_id`` from the platform registry.
    source_kind : str
        Pillar tag: ``"finance"``, ``"copies"``, or ``"worlds"``.
    label : str
        Human-readable label for display (e.g. "SPY backtest seed=42").
    metadata : dict
        Arbitrary extra context carried alongside the vector. Not used
        in distance computations.
    """

    vector: NDArray[np.float64]
    source_id: str
    source_kind: str
    label: str
    metadata: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Normalization ranges
# ---------------------------------------------------------------------------
# Each tuple is (metric_key, min_value, max_value). Values are clamped to
# [min, max] then linearly mapped to [0, 1]. The ranges are based on
# empirically observed outputs from each pillar's runners.

# Finance: backtest summary metrics
# - hit_rate: fraction of cones containing the realized value [0, 1]
# - crps: continuous ranked probability score — lower is better [0, 1]
# - coverage: empirical coverage of the prediction interval [0, 1]
# - trust_score: composite trust metric from trust_filter [0, 1]
# - calibration_grade_numeric: numeric grade (0=F ... 4=A) [0, 4]
_FINANCE_RANGES: List[Tuple[str, float, float]] = [
    ("hit_rate", 0.0, 1.0),
    ("crps", 0.0, 1.0),
    ("coverage", 0.0, 1.0),
    ("trust_score", 0.0, 1.0),
    ("calibration_grade_numeric", 0.0, 4.0),
]

# Copies (synthetic data): fidelity/privacy/utility scorecards
# - fidelity_score: aggregate distribution similarity [0, 1]
# - privacy_score: re-identification resistance [0, 1]
# - utility_gap: TRTS-vs-TSTR performance gap [0, 1] (lower = better)
_COPIES_RANGES: List[Tuple[str, float, float]] = [
    ("fidelity_score", 0.0, 1.0),
    ("privacy_score", 0.0, 1.0),
    ("utility_gap", 0.0, 1.0),
]

# Worlds (simulation): headless runner telemetry summary
# - alive: count of living agents at end of simulation [0, 10_000]
# - dead: count of dead agents [0, 10_000]
# - mean_energy: average energy across living agents [0, 200]
# - food_count: available food items on the grid [0, 5_000]
# - population_density: agents per grid cell [0, 1]
_WORLDS_RANGES: List[Tuple[str, float, float]] = [
    ("alive", 0.0, 10_000.0),
    ("dead", 0.0, 10_000.0),
    ("mean_energy", 0.0, 200.0),
    ("food_count", 0.0, 5_000.0),
    ("population_density", 0.0, 1.0),
]

# Dimension counts for each pillar — used for validation and pre-allocation
FINANCE_DIM = len(_FINANCE_RANGES)  # 5
COPIES_DIM = len(_COPIES_RANGES)  # 3
WORLDS_DIM = len(_WORLDS_RANGES)  # 5

# The maximum dimension across all pillars. Vectors from smaller pillars
# are padded with 0.5 (neutral) to this length when inserted into a
# mixed-pillar index so that cosine distance is computed in a shared space.
MAX_DIM = max(FINANCE_DIM, COPIES_DIM, WORLDS_DIM)  # 5


# ---------------------------------------------------------------------------
# Extractor helpers
# ---------------------------------------------------------------------------


def _normalize(
    value: float,
    lo: float,
    hi: float,
) -> float:
    """Clamp *value* to [lo, hi] then linearly map to [0, 1].

    Edge case: if lo == hi the output is 0.5 (undefined range -> neutral).
    """
    if hi <= lo:
        return 0.5
    clamped = max(lo, min(hi, value))
    return (clamped - lo) / (hi - lo)


def _extract(
    summary: Dict[str, Any],
    ranges: List[Tuple[str, float, float]],
    *,
    pad_to: int = MAX_DIM,
) -> NDArray[np.float64]:
    """Build a normalized vector from *summary* using *ranges*.

    Missing keys default to 0.5 (neutral). The result is padded with 0.5
    (neutral) to *pad_to* dimensions so all vectors in a mixed-pillar
    index share the same length.

    Parameters
    ----------
    summary : dict
        The run's ``summary`` dict from the registry.
    ranges : list of (key, min, max)
        Per-dimension normalization spec.
    pad_to : int
        Final vector length. Trailing dimensions are filled with 0.5
        (neutral) rather than 0.0, so they do not bias cosine distance
        toward or away from any axis.
    """
    # Pad with 0.5 (neutral) so copies vectors don't cluster artificially in the extra dimensions
    raw = np.full(pad_to, 0.5, dtype=np.float64)
    for i, (key, lo, hi) in enumerate(ranges):
        val = summary.get(key)
        if val is not None:
            try:
                raw[i] = _normalize(float(val), lo, hi)
            except (TypeError, ValueError):
                # Non-numeric value -> leave at 0.5 (neutral)
                pass
    return raw


# ---------------------------------------------------------------------------
# Public extractors — one per pillar
# ---------------------------------------------------------------------------


def extract_finance_state(run_summary: Dict[str, Any]) -> StateVector:
    """Map a finance run's summary to a normalized :class:`StateVector`.

    Expected keys: ``hit_rate``, ``crps``, ``coverage``, ``trust_score``,
    ``calibration_grade_numeric``. Missing keys default to 0.5.

    Parameters
    ----------
    run_summary : dict
        Must contain at least ``"run_id"`` (used as ``source_id``).
        All other keys are extracted from the summary's metric fields.
    """
    vec = _extract(run_summary, _FINANCE_RANGES)
    return StateVector(
        vector=vec,
        source_id=run_summary.get("run_id", ""),
        source_kind="finance",
        label=run_summary.get("label", f"finance-{run_summary.get('run_id', '?')}"),
        metadata={k: run_summary.get(k) for k, _, _ in _FINANCE_RANGES},
    )


def extract_copies_state(run_summary: Dict[str, Any]) -> StateVector:
    """Map a copies run's summary to a normalized :class:`StateVector`.

    Expected keys: ``fidelity_score``, ``privacy_score``, ``utility_gap``.
    Missing keys default to 0.5. The vector is padded with 0.5 (neutral)
    to :data:`MAX_DIM` dimensions.

    Parameters
    ----------
    run_summary : dict
        Must contain at least ``"run_id"``.
    """
    vec = _extract(run_summary, _COPIES_RANGES)
    return StateVector(
        vector=vec,
        source_id=run_summary.get("run_id", ""),
        source_kind="copies",
        label=run_summary.get("label", f"copies-{run_summary.get('run_id', '?')}"),
        metadata={k: run_summary.get(k) for k, _, _ in _COPIES_RANGES},
    )


def extract_worlds_state(run_summary: Dict[str, Any]) -> StateVector:
    """Map a worlds run's summary to a normalized :class:`StateVector`.

    Expected keys: ``alive``, ``dead``, ``mean_energy``, ``food_count``,
    ``population_density``. Missing keys default to 0.5.

    Parameters
    ----------
    run_summary : dict
        Must contain at least ``"run_id"``.
    """
    vec = _extract(run_summary, _WORLDS_RANGES)
    return StateVector(
        vector=vec,
        source_id=run_summary.get("run_id", ""),
        source_kind="worlds",
        label=run_summary.get("label", f"worlds-{run_summary.get('run_id', '?')}"),
        metadata={k: run_summary.get(k) for k, _, _ in _WORLDS_RANGES},
    )


# ---------------------------------------------------------------------------
# StateIndex — brute-force nearest-neighbor index
# ---------------------------------------------------------------------------


class StateIndex:
    """In-memory nearest-neighbor index over :class:`StateVector` objects.

    Backed by a plain Python list and a lazily-built numpy matrix. The
    matrix is invalidated on every mutation (``add`` / ``add_batch``);
    queries rebuild it on demand. This lazy-rebuild strategy is optimal
    for the registry workload (batch-insert then query, not interleaved
    writes and reads).

    Distance metric
    ---------------
    Queries use **cosine distance** (1 - cosine_similarity). Cosine is
    chosen over Euclidean because pillar vectors may have different
    numbers of "active" dimensions (finance=5, copies=3 padded to 5).
    Cosine is direction-sensitive and length-invariant, which means the
    neutral-padded dimensions (0.5) contribute proportionally less to
    the distance than the pillar's own metrics.

    Capacity
    --------
    Practical limit: ~50k vectors before query latency exceeds ~100ms.
    Beyond that, swap ``_build_matrix`` + ``query_nearest`` for a
    ball-tree or faiss IVF index.
    """

    def __init__(self) -> None:
        # The canonical store: a Python list of StateVectors. Order is
        # insertion order. Never reordered.
        self._vectors: List[StateVector] = []

        # Lazily-computed (n, d) numpy matrix for vectorized queries.
        # Set to None whenever the list is mutated; rebuilt on first
        # query after mutation.
        self._matrix: Optional[NDArray[np.float64]] = None

    # -- mutation -----------------------------------------------------------

    def add(self, vector: StateVector) -> None:
        """Append a single :class:`StateVector` to the index.

        Invalidates the cached numpy matrix so the next query rebuilds
        it. O(1) amortized (list append).
        """
        self._vectors.append(vector)
        self._matrix = None  # invalidate cache

    def add_batch(self, vectors: List[StateVector]) -> None:
        """Append multiple :class:`StateVector` objects at once.

        More efficient than calling :meth:`add` in a loop when the
        matrix cache is hot, because we invalidate only once.
        """
        self._vectors.extend(vectors)
        if vectors:
            self._matrix = None  # invalidate cache

    # -- queries ------------------------------------------------------------

    def query_nearest(
        self,
        vector: NDArray[np.float64],
        k: int = 5,
    ) -> List[Tuple[StateVector, float]]:
        """Return the *k* nearest :class:`StateVector` objects by cosine distance.

        Parameters
        ----------
        vector : np.ndarray
            Query vector. Must have the same dimensionality as the indexed
            vectors (:data:`MAX_DIM`).
        k : int
            Number of neighbors to return. Clamped to ``self.size()``.

        Returns
        -------
        list of (StateVector, float)
            Pairs of (neighbor, distance) sorted ascending by distance.
            Distance is ``1 - cosine_similarity`` and lives in [0, 2].
        """
        if not self._vectors:
            return []
        mat = self._get_matrix()
        # Cosine distance = 1 - (q . v) / (||q|| * ||v||)
        distances = self._cosine_distances(vector, mat)
        k = min(k, len(self._vectors))
        # argpartition is O(n) for k << n; we sort only the top-k slice
        if k < len(distances):
            top_k_idx = np.argpartition(distances, k)[:k]
        else:
            top_k_idx = np.arange(len(distances))
        # Sort the top-k by distance
        sorted_within = top_k_idx[np.argsort(distances[top_k_idx])]
        return [(self._vectors[i], float(distances[i])) for i in sorted_within]

    def query_radius(
        self,
        vector: NDArray[np.float64],
        radius: float,
    ) -> List[Tuple[StateVector, float]]:
        """Return all :class:`StateVector` objects within *radius* cosine distance.

        Parameters
        ----------
        vector : np.ndarray
            Query vector (:data:`MAX_DIM` dimensions).
        radius : float
            Maximum cosine distance (inclusive).

        Returns
        -------
        list of (StateVector, float)
            Pairs sorted ascending by distance.
        """
        if not self._vectors:
            return []
        mat = self._get_matrix()
        distances = self._cosine_distances(vector, mat)
        mask = distances <= radius
        indices = np.where(mask)[0]
        order = indices[np.argsort(distances[indices])]
        return [(self._vectors[i], float(distances[i])) for i in order]

    # -- accessors ----------------------------------------------------------

    def all_vectors(self) -> List[StateVector]:
        """Return all indexed :class:`StateVector` objects in insertion order."""
        return list(self._vectors)

    def size(self) -> int:
        """Return the number of vectors in the index."""
        return len(self._vectors)

    # -- internal -----------------------------------------------------------

    def _get_matrix(self) -> NDArray[np.float64]:
        """Lazily build or return the cached (n, d) numpy matrix.

        Each row is the ``.vector`` attribute of the corresponding
        :class:`StateVector`. Row order matches ``self._vectors``.
        """
        if self._matrix is None:
            self._matrix = np.array(
                [sv.vector for sv in self._vectors], dtype=np.float64
            )
        return self._matrix

    @staticmethod
    def _cosine_distances(
        query: NDArray[np.float64],
        matrix: NDArray[np.float64],
    ) -> NDArray[np.float64]:
        """Compute cosine distance between *query* and every row of *matrix*.

        Returns a 1-D array of shape (n,) with values in [0, 2].
        Zero-norm vectors produce distance 1.0 (orthogonal assumption).
        """
        query = np.asarray(query, dtype=np.float64).ravel()
        q_norm = np.linalg.norm(query)
        # Row norms of the matrix — shape (n,)
        row_norms = np.linalg.norm(matrix, axis=1)
        # Dot products — shape (n,)
        dots = matrix @ query
        # Guard against zero-norm vectors: replace 0 norms with 1 so the
        # division yields 0 (which maps to distance 1.0 after subtraction).
        safe_q = q_norm if q_norm > 0 else 1.0
        safe_rows = np.where(row_norms > 0, row_norms, 1.0)
        similarities = dots / (safe_rows * safe_q)
        # Clamp to [-1, 1] to guard against floating-point overshoot
        similarities = np.clip(similarities, -1.0, 1.0)
        return 1.0 - similarities


# ---------------------------------------------------------------------------
# Index builder — bridges registry -> StateIndex
# ---------------------------------------------------------------------------


# Pillar tag -> extractor mapping. Used by ``build_index_from_registry`` to
# dispatch each run to the correct extractor. Tags must match the values
# produced by ``_DEFAULT_PILLAR_FOR_KIND`` in ``contracts.py``.
_PILLAR_EXTRACTORS = {
    "finance": extract_finance_state,
    "synthetic": extract_copies_state,  # copies runs live under "synthetic" pillar
    "worlds": extract_worlds_state,
}


def build_index_from_registry(registry: Any) -> StateIndex:
    """Load all runs from *registry* and build a :class:`StateIndex`.

    Iterates over runs from each supported pillar, extracts state vectors,
    and inserts them into a fresh index. Runs with unsupported pillar tags
    are silently skipped — the index only contains runs for which we have
    an extractor.

    Parameters
    ----------
    registry : RunRegistry
        An open :class:`~the_similarity.platform.registry.RunRegistry`.
        The caller is responsible for opening and closing the registry.

    Returns
    -------
    StateIndex
        A populated index ready for queries.
    """
    index = StateIndex()
    for pillar, extractor in _PILLAR_EXTRACTORS.items():
        runs = registry.list_runs(pillar=pillar, limit=10_000)
        for run in runs:
            # Merge run_id into the summary dict so the extractor can
            # pull it out for StateVector.source_id. We do NOT mutate the
            # original RunRecord — we build a new dict.
            summary_with_id = {**run.summary, "run_id": run.run_id}
            sv = extractor(summary_with_id)
            index.add(sv)
    return index


# ---------------------------------------------------------------------------
# Dimensionality reduction for visualization
# ---------------------------------------------------------------------------


def reduce_to_3d(
    index: StateIndex,
    method: str = "pca",
) -> NDArray[np.float64]:
    """Project all indexed vectors to 3 dimensions for visualization.

    Parameters
    ----------
    index : StateIndex
        Must contain at least 1 vector.
    method : str
        ``"pca"`` (default) — sklearn PCA. Deterministic, fast.
        ``"tsne"`` — sklearn t-SNE. Non-deterministic, better for
        separating clusters but slower.

    Returns
    -------
    np.ndarray
        Shape ``(n, 3)`` float64 array. Row order matches
        ``index.all_vectors()``.

    Raises
    ------
    ValueError
        If the index is empty or *method* is unknown.
    """
    return _reduce(index, n_components=3, method=method)


def reduce_to_2d(
    index: StateIndex,
    method: str = "pca",
) -> NDArray[np.float64]:
    """Project all indexed vectors to 2 dimensions for visualization.

    Same interface as :func:`reduce_to_3d` but returns ``(n, 2)``.
    """
    return _reduce(index, n_components=2, method=method)


def _reduce(
    index: StateIndex,
    n_components: int,
    method: str,
) -> NDArray[np.float64]:
    """Internal reduction dispatch.

    Separated from the public API so both ``reduce_to_2d`` and
    ``reduce_to_3d`` share validation and method dispatch.
    """
    if index.size() == 0:
        raise ValueError("Cannot reduce an empty StateIndex.")

    mat = index._get_matrix()  # (n, d) — reuse the cached matrix

    # When the number of samples <= n_components, PCA/TSNE can fail or
    # produce degenerate output. We pad with zeros if needed, but more
    # importantly we clamp n_components to min(n, d, n_components).
    n_samples, n_features = mat.shape
    effective_components = min(n_components, n_samples, n_features)

    if method == "pca":
        from sklearn.decomposition import PCA

        reducer = PCA(n_components=effective_components, random_state=42)
        result = reducer.fit_transform(mat)
    elif method == "tsne":
        from sklearn.manifold import TSNE

        # t-SNE perplexity must be < n_samples. Default sklearn perplexity
        # is 30; we clamp it to (n_samples - 1) when the index is small.
        perplexity = min(30.0, max(1.0, n_samples - 1.0))
        reducer = TSNE(
            n_components=effective_components,
            perplexity=perplexity,
            random_state=42,
        )
        result = reducer.fit_transform(mat)
    else:
        raise ValueError(f"Unknown reduction method {method!r}. Use 'pca' or 'tsne'.")

    # If effective_components < n_components, pad with zeros so the caller
    # always gets the promised shape.
    if effective_components < n_components:
        padding = np.zeros(
            (n_samples, n_components - effective_components), dtype=np.float64
        )
        result = np.hstack([result, padding])

    return result
