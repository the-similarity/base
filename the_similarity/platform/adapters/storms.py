"""HURDAT2 storm-tracks backtest -> platform registry adapter.

Mirrors :mod:`the_similarity.platform.adapters.trajectories` (the
PR #301 synthetic-agents adapter) with one key difference: the
``RunKind`` is :attr:`RunKind.EVENTS` rather than ``WORLDS``. The
events pillar is the platform-spine slot for real-world phenomena
(weather, geopolitics, supply chain), which is exactly what HURDAT2
storms are. Reusing the existing enum value is purely additive — no
schema bump required.

Output
------
- ONE :class:`RunRecord` (kind=``EVENTS``, pillar=``events``,
  status=``SUCCEEDED``) representing the experiment.
- ONE :class:`DatasetSpec` for the storm trajectory corpus (the
  HURDAT2 Atlantic parquet) — registered when the caller passes a
  ``dataset_id``.
- ONE :class:`ScorecardSummary` with ``kind=ScorecardKind.BACKTEST``
  carrying the per-predictor metrics dict in
  ``details["per_predictor"]``. We collapse all predictors into a
  single scorecard row because the registry's scorecards table has
  primary key ``(run_id, kind)`` — see the trajectories adapter
  docstring for the full justification.

Lifecycle
---------
This adapter is a **post-experiment** writer. The backtest itself is
in ``the_similarity/tests/test_trajectory_3d_storms.py``; this module
wires the result numbers into the platform's persistent index without
re-running anything.
"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional

from the_similarity.platform.artifacts import (
    RunArtifact,
    RunKind,
    iso_now,
    new_run_id,
)
from the_similarity.platform.contracts import (
    DatasetSpec,
    ScorecardKind,
    ScorecardSummary,
)
from the_similarity.platform.registry import RunRegistry


def register_storm_backtest_run(
    *,
    predictor_metrics: Mapping[str, Mapping[str, float]],
    n_storms_train: int,
    n_storms_test: int,
    n_windows: int,
    window_len: int,
    forward_bars: int,
    z_scale: float,
    primary_predictor: str = "model",
    dataset_id: Optional[str] = None,
    dataset_name: Optional[str] = None,
    config: Optional[Mapping[str, Any]] = None,
    seed: Optional[int] = None,
    registry: Optional[RunRegistry] = None,
    db_path: Optional[str] = None,
    run_id: Optional[str] = None,
) -> str:
    """Register a HURDAT2 storm-tracks backtest run in the platform registry.

    Parameters
    ----------
    predictor_metrics:
        Dict-of-dicts: ``{predictor_name: {"spatial_mae_km": float,
        "hit_rate": float, "crps": float, "n_trials": int}}``.
    n_storms_train / n_storms_test:
        Cardinality of the chronological train / test split.
    n_windows:
        Number of windows in the corpus (after window_len + forward_bars
        filtering and stride).
    window_len / forward_bars:
        Backtest hyperparameters; recorded in config for reproducibility.
    z_scale:
        The z-axis (max_wind) scaling factor used for this run. Critical
        for the ablation grid — the same predictor config can produce
        radically different results at z=0.0 vs z=5.0.
    primary_predictor:
        Which predictor name to flag as "primary" in scorecard details.
        Default ``"model"``.
    dataset_id / dataset_name:
        Optional storm-corpus dataset registration. Both required if
        either is provided.
    config:
        Optional extra config dict (e.g. ``{"sigma": 1.5,
        "sigma_pos": 1.0}``). Caller keys take precedence over the
        adapter defaults.
    seed:
        RNG seed used for any stochastic predictors (random_analogue
        baseline). Threaded into provenance.
    registry / db_path:
        Same precedence as :func:`register_trajectory_backtest_run` —
        explicit registry wins; otherwise db_path; otherwise resolves
        via ``THE_SIMILARITY_REGISTRY_DB`` env var or default home dir.
    run_id:
        Optional explicit run id; defaults to a fresh UUID4 hex.

    Returns
    -------
    str
        The ``run_id`` written.
    """
    primary = predictor_metrics.get(primary_predictor, {})
    summary: Dict[str, Any] = {
        "experiment": "storm_tracks_backtest",
        "pillar": "events",
        "data_source": "noaa_hurdat2_atlantic",
        "n_storms_train": n_storms_train,
        "n_storms_test": n_storms_test,
        "n_windows": n_windows,
        "window_len": window_len,
        "forward_bars": forward_bars,
        "z_scale": z_scale,
        "n_predictors": len(predictor_metrics),
        "primary_predictor": primary_predictor,
        # Headline numbers from the primary predictor only.
        "spatial_mae_km": primary.get("spatial_mae_km"),
        "hit_rate": primary.get("hit_rate"),
        "crps": primary.get("crps"),
    }

    config_payload: Dict[str, Any] = {
        "experiment": "storm_tracks_backtest",
        "data_source": "noaa_hurdat2_atlantic",
        "n_storms_train": n_storms_train,
        "n_storms_test": n_storms_test,
        "window_len": window_len,
        "forward_bars": forward_bars,
        "z_scale": z_scale,
    }
    if config:
        for k, v in config.items():
            config_payload[k] = v

    provenance: Dict[str, Any] = {
        "generator_name": "the_similarity.storm_tracks_backtest",
        "generator_version": "0.1.0",
        "seed": seed,
        "created_at": iso_now(),
    }
    if dataset_id is not None:
        provenance["source_id"] = dataset_id

    resolved_run_id = run_id or new_run_id()

    artifact = RunArtifact(
        run_id=resolved_run_id,
        kind=RunKind.EVENTS,
        config=config_payload,
        seed=seed,
        # In-memory experiment — no on-disk artifact files.
        artifact_paths={},
        summary=summary,
        provenance=provenance,
        created_at=iso_now(),
    )

    # Build per-predictor scorecards. The registry has a (run_id, kind)
    # uniqueness constraint, so we collapse them into a single
    # BACKTEST row whose details["per_predictor"] dict carries the
    # full comparison.
    scorecards: List[ScorecardSummary] = []
    for name, m in predictor_metrics.items():
        details: Dict[str, Any] = {
            "predictor": name,
            "spatial_mae_km": m.get("spatial_mae_km"),
            "hit_rate": m.get("hit_rate"),
            "crps": m.get("crps"),
            "n_trials": m.get("n_trials"),
            "primary": name == primary_predictor,
        }
        hit_rate = m.get("hit_rate")
        scorecards.append(
            ScorecardSummary(
                run_id=resolved_run_id,
                kind=ScorecardKind.BACKTEST,
                overall_score=float(hit_rate) if hit_rate is not None else None,
                passed=None,
                thresholds={},
                details=details,
            )
        )

    dataset_spec: Optional[DatasetSpec] = None
    if dataset_id is not None:
        if not dataset_name:
            raise ValueError("dataset_name is required when dataset_id is provided")
        dataset_spec = DatasetSpec(
            dataset_id=dataset_id,
            name=dataset_name,
            version="0.1.0",
            # Source URL points back at the public NHC HURDAT2 page so
            # the dataset row is self-describing for cross-referencing.
            source="https://www.nhc.noaa.gov/data/hurdat/",
            n_rows=n_storms_train + n_storms_test,
            n_columns=3,
            metadata={
                "pillar": "events",
                "experiment": "storm_tracks_backtest",
                "basin": "atlantic",
                "n_storms_train": n_storms_train,
                "n_storms_test": n_storms_test,
                "axes": ["x_km", "y_km", "z_scaled_wind"],
                "z_scale": z_scale,
            },
        )

    if registry is not None:
        _register_all(registry, artifact, scorecards, dataset_spec)
        return resolved_run_id

    from pathlib import Path
    import os

    if db_path is not None:
        resolved_db = Path(db_path).expanduser()
    else:
        env_value = os.environ.get("THE_SIMILARITY_REGISTRY_DB")
        resolved_db = (
            Path(env_value).expanduser()
            if env_value
            else Path("~/.the_similarity/registry.db").expanduser()
        )

    with RunRegistry(resolved_db) as r:
        _register_all(r, artifact, scorecards, dataset_spec)
    return resolved_run_id


def _register_all(
    registry: RunRegistry,
    artifact: RunArtifact,
    scorecards: List[ScorecardSummary],
    dataset_spec: Optional[DatasetSpec],
) -> None:
    """Centralized multi-step write so caller-/self-managed paths share logic.

    Steps mirror :func:`the_similarity.platform.adapters.trajectories._register_all`:
        1. Register the run row.
        2. Collapse per-predictor scorecards into ONE BACKTEST row
           (registry uniqueness keys force this).
        3. Optionally register the dataset spec.

    Each step uses the registry's upsert semantics so retries are safe.
    """
    registry.register(artifact)

    if scorecards:
        per_pred = {sc.details["predictor"]: sc.details for sc in scorecards}
        primary_name = next(
            (name for name, d in per_pred.items() if d.get("primary")),
            None,
        )
        primary_details = per_pred.get(primary_name, {}) if primary_name else {}
        merged = ScorecardSummary(
            run_id=artifact.run_id,
            kind=ScorecardKind.BACKTEST,
            overall_score=primary_details.get("hit_rate"),
            passed=None,
            thresholds={},
            details={
                "primary_predictor": primary_name,
                # Headline (primary) numbers at the top so the grid
                # row reads naturally.
                "spatial_mae_km": primary_details.get("spatial_mae_km"),
                "hit_rate": primary_details.get("hit_rate"),
                "crps": primary_details.get("crps"),
                "n_trials": primary_details.get("n_trials"),
                "per_predictor": per_pred,
            },
        )
        registry.register_scorecard(merged)

    if dataset_spec is not None:
        registry.register_dataset(dataset_spec)


__all__ = ["register_storm_backtest_run"]
