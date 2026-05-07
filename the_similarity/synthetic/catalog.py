"""Synthetic dataset catalog — register, list, and inspect synthetic datasets.

This module bridges the synthetic pipeline's on-disk artifacts (real.parquet,
synth.parquet, scorecard.json) with the platform's :class:`DatasetSpec`
registry. It reads a completed run directory, computes file-level metadata
(row count, column count, SHA-256 checksum), and registers the result as a
:class:`~the_similarity.platform.contracts.DatasetSpec` with
``source="synthetic:<run_id>"``.

Three public functions
---------------------
- :func:`register_synthetic_dataset` — reads a run dir, builds a
  :class:`DatasetSpec`, registers it in the platform registry.
- :func:`list_catalog` — lists synthetic datasets from the registry,
  optionally filtering to promoted-only entries.
- :func:`get_dataset_card` — returns a rich "dataset card" dict that
  combines the registry row with scorecard highlights and file paths.

Integration points
------------------
- **CLI** — ``python -m the_similarity.synthetic.cli catalog register|list|show``
  delegates to these functions.
- **API** — ``GET /platform/datasets/{id}/card`` calls :func:`get_dataset_card`.
- **Agent 2 (promotion)** — promotion logic registers promoted copies as
  DatasetSpec with ``source="synthetic:<run_id>"``. This module provides
  the same registration path for non-promoted datasets.

Design constraints
------------------
- pandas is imported lazily (inside function bodies) to keep module load
  cheap for CLI ``--help`` and import-time type checking.
- SHA-256 is computed over the full file contents. For multi-GB files this
  is expensive; callers can skip by passing ``compute_checksum=False``.
- The ``synth.parquet`` file is the primary registration target. ``real.parquet``
  is referenced in metadata but not registered as a separate dataset — it
  represents the source, not a synthetic output.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from the_similarity.platform.contracts import DatasetSpec
from the_similarity.platform.registry import RunRegistry


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _sha256_file(path: Path) -> str:
    """Compute SHA-256 hex digest of a file. Reads in 64 KiB chunks to
    bound memory usage on large parquet files.

    Returns
    -------
    str
        Lowercase hex digest (64 characters).
    """
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(65536)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _read_parquet_shape(path: Path) -> tuple[int, int]:
    """Return (n_rows, n_columns) from a parquet file without loading
    all data into memory. Uses pyarrow metadata when available, falls
    back to pandas.

    Raises
    ------
    FileNotFoundError
        If the parquet file does not exist.
    """
    try:
        import pyarrow.parquet as pq

        meta = pq.read_metadata(path)
        # pyarrow metadata: num_rows at file level, num_columns from schema
        schema = pq.read_schema(path)
        return meta.num_rows, len(schema)
    except ImportError:
        # Fallback: read just enough to get shape via pandas
        import pandas as pd

        df = pd.read_parquet(path)
        return df.shape


def _load_scorecard(run_dir: Path) -> Optional[Dict[str, Any]]:
    """Load ``scorecard.json`` from a run directory if it exists.

    Returns None when the file is absent (e.g. a run that skipped scoring).
    """
    scorecard_path = run_dir / "scorecard.json"
    if not scorecard_path.exists():
        return None
    return json.loads(scorecard_path.read_text())


def _scorecard_summary(scorecard: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Extract headline metrics from a full scorecard dict.

    Returns a compact summary suitable for embedding in a dataset card.
    Gracefully handles None and partial scorecards.
    """
    if scorecard is None:
        return {}

    summary: Dict[str, Any] = {}

    # Overall pass/fail
    if "passed" in scorecard:
        summary["passed"] = scorecard["passed"]

    # Fidelity headline
    fidelity = scorecard.get("fidelity")
    if fidelity and isinstance(fidelity, dict):
        summary["fidelity_score"] = fidelity.get("overall_score")
        summary["fidelity_passed"] = fidelity.get("passed")

    # Privacy headline
    privacy = scorecard.get("privacy")
    if privacy and isinstance(privacy, dict):
        summary["privacy_score"] = privacy.get("overall_score")
        summary["privacy_passed"] = privacy.get("passed")

    # Utility headline
    utility = scorecard.get("utility")
    if utility and isinstance(utility, dict):
        summary["utility_transfer_gap"] = utility.get("transfer_gap")
        summary["utility_passed"] = utility.get("passed")

    return summary


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def register_synthetic_dataset(
    run_id: str,
    name: str,
    version: str,
    run_dir: Path,
    registry: RunRegistry,
    *,
    compute_checksum: bool = True,
) -> str:
    """Register a synthetic dataset from a completed copies run directory.

    Reads ``synth.parquet`` from ``run_dir`` to compute file statistics
    (n_rows, n_columns, checksum), loads ``scorecard.json`` for metadata,
    and creates a :class:`DatasetSpec` with ``source="synthetic:<run_id>"``.

    Parameters
    ----------
    run_id:
        The synthetic run's identifier. Embedded in the ``source`` field
        as ``"synthetic:<run_id>"`` for traceability.
    name:
        Human-readable dataset name (e.g. ``"SPY synthetic copy"``).
    version:
        Version string (e.g. ``"v1.0"``).
    run_dir:
        Path to the completed run directory containing ``synth.parquet``
        and optionally ``scorecard.json``.
    registry:
        Platform registry instance to register the dataset in.
    compute_checksum:
        If True (default), compute SHA-256 of ``synth.parquet``. Set to
        False for large files where hashing is too expensive.

    Returns
    -------
    str
        The ``dataset_id`` of the registered dataset.

    Raises
    ------
    FileNotFoundError
        If ``synth.parquet`` does not exist in ``run_dir``.
    """
    synth_path = Path(run_dir) / "synth.parquet"
    if not synth_path.exists():
        raise FileNotFoundError(f"synth.parquet not found in run directory: {run_dir}")

    # Compute file statistics from the parquet file
    n_rows, n_columns = _read_parquet_shape(synth_path)

    checksum: Optional[str] = None
    if compute_checksum:
        checksum = _sha256_file(synth_path)

    # Load scorecard for metadata embedding
    scorecard = _load_scorecard(Path(run_dir))
    sc_summary = _scorecard_summary(scorecard)

    # Build metadata dict with run provenance + scorecard highlights
    metadata: Dict[str, Any] = {
        "run_id": run_id,
        "run_dir": str(run_dir),
        "scorecard_summary": sc_summary,
    }

    # Check for real.parquet to record source file path
    real_path = Path(run_dir) / "real.parquet"
    if real_path.exists():
        metadata["real_parquet"] = str(real_path)

    # Generate a dataset_id that encodes synthetic provenance
    dataset_id = f"synthetic-{run_id}"

    spec = DatasetSpec(
        dataset_id=dataset_id,
        name=name,
        version=version,
        source=f"synthetic:{run_id}",
        n_rows=n_rows,
        n_columns=n_columns,
        checksum=checksum,
        metadata=metadata,
    )

    registry.register_dataset(spec)
    return dataset_id


def list_catalog(
    registry: RunRegistry,
    *,
    promoted_only: bool = False,
) -> List[DatasetSpec]:
    """List synthetic datasets from the registry.

    Parameters
    ----------
    registry:
        Platform registry instance to query.
    promoted_only:
        If True, filter to datasets whose metadata contains
        ``"promoted": True``. Promotion is set by Agent 2's promotion
        logic when a synthetic copy passes quality gates.

    Returns
    -------
    list[DatasetSpec]
        Matching datasets sorted by name (registry default ordering).
    """
    all_datasets = registry.list_datasets()

    # Filter to synthetic datasets by checking the source prefix
    synthetic = [ds for ds in all_datasets if ds.source.startswith("synthetic:")]

    if promoted_only:
        synthetic = [
            ds for ds in synthetic if ds.metadata.get("promoted", False) is True
        ]

    return synthetic


def get_dataset_card(
    dataset_id: str,
    registry: RunRegistry,
) -> Dict[str, Any]:
    """Build a rich "dataset card" for a registered synthetic dataset.

    The card combines the registry row (DatasetSpec fields) with scorecard
    highlights extracted from the metadata. This is richer than the raw
    DatasetSpec — it surfaces generation method, privacy status, and
    quality metrics in a single flat-ish dict suitable for UI rendering.

    Parameters
    ----------
    dataset_id:
        The ``dataset_id`` to look up.
    registry:
        Platform registry instance.

    Returns
    -------
    dict
        Dataset card with keys: ``dataset_id``, ``name``, ``version``,
        ``source``, ``n_rows``, ``n_columns``, ``checksum``,
        ``source_run_id``, ``generation_method``, ``scorecard_summary``,
        ``privacy_status``, ``file_paths``.

    Raises
    ------
    KeyError
        If ``dataset_id`` is not found in the registry.
    """
    # Find the dataset in the registry
    all_datasets = registry.list_datasets()
    spec: Optional[DatasetSpec] = None
    for ds in all_datasets:
        if ds.dataset_id == dataset_id:
            spec = ds
            break

    if spec is None:
        raise KeyError(f"dataset_id not found: {dataset_id}")

    # Extract run_id from source field (format: "synthetic:<run_id>")
    source_run_id: Optional[str] = None
    generation_method = "unknown"
    if spec.source.startswith("synthetic:"):
        source_run_id = spec.source[len("synthetic:") :]

    # Extract scorecard summary from metadata
    metadata = spec.metadata or {}
    sc_summary = metadata.get("scorecard_summary", {})

    # Determine privacy status from scorecard
    privacy_status = "unknown"
    if "privacy_passed" in sc_summary:
        privacy_status = "passed" if sc_summary["privacy_passed"] else "failed"

    # Build file paths from metadata
    file_paths: Dict[str, str] = {}
    run_dir = metadata.get("run_dir")
    if run_dir:
        file_paths["synth_parquet"] = str(Path(run_dir) / "synth.parquet")
        file_paths["scorecard"] = str(Path(run_dir) / "scorecard.json")
        if metadata.get("real_parquet"):
            file_paths["real_parquet"] = metadata["real_parquet"]

    return {
        "dataset_id": spec.dataset_id,
        "name": spec.name,
        "version": spec.version,
        "source": spec.source,
        "n_rows": spec.n_rows,
        "n_columns": spec.n_columns,
        "checksum": spec.checksum,
        "source_run_id": source_run_id,
        "generation_method": generation_method,
        "scorecard_summary": sc_summary,
        "privacy_status": privacy_status,
        "file_paths": file_paths,
        "promoted": metadata.get("promoted", False),
    }


__all__ = [
    "get_dataset_card",
    "list_catalog",
    "register_synthetic_dataset",
]
