"""Promotion logic — mark a synthetic run as the promoted dataset for a name.

Promotion is the act of tagging a specific synthetic run as the "current
best" for a dataset name. This creates a :class:`DatasetSpec` in the
platform registry with ``source="synthetic:<run_id>"`` and metadata
``{"promoted": true, "promoted_at": <iso_now>}``.

Semantics
---------
- Only one dataset spec can be promoted per ``dataset_name`` at a time.
  Re-promoting overwrites the previous spec (upsert on ``dataset_id``).
- The ``dataset_id`` is derived deterministically from ``dataset_name``
  as ``"promoted:<dataset_name>"`` so lookups are O(1) by convention.
- Promotion does NOT copy data — it creates a pointer. The actual
  synthetic dataset lives in the run directory referenced by ``run_id``.

Thread safety
-------------
Each function takes an explicit :class:`RunRegistry` instance. The
registry's WAL mode handles cross-process writes safely, but callers
must not share a single registry instance across threads (one connection
per thread is the documented contract).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from the_similarity.platform.contracts import DatasetSpec
from the_similarity.synthetic.contracts import iso_now

# Type-only import kept at the top (ruff E402). RunRegistry is only
# needed inside type annotations resolved lazily via PEP 563 / future
# ``annotations``, so there is no circular-import risk at load time.
if TYPE_CHECKING:
    from the_similarity.platform.registry import RunRegistry  # noqa: F401


def _promoted_dataset_id(dataset_name: str) -> str:
    """Deterministic dataset_id for a promoted dataset name.

    Convention: ``"promoted:<dataset_name>"`` so lookups are trivial
    and there is no ambiguity with non-promoted dataset specs.
    """
    return f"promoted:{dataset_name}"


def promote_run(
    run_id: str,
    dataset_name: str,
    registry: "RunRegistry",
) -> str:
    """Mark a synthetic run as the promoted dataset for ``dataset_name``.

    Creates (or upserts) a :class:`DatasetSpec` in the registry with:
    - ``dataset_id = "promoted:<dataset_name>"``
    - ``source = "synthetic:<run_id>"``
    - ``metadata = {"promoted": True, "promoted_at": <iso_now>}``

    Parameters
    ----------
    run_id:
        The run to promote. Must already exist in the registry (not
        validated here — the registry will happily store the pointer
        even if the run is missing, but downstream consumers should
        check).
    dataset_name:
        Human-readable name for the promoted dataset (e.g.
        ``"spy-synthetic"``). Used as the lookup key.
    registry:
        A :class:`~the_similarity.platform.registry.RunRegistry` instance.

    Returns
    -------
    str:
        The ``dataset_id`` of the created/updated :class:`DatasetSpec`.
    """
    spec = DatasetSpec(
        dataset_id=_promoted_dataset_id(dataset_name),
        name=dataset_name,
        version="promoted",
        source=f"synthetic:{run_id}",
        metadata={
            "promoted": True,
            "promoted_at": iso_now(),
        },
    )
    return registry.register_dataset(spec)


def get_promoted(
    dataset_name: str,
    registry: "RunRegistry",
) -> Optional[DatasetSpec]:
    """Return the currently promoted dataset for ``dataset_name``, or None.

    Looks up the deterministic ``dataset_id`` convention. If no promoted
    dataset exists for this name, returns ``None``.

    Parameters
    ----------
    dataset_name:
        The dataset name to look up.
    registry:
        A :class:`~the_similarity.platform.registry.RunRegistry` instance.

    Returns
    -------
    Optional[DatasetSpec]:
        The promoted :class:`DatasetSpec` if one exists, else ``None``.
    """
    target_id = _promoted_dataset_id(dataset_name)
    # List all datasets and filter — the registry does not expose a
    # get_dataset_by_id method, so we scan. The dataset table is small
    # (tens of rows at most) so this is fine.
    for spec in registry.list_datasets():
        if spec.dataset_id == target_id:
            return spec
    return None


def list_promoted(
    registry: "RunRegistry",
) -> list[DatasetSpec]:
    """Return all currently promoted datasets.

    Filters the full dataset list by the ``promoted:`` prefix convention.
    Returned in the same order as ``registry.list_datasets()`` (name ASC).

    Parameters
    ----------
    registry:
        A :class:`~the_similarity.platform.registry.RunRegistry` instance.

    Returns
    -------
    list[DatasetSpec]:
        All promoted :class:`DatasetSpec` rows. Empty list if none exist.
    """
    return [
        spec
        for spec in registry.list_datasets()
        if spec.dataset_id.startswith("promoted:")
    ]


__all__ = [
    "get_promoted",
    "list_promoted",
    "promote_run",
]
