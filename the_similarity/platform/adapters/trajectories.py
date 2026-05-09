"""3D trajectory backtest -> platform registry adapter.

Wraps the output of the 3D-trajectory MVP backtest into a
:class:`~the_similarity.platform.artifacts.RunArtifact` with
``kind=RunKind.WORLDS`` (since the underlying input is an
agent-trajectory corpus from the worlds pillar) and persists it
through a shared :class:`~the_similarity.platform.registry.RunRegistry`.

Why ``RunKind.WORLDS`` (and not a new kind)?
--------------------------------------------
The platform contract treats ``RunKind`` as a *source pillar* tag
rather than an *experiment family* tag. Trajectory-self-similarity
runs are evaluations OVER worlds-pillar data; they are not a new
pillar themselves. Adding a new ``RunKind`` requires a schema bump,
TS-side enum mirror, and migration. Reusing ``WORLDS`` and
distinguishing trajectory experiments via
``config["experiment"] = "trajectory_3d_backtest"`` is the
additive, non-breaking path.

Output
------
- ONE :class:`RunRecord` representing the experiment as a whole
  (``kind=WORLDS``, ``pillar="worlds"``, ``status=SUCCEEDED``).
- ONE :class:`DatasetSpec` for the trajectory corpus (the input
  source) — registered if the caller passes a
  ``dataset_id``.
- ONE :class:`ScorecardSummary` per predictor with
  ``kind=ScorecardKind.BACKTEST``. Each carries the (MAE,
  hit_rate, CRPS) triple for that predictor; the ``model`` row is
  flagged as the "primary" via ``details["primary"] = True``.

Lifecycle
---------
This adapter is a **post-experiment** writer. The backtest itself
is a pure Python pipeline (see ``the_similarity/tests/test_trajectory_3d.py``);
this module wires the resulting numbers into the platform's
persistent index without re-running anything.
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


# ---------------------------------------------------------------------------
# Public adapter
# ---------------------------------------------------------------------------


def register_trajectory_backtest_run(
    *,
    predictor_metrics: Mapping[str, Mapping[str, float]],
    n_agents: int,
    n_ticks: int,
    n_windows: int,
    window_len: int,
    forward_bars: int,
    primary_predictor: str = "model",
    dataset_id: Optional[str] = None,
    dataset_name: Optional[str] = None,
    config: Optional[Mapping[str, Any]] = None,
    seed: Optional[int] = None,
    registry: Optional[RunRegistry] = None,
    db_path: Optional[str] = None,
    run_id: Optional[str] = None,
) -> str:
    """Register a 3D trajectory backtest run in the platform registry.

    Parameters
    ----------
    predictor_metrics:
        Dict-of-dicts: ``{predictor_name: {"spatial_mae": float,
        "hit_rate": float, "crps": float, "n_trials": int}}``. One
        scorecard is registered per predictor.
    n_agents / n_ticks / n_windows / window_len / forward_bars:
        Corpus shape parameters — recorded in the run config so the
        experiment is reproducible.
    primary_predictor:
        Which predictor name to flag as "primary" in its scorecard
        details. Default ``"model"``.
    dataset_id:
        Optional stable ID for the underlying trajectory corpus. If
        provided, a :class:`DatasetSpec` is registered alongside the
        run. ``None`` means "skip dataset registration".
    dataset_name:
        Human-readable display name for the dataset. Required when
        ``dataset_id`` is provided.
    config:
        Optional extra config dict (e.g. ``{"sigma_pos": 2.0,
        "stride": 30}``). Merged into the run artifact's config
        column.
    seed:
        RNG seed used by the backtest, threaded into provenance.
    registry / db_path:
        Same precedence as :func:`register_backtest_run` — pass an
        open registry, a db path, or neither (resolves via env var
        / default home dir).
    run_id:
        Optional explicit run id; defaults to a fresh UUID4 hex.

    Returns
    -------
    str
        The ``run_id`` written. Persisted alongside the per-predictor
        scorecards so a single ``python -m the_similarity.platform
        show <run_id>`` reveals the full comparison.
    """
    # Build the headline summary. We pick a small subset of fields
    # that are useful for grid display without the full per-predictor
    # detail (which lives in the per-scorecard rows).
    primary = predictor_metrics.get(primary_predictor, {})
    summary: Dict[str, Any] = {
        "experiment": "trajectory_3d_backtest",
        "pillar": "worlds",
        "n_agents": n_agents,
        "n_ticks": n_ticks,
        "n_windows": n_windows,
        "window_len": window_len,
        "forward_bars": forward_bars,
        "n_predictors": len(predictor_metrics),
        "primary_predictor": primary_predictor,
        # Headline numbers from the primary predictor only — full
        # detail is in the scorecards.
        "spatial_mae": primary.get("spatial_mae"),
        "hit_rate": primary.get("hit_rate"),
        "crps": primary.get("crps"),
    }

    # Build config payload merging caller-supplied values + the
    # dimensions implicit in the corpus.
    config_payload: Dict[str, Any] = {
        "experiment": "trajectory_3d_backtest",
        "n_agents": n_agents,
        "n_ticks": n_ticks,
        "window_len": window_len,
        "forward_bars": forward_bars,
    }
    if config:
        for k, v in config.items():
            # Caller-provided keys take precedence so they can pin
            # additional hyperparameters (sigma_pos, stride, etc.).
            config_payload[k] = v

    provenance: Dict[str, Any] = {
        "generator_name": "the_similarity.trajectory_3d_backtest",
        "generator_version": "0.1.0",
        "seed": seed,
        "created_at": iso_now(),
    }
    if dataset_id is not None:
        provenance["source_id"] = dataset_id

    resolved_run_id = run_id or new_run_id()

    artifact = RunArtifact(
        run_id=resolved_run_id,
        kind=RunKind.WORLDS,
        config=config_payload,
        seed=seed,
        # In-memory experiment — no on-disk artifact files. The
        # scorecards carry the metrics and the registry's JSON
        # columns store everything else.
        artifact_paths={},
        summary=summary,
        provenance=provenance,
        created_at=iso_now(),
    )

    # Build per-predictor scorecards. Each predictor gets its own
    # row so the platform's ``compare`` API can grid them against
    # each other. We use ScorecardKind.BACKTEST for all of them
    # (same metric family).
    scorecards: List[ScorecardSummary] = []
    for name, m in predictor_metrics.items():
        details: Dict[str, Any] = {
            "predictor": name,
            "spatial_mae": m.get("spatial_mae"),
            "hit_rate": m.get("hit_rate"),
            "crps": m.get("crps"),
            "n_trials": m.get("n_trials"),
            "primary": name == primary_predictor,
        }
        # ``overall_score`` is a 0..1 scalar in the platform contract.
        # Lower MAE is better, so we expose ``hit_rate`` here (which
        # is naturally bounded in [0, 1]) and let detail rows carry
        # the raw MAE / CRPS for the grid.
        hit_rate = m.get("hit_rate")
        scorecards.append(
            ScorecardSummary(
                run_id=resolved_run_id,
                kind=ScorecardKind.BACKTEST,
                overall_score=float(hit_rate) if hit_rate is not None else None,
                # No pass/fail gate at v1 — the experiment is the
                # gate.
                passed=None,
                thresholds={},
                details=details,
            )
        )

    # Build dataset spec if requested. The dataset row carries the
    # corpus dimensions in metadata so cross-references stay
    # self-describing.
    dataset_spec: Optional[DatasetSpec] = None
    if dataset_id is not None:
        if not dataset_name:
            raise ValueError(
                "dataset_name is required when dataset_id is provided"
            )
        dataset_spec = DatasetSpec(
            dataset_id=dataset_id,
            name=dataset_name,
            version="0.1.0",
            # Synthetic data has no on-disk source — point at the
            # generating run so the registry has a self-link.
            source=f"synthetic:{resolved_run_id}",
            n_rows=n_agents * n_ticks,
            n_columns=3,
            metadata={
                "pillar": "worlds",
                "experiment": "trajectory_3d_backtest",
                "n_agents": n_agents,
                "n_ticks_per_agent": n_ticks,
                "axes": ["x", "y", "z"],
            },
        )

    # Register (registry-provided or self-managed registry context).
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

    Steps:
        1. Register the run (creates the ``runs`` row).
        2. Register every per-predictor scorecard. The registry uses
           an upsert keyed on ``(run_id, kind)`` — but because all
           our scorecards share ``kind=BACKTEST``, only ONE row per
           run survives. We work around this by rewriting the kind
           per predictor — but that violates the enum. Instead, we
           cram every predictor's metrics into a SINGLE scorecard's
           ``details`` dict so all predictors live on one row.
        3. Optionally register the dataset spec.

    Each step is idempotent (upsert semantics) so retries are safe.
    """
    registry.register(artifact)

    # The scorecards table has primary key (run_id, kind). With all
    # our scorecards sharing kind=BACKTEST, only the last write
    # would survive. So we COLLAPSE every predictor's scorecard into
    # one row whose ``details["per_predictor"]`` dict carries the
    # full comparison.
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
                # row reads naturally without descending into the
                # nested dict.
                "spatial_mae": primary_details.get("spatial_mae"),
                "hit_rate": primary_details.get("hit_rate"),
                "crps": primary_details.get("crps"),
                "n_trials": primary_details.get("n_trials"),
                # Full per-predictor breakdown.
                "per_predictor": per_pred,
            },
        )
        registry.register_scorecard(merged)

    if dataset_spec is not None:
        registry.register_dataset(dataset_spec)


__all__ = ["register_trajectory_backtest_run"]
