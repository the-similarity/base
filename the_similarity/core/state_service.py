"""State-space service — wraps StateIndex + StateGraph for API consumption.

Purpose
-------
Provides a high-level facade over the spatial index (Agent 1's
``the_similarity.platform.state_space.StateIndex``) and the relational
graph (Agent 2's ``the_similarity.platform.state_graph.StateGraph``).
The service translates registry runs into feature vectors, builds the
index and graph structures, and exposes query methods that return plain
dicts suitable for JSON serialization by the API layer.

Fail-safe design
----------------
Both ``StateIndex`` and ``StateGraph`` are built by parallel agents and
may not be available at import time. Every import is wrapped in a
try/except so the service degrades gracefully — methods return empty
results rather than crashing when dependencies are missing.

Lifecycle
---------
1. Construct ``StateService()`` (no arguments — stateless until built).
2. Call ``build(registry)`` to populate the index + graph from all runs
   in the registry. This is an O(N) operation over the run count.
3. Query via ``nearest()``, ``clusters()``, ``transitions()``, etc.
4. Re-call ``build()`` to refresh after new runs land.

Thread safety
-------------
Not thread-safe. The service holds mutable state (the index and graph).
In the API layer, construct a fresh service per request or protect with
a lock. Given the current scale (hundreds of runs, not millions), the
build cost is negligible.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

# The RunRegistry is always available — it's the platform backbone. Kept at
# top-of-file (above the guarded imports below) so newer ruff versions no
# longer flag it with E402.
from the_similarity.platform.registry import RunRegistry

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Guarded imports — Agent 1 (StateIndex) and Agent 2 (StateGraph) ship in
# parallel branches. We stub them out if not yet available.
# ---------------------------------------------------------------------------

try:
    from the_similarity.core.state_space import StateIndex  # Agent 1 — canonical owner
except ImportError:
    StateIndex = None  # type: ignore[assignment,misc]

try:
    from the_similarity.core.state_graph import StateGraph  # Agent 2 — graph layer
except ImportError:
    StateGraph = None  # type: ignore[assignment,misc]


def _run_to_feature_dict(artifact: Any) -> Dict[str, Any]:
    """Extract a flat feature dict from a RunArtifact for indexing.

    The feature vector is built from the run's ``summary`` dict, which
    contains headline numbers (scores, row counts, etc.) that are
    meaningful for spatial comparison. Non-numeric values are skipped.

    Returns a dict with keys:
    - ``run_id``: str identifier
    - ``kind``: str run kind (copies, worlds, finance, etc.)
    - ``label``: human-readable label derived from config/kind
    - ``features``: dict of numeric feature name -> float value
    """
    summary = artifact.summary or {}
    # Extract only numeric features from the summary for spatial indexing.
    features: Dict[str, float] = {}
    for key, val in summary.items():
        if isinstance(val, (int, float)):
            features[key] = float(val)

    # Also pull seed as a feature if present (useful for grouping).
    if artifact.seed is not None:
        features["seed"] = float(artifact.seed)

    # Build a human-readable label from config or kind.
    config = artifact.config or {}
    label = config.get("generator_name", "") or config.get("scenario_name", "") or ""
    if not label:
        label = str(artifact.kind)

    return {
        "run_id": artifact.run_id,
        "kind": str(artifact.kind),
        "label": label,
        "features": features,
    }


class StateService:
    """High-level facade over StateIndex + StateGraph.

    Wraps the spatial index and relational graph into a single interface
    that the API routes can call. Methods return plain dicts (no domain
    objects) so the router layer can serialize them directly.

    Attributes
    ----------
    _index : StateIndex | None
        Spatial index for nearest-neighbor queries. None if Agent 1's
        module is not available or ``build()`` has not been called.
    _graph : StateGraph | None
        Relational graph for cluster/transition queries. None if Agent 2's
        module is not available or ``build()`` has not been called.
    _runs : list[dict]
        Cached list of feature dicts from the last ``build()`` call.
        Each entry has ``run_id``, ``kind``, ``label``, ``features``.
    """

    def __init__(self) -> None:
        self._index = None
        self._graph = None
        self._runs: List[Dict[str, Any]] = []
        # Map run_id -> index in _runs for fast lookup.
        self._id_to_idx: Dict[str, int] = {}

    def build(self, registry: RunRegistry) -> None:
        """Build the index and graph from all runs in the registry.

        Fetches all runs via ``registry.list()`` (default limit=100), extracts
        feature vectors, and builds the spatial index + relational graph.
        Replaces any previously built state.

        Parameters
        ----------
        registry : RunRegistry
            The platform run registry to read from.
        """
        # Fetch all runs — use a generous limit to capture everything.
        artifacts = registry.list(limit=10_000)

        self._runs = [_run_to_feature_dict(a) for a in artifacts]
        self._id_to_idx = {r["run_id"]: i for i, r in enumerate(self._runs)}

        # Build spatial index if the module is available.
        if StateIndex is not None:
            try:
                self._index = StateIndex()
                self._index.build(self._runs)
            except Exception:
                logger.warning(
                    "StateIndex.build() failed — nearest/projection queries "
                    "will return empty results.",
                    exc_info=True,
                )
                self._index = None

        # Build relational graph if the module is available.
        if StateGraph is not None:
            try:
                self._graph = StateGraph()
                self._graph.build(self._runs)
            except Exception:
                logger.warning(
                    "StateGraph.build() failed — cluster/transition queries "
                    "will return empty results.",
                    exc_info=True,
                )
                self._graph = None

    # ------------------------------------------------------------------
    # Query methods — all return list[dict] for JSON serialization.
    # ------------------------------------------------------------------

    def nearest(self, run_id: str, k: int = 5) -> List[Dict[str, Any]]:
        """Find the k nearest runs to ``run_id`` in feature space.

        Parameters
        ----------
        run_id : str
            The anchor run to find neighbors for.
        k : int
            Number of neighbors to return (default 5).

        Returns
        -------
        list[dict]
            Each dict has ``run_id``, ``kind``, ``label``, ``distance``.
            Empty list if the index is not available or run_id is unknown.
        """
        if self._index is None or run_id not in self._id_to_idx:
            return []
        try:
            return self._index.nearest(run_id, k=k)
        except Exception:
            logger.warning("StateIndex.nearest() failed", exc_info=True)
            return []

    def clusters(self) -> List[List[Dict[str, Any]]]:
        """Return cluster assignments for all indexed runs.

        Returns
        -------
        list[list[dict]]
            Outer list = clusters. Each inner list = runs in that cluster,
            each as ``{run_id, kind, label}``. Empty list if the graph is
            not available.
        """
        if self._graph is None:
            return []
        try:
            return self._graph.clusters()
        except Exception:
            logger.warning("StateGraph.clusters() failed", exc_info=True)
            return []

    def transitions(self, kind: Optional[str] = None) -> List[Dict[str, Any]]:
        """Return transition edges from the state graph.

        Parameters
        ----------
        kind : str | None
            If provided, filter edges to only those involving runs of this
            kind (e.g. ``"finance"``).

        Returns
        -------
        list[dict]
            Each dict has ``source``, ``target``, ``weight``.
            Empty list if the graph is not available.
        """
        if self._graph is None:
            return []
        try:
            return self._graph.transitions(kind=kind)
        except Exception:
            logger.warning("StateGraph.transitions() failed", exc_info=True)
            return []

    def cross_domain(
        self, source_id: str, target_kind: str, k: int = 3
    ) -> List[Dict[str, Any]]:
        """Find runs of a different kind that are closest to ``source_id``.

        Parameters
        ----------
        source_id : str
            The anchor run.
        target_kind : str
            The kind of run to search for (e.g. ``"worlds"``).
        k : int
            Number of cross-domain neighbors to return.

        Returns
        -------
        list[dict]
            Each dict has ``run_id``, ``kind``, ``label``, ``distance``.
            Empty list if the graph is not available or source_id unknown.
        """
        if self._graph is None:
            # Fallback: if we have the index, filter nearest by kind.
            if self._index is not None and source_id in self._id_to_idx:
                try:
                    # Over-fetch and filter by target_kind.
                    candidates = self._index.nearest(source_id, k=k * 10)
                    return [
                        c for c in candidates if c.get("kind") == target_kind
                    ][:k]
                except Exception:
                    pass
            return []
        try:
            return self._graph.cross_domain(source_id, target_kind=target_kind, k=k)
        except Exception:
            logger.warning("StateGraph.cross_domain() failed", exc_info=True)
            return []

    def projection_3d(self) -> List[Dict[str, Any]]:
        """Return 3D coordinates for all indexed runs.

        Uses StateIndex.reduce_to_3d() if available, otherwise falls back
        to a simple deterministic layout based on run order and kind.

        Returns
        -------
        list[dict]
            Each dict has ``run_id``, ``kind``, ``x``, ``y``, ``z``, ``label``.
            Empty list if no runs have been indexed.
        """
        if not self._runs:
            return []

        # Try the real dimensionality reduction from Agent 1.
        if self._index is not None:
            try:
                return self._index.reduce_to_3d()
            except Exception:
                logger.warning(
                    "StateIndex.reduce_to_3d() failed — falling back to "
                    "deterministic layout.",
                    exc_info=True,
                )

        # Fallback: deterministic 3D layout. Assign coordinates based on
        # run index and kind so the visualization is at least meaningful.
        # Group by kind on the Z axis, spread within each group on X/Y.
        kind_offsets: Dict[str, float] = {}
        kind_counters: Dict[str, int] = {}
        result: List[Dict[str, Any]] = []

        for i, run in enumerate(self._runs):
            kind = run["kind"]
            if kind not in kind_offsets:
                kind_offsets[kind] = float(len(kind_offsets))
                kind_counters[kind] = 0
            idx_in_kind = kind_counters[kind]
            kind_counters[kind] += 1

            # Spread runs of the same kind in a grid pattern on X/Y,
            # separated by kind on Z.
            cols = max(1, int(len(self._runs) ** 0.5))
            x = float(idx_in_kind % cols)
            y = float(idx_in_kind // cols)
            z = kind_offsets[kind]

            result.append({
                "run_id": run["run_id"],
                "kind": kind,
                "x": x,
                "y": y,
                "z": z,
                "label": run["label"],
            })

        return result
