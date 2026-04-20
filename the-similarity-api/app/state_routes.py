"""State-space query routes — mounts at ``/platform/state/*``.

Purpose
-------
Expose the platform's state-space index and relational graph through the
customer-facing API. These endpoints power the 3D state-space visualization
in the frontend — each run is a point in feature space, and the graph
captures cluster membership and transition structure.

Endpoints (all prefixed ``/platform/state`` by the router's prefix)
--------------------------------------------------------------------
- ``GET /platform/state/projection``                    — 3D coordinates for all runs.
- ``GET /platform/state/nearest/{run_id}?k=5``          — nearest neighbors in feature space.
- ``GET /platform/state/clusters``                      — cluster assignments.
- ``GET /platform/state/transitions?kind=finance``      — transition graph edges.
- ``GET /platform/state/cross-domain/{run_id}?target_kind=worlds&k=3`` — cross-domain correspondences.

Design invariants
-----------------
1. **Lazy build** — the state service is built on first request, not at
   startup. This keeps cold-start time low and allows the registry to
   populate before we read from it.
2. **Graceful degradation** — if Agent 1's StateIndex or Agent 2's
   StateGraph are not yet available, endpoints return empty results
   (not errors). The service layer handles all try/except logic.
3. **Per-request registry** — mirrors ``platform_routes.py``'s dependency
   injection pattern. The registry is opened per request, passed to the
   service's ``build()`` method, and closed after the response.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query

from app.platform_routes import get_registry
from the_similarity.core.state_service import StateService
from the_similarity.platform.registry import RunRegistry

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Router — ``/platform/state`` prefix. Mounted alongside the existing
# platform router in ``app/main.py``.
# ---------------------------------------------------------------------------

router = APIRouter(prefix="/platform/state", tags=["state-space"])


# ---------------------------------------------------------------------------
# Service singleton — built lazily on first request. Re-built on each
# request to pick up newly registered runs. At current scale (hundreds
# of runs) this is cheap; if it becomes expensive, add a TTL cache.
# ---------------------------------------------------------------------------

_service = StateService()


def _get_built_service(
    registry: RunRegistry = Depends(get_registry),
) -> StateService:
    """FastAPI dependency that returns a built StateService.

    Rebuilds the index from the registry on every call. This is the
    simplest correctness model — always fresh data. The build cost is
    O(N) where N is the run count, which is negligible at current scale.
    """
    _service.build(registry)
    return _service


# ---------------------------------------------------------------------------
# GET /platform/state/projection
# ---------------------------------------------------------------------------


@router.get("/projection", response_model=List[Dict[str, Any]])
def get_projection(
    service: StateService = Depends(_get_built_service),
) -> List[Dict[str, Any]]:
    """Return 3D coordinates for all indexed runs.

    Each entry is a dict with ``run_id``, ``kind``, ``x``, ``y``, ``z``,
    ``label``. The coordinates come from dimensionality reduction (UMAP/PCA)
    when Agent 1's StateIndex is available, or from a deterministic
    kind-based layout as a fallback.
    """
    return service.projection_3d()


# ---------------------------------------------------------------------------
# GET /platform/state/nearest/{run_id}
# ---------------------------------------------------------------------------


@router.get("/nearest/{run_id}", response_model=List[Dict[str, Any]])
def get_nearest(
    run_id: str,
    k: int = Query(5, ge=1, le=50, description="Number of neighbors to return."),
    service: StateService = Depends(_get_built_service),
) -> List[Dict[str, Any]]:
    """Find the k nearest runs to ``run_id`` in feature space.

    Returns a list of dicts with ``run_id``, ``kind``, ``label``,
    ``distance``. Empty list if the run_id is unknown or the index
    is not available.
    """
    return service.nearest(run_id, k=k)


# ---------------------------------------------------------------------------
# GET /platform/state/clusters
# ---------------------------------------------------------------------------


@router.get("/clusters", response_model=List[List[Dict[str, Any]]])
def get_clusters(
    service: StateService = Depends(_get_built_service),
) -> List[List[Dict[str, Any]]]:
    """Return cluster assignments for all indexed runs.

    Outer list = clusters. Each inner list = runs in that cluster, each
    as ``{run_id, kind, label}``. Empty outer list if no clusters are
    found or the graph module is not available.
    """
    return service.clusters()


# ---------------------------------------------------------------------------
# GET /platform/state/transitions
# ---------------------------------------------------------------------------


@router.get("/transitions", response_model=List[Dict[str, Any]])
def get_transitions(
    kind: Optional[str] = Query(
        None, description="Filter to edges involving runs of this kind."
    ),
    service: StateService = Depends(_get_built_service),
) -> List[Dict[str, Any]]:
    """Return transition edges from the state graph.

    Each dict has ``source``, ``target``, ``weight``. Optionally filtered
    to only edges involving runs of the given ``kind``.
    """
    return service.transitions(kind=kind)


# ---------------------------------------------------------------------------
# GET /platform/state/cross-domain/{run_id}
# ---------------------------------------------------------------------------


@router.get("/cross-domain/{run_id}", response_model=List[Dict[str, Any]])
def get_cross_domain(
    run_id: str,
    target_kind: str = Query(
        ..., description="The kind of run to search for (e.g. 'worlds')."
    ),
    k: int = Query(3, ge=1, le=50, description="Number of results to return."),
    service: StateService = Depends(_get_built_service),
) -> List[Dict[str, Any]]:
    """Find runs of a different kind that are closest to ``run_id``.

    Returns a list of dicts with ``run_id``, ``kind``, ``label``,
    ``distance``. Empty list if the run_id is unknown or no cross-domain
    neighbors are found.
    """
    return service.cross_domain(run_id, target_kind=target_kind, k=k)


__all__ = ["router"]
