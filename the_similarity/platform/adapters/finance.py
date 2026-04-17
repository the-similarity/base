"""Finance pillar -> platform registry adapter.

Wraps the output of :func:`the_similarity.api.backtest` (a
:class:`~the_similarity.core.backtester.BacktestReport`) into a
:class:`~the_similarity.platform.artifacts.RunArtifact` with
``kind=RunKind.FINANCE``, and persists it through a shared
:class:`~the_similarity.platform.registry.RunRegistry`.

Design notes
------------
- **Dict-or-report** input: the adapter accepts either a ``BacktestReport``
  object or a plain dict so tests can feed a fake without instantiating the
  dataclass (which transitively imports numpy / the scorer stack).
- **Best-effort**: registration failures are the caller's problem. Finance
  backtests already persist whatever the user cares about in-memory; losing
  a registry row is an ops inconvenience, not a data-loss event.
- **Trust + Calibration artifacts**: when ``register=True`` in
  :func:`the_similarity.api.backtest`, this adapter computes and registers
  a :class:`~the_similarity.platform.adapters.trust.TrustArtifact` and a
  :class:`~the_similarity.platform.adapters.calibration.CalibrationArtifact`
  alongside the run. These provide structured quality gates and per-
  percentile calibration diagnostics without requiring downstream consumers
  to re-derive the metrics.
- **Pillar label**: the :class:`RunArtifact` contract has no ``pillar``
  field; we mirror the label into ``summary["pillar"] = "finance"`` so UI
  clients can filter without a schema change. ``kind=RunKind.FINANCE``
  already carries the same information for Python consumers.
"""

from __future__ import annotations

from typing import Any, Dict, Mapping, Optional

# Import the registry and artifact shapes lazily-safe: these are all pure
# Python / stdlib so the import is cheap and safe at module load.
from the_similarity.platform.artifacts import (
    RunArtifact,
    RunKind,
    iso_now,
    new_run_id,
)
from the_similarity.platform.registry import RunRegistry


# ---------------------------------------------------------------------------
# Coercion helpers
# ---------------------------------------------------------------------------


def _coerce_report(report: Any) -> Dict[str, Any]:
    """Extract headline fields from a backtest result of any shape.

    Accepts either a ``BacktestReport`` (with ``.hit_rate``,
    ``.calibration``, ``.crps``, ``.mean_error``, ``.coverage``,
    ``.n_valid_trials``, ``.n_skipped_trials``) or a plain dict with the
    same keys. Missing keys surface as ``None`` in the returned dict —
    callers decide whether to treat that as a failure.

    Why not a TypedDict? Because the upstream report is a frozen dataclass
    that we cannot import at module top without pulling numpy. Duck-typing
    via ``getattr`` / ``dict.get`` avoids the transitive dependency.
    """
    out: Dict[str, Any] = {}

    if isinstance(report, Mapping):
        # Dict path: copy the subset we care about, coercing nested dicts
        # (calibration) through dict() so the JSON dump never references
        # a foreign mapping impl (e.g. MappingProxyType from a frozen
        # dataclass's __dict__).
        for key in (
            "hit_rate",
            "mean_error",
            "crps",
            "coverage",
            "interval_score",
            "profit_factor",
            "max_drawdown",
            "sharpe",
            "n_valid_trials",
            "n_skipped_trials",
            "window_size",
            "forward_bars",
        ):
            if key in report:
                out[key] = report[key]
        calib = report.get("calibration")
        if calib is not None:
            # Keys in BacktestReport.calibration are percentile ints; JSON
            # object keys must be strings. Stringify up-front so the
            # registry's JSON column round-trips cleanly.
            out["calibration"] = {str(k): v for k, v in dict(calib).items()}
        return out

    # Object path: pull attributes defensively. ``getattr`` with a default
    # makes the adapter tolerate lightweight fakes in tests (only the
    # fields a given test cares about need to be defined).
    for key in (
        "hit_rate",
        "mean_error",
        "crps",
        "coverage",
        "interval_score",
        "profit_factor",
        "max_drawdown",
        "sharpe",
        "n_valid_trials",
        "n_skipped_trials",
        "window_size",
        "forward_bars",
    ):
        val = getattr(report, key, None)
        if val is not None:
            out[key] = val
    calib = getattr(report, "calibration", None)
    if calib:
        out["calibration"] = {str(k): v for k, v in dict(calib).items()}
    return out


def _enrich_summary(summary: Dict[str, Any]) -> Dict[str, Any]:
    """Add computed trust_score and calibration_grade to the summary.

    Enriches the summary dict in-place with:

    - ``trust_score``: composite 0..1 score derived from:
      ``0.4 * hit_rate + 0.3 * coverage + 0.3 * (1 - min(crps, 1))``
    - ``calibration_grade``: "excellent" / "good" / "fair" / "poor"
      based on mean absolute calibration error across percentiles.

    These are convenience fields so the registry's summary column carries
    the quality signal without requiring a join to the trust artifact.
    """
    from the_similarity.platform.adapters.trust import (
        compute_calibration_grade,
        compute_trust_score,
    )

    hit_rate = float(summary.get("hit_rate", 0.0) or 0.0)
    coverage = float(summary.get("coverage", 0.0) or 0.0)
    crps_val = float(summary.get("crps", 0.0) or 0.0)
    calibration = summary.get("calibration", {})

    summary["trust_score"] = compute_trust_score(hit_rate, coverage, crps_val)
    summary["calibration_grade"] = compute_calibration_grade(calibration or {})

    return summary


# ---------------------------------------------------------------------------
# Public adapter
# ---------------------------------------------------------------------------


def register_backtest_run(
    backtest_result: Any,
    config: Optional[Mapping[str, Any]] = None,
    seed: Optional[int] = None,
    registry: Optional[RunRegistry] = None,
    db_path: Optional[str] = None,
    run_id: Optional[str] = None,
    source_id: Optional[str] = None,
) -> str:
    """Register a finance backtest run in the platform registry.

    In addition to the base :class:`RunArtifact`, this adapter also
    computes and registers:

    - A :class:`~the_similarity.platform.adapters.trust.TrustArtifact`
      (``trust.json`` artifact record) with the trust decision.
    - A :class:`~the_similarity.platform.adapters.calibration.CalibrationArtifact`
      (``calibration.json`` artifact record) with per-percentile detail.
    - A :class:`~the_similarity.platform.contracts.ScorecardSummary`
      with ``kind=BACKTEST`` containing ``trust_score`` and
      ``calibration_grade``.

    Parameters
    ----------
    backtest_result:
        Either a :class:`~the_similarity.core.backtester.BacktestReport` or
        any dict carrying the same headline fields (hit_rate, crps,
        calibration, ...). See :func:`_coerce_report` for accepted keys.
    config:
        Optional dict of run inputs (window_size, forward_bars, n_trials,
        top_k, etc.). Merged into the artifact's ``config``; overridden by
        nothing. Must be JSON-serializable — we do not coerce.
    seed:
        Optional RNG seed threaded through the backtester. ``None`` is
        acceptable (the artifact contract allows null).
    registry:
        Optional pre-opened :class:`RunRegistry`. When omitted the adapter
        opens one against ``db_path`` (or the default resolution — see
        :class:`RunRegistry`) and closes it before returning.
    db_path:
        Optional SQLite path override, used only when ``registry`` is
        None. Mirrors the CLI's ``--db`` precedence rules.
    run_id:
        Optional explicit run_id. Defaults to a fresh UUID4 hex. Passing
        an existing run_id triggers the registry's upsert behavior.
    source_id:
        Optional symbol / dataset identifier (e.g. ``"spy"``). Stored in
        ``provenance["source_id"]`` to match the copies pillar convention.

    Returns
    -------
    str
        The ``run_id`` written to the registry. Callers typically log
        this so the run is referenceable via
        ``python -m the_similarity.platform show <run_id>``.
    """
    summary = _coerce_report(backtest_result)
    # Stamp the pillar label so UI filters by pillar without re-reading the
    # enum. Keeping this in summary (not config) means it appears in the
    # CLI's one-line listing preview, which is the 90% case we optimize for.
    summary["pillar"] = "finance"

    # Enrich summary with computed trust_score + calibration_grade so
    # the headline numbers are available in the registry without joining
    # to the trust artifact.
    _enrich_summary(summary)

    # Build config dict with sensible defaults — callers may pass None and
    # still get a valid JSON object rather than a null in the DB.
    config_payload: Dict[str, Any] = dict(config) if config else {}
    # Copy headline knobs from the report into config too so the artifact
    # is self-describing even when the caller omitted them.
    for echo_key in ("window_size", "forward_bars"):
        if echo_key not in config_payload and echo_key in summary:
            config_payload[echo_key] = summary[echo_key]

    provenance: Dict[str, Any] = {
        "generator_name": "the_similarity.api.backtest",
        "generator_version": "0",
        "seed": seed,
        "created_at": iso_now(),
    }
    if source_id is not None:
        provenance["source_id"] = source_id

    resolved_run_id = run_id or new_run_id()

    artifact = RunArtifact(
        run_id=resolved_run_id,
        kind=RunKind.FINANCE,
        config=config_payload,
        seed=seed,
        # Finance runs are fully in-process; no on-disk artifact files.
        # Trust and calibration artifacts are registered as metadata rows
        # in the artifacts table, not as files on disk.
        artifact_paths={},
        summary=summary,
        provenance=provenance,
        created_at=iso_now(),
    )

    # Build trust + calibration artifacts from the enriched summary.
    from the_similarity.platform.adapters.trust import build_trust_artifact
    from the_similarity.platform.adapters.calibration import (
        build_calibration_artifact,
    )
    from the_similarity.platform.contracts import (
        ArtifactRecord,
        ScorecardKind,
        ScorecardSummary,
    )

    trust_artifact = build_trust_artifact(resolved_run_id, summary)
    calibration_artifact = build_calibration_artifact(
        resolved_run_id, summary.get("calibration", {})
    )

    # Build artifact records for trust.json and calibration.json so the
    # registry's artifacts table knows about them. These are metadata-only
    # (no on-disk file) — the content lives in the registry's JSON columns.
    trust_artifact_record = ArtifactRecord(
        run_id=resolved_run_id,
        name="trust",
        path="trust.json",
        content_type="application/json",
        created_at=iso_now(),
    )
    calibration_artifact_record = ArtifactRecord(
        run_id=resolved_run_id,
        name="calibration",
        path="calibration.json",
        content_type="application/json",
        created_at=iso_now(),
    )

    # Build a ScorecardSummary with kind=BACKTEST that carries the
    # trust_score + calibration_grade for quick grid display.
    scorecard = ScorecardSummary(
        run_id=resolved_run_id,
        kind=ScorecardKind.BACKTEST,
        overall_score=trust_artifact.trust_score,
        passed=trust_artifact.decision.value == "trusted",
        thresholds=trust_artifact.thresholds,
        details={
            "trust_score": trust_artifact.trust_score,
            "calibration_grade": trust_artifact.calibration_grade,
            "decision": trust_artifact.decision.value,
            "hit_rate": summary.get("hit_rate"),
            "coverage": summary.get("coverage"),
            "crps": summary.get("crps"),
            "mean_error": summary.get("mean_error"),
        },
    )

    # Two code paths: caller-provided registry (tests, long-running CLIs)
    # vs self-managed (one-shot programmatic use). In the self-managed
    # path we open + close inside a with-block to avoid leaking FDs.
    if registry is not None:
        _register_all(
            registry,
            artifact,
            trust_artifact_record,
            calibration_artifact_record,
            scorecard,
        )
        return resolved_run_id

    # db_path=None lets RunRegistry apply its own defaults (env var +
    # ~/.the_similarity/registry.db fallback). We only need to supply a
    # value if the caller explicitly pinned one.
    from pathlib import Path

    import os

    resolved: Path
    if db_path is not None:
        resolved = Path(db_path).expanduser()
    else:
        env_value = os.environ.get("THE_SIMILARITY_REGISTRY_DB")
        resolved = (
            Path(env_value).expanduser()
            if env_value
            else Path("~/.the_similarity/registry.db").expanduser()
        )

    with RunRegistry(resolved) as r:
        _register_all(
            r,
            artifact,
            trust_artifact_record,
            calibration_artifact_record,
            scorecard,
        )
    return resolved_run_id


def _register_all(
    registry: RunRegistry,
    artifact: RunArtifact,
    trust_artifact_record: Any,
    calibration_artifact_record: Any,
    scorecard: Any,
) -> None:
    """Register the run, artifact metadata, and scorecard in one place.

    Centralizes the multi-step registration so both the caller-provided
    and self-managed registry paths share identical write logic. Each
    step is idempotent (upsert semantics) so retries are safe.
    """
    # 1. Register the base run artifact (creates the runs row).
    registry.register(artifact)
    # 2. Register the trust + calibration artifact metadata rows.
    registry.register_artifact(trust_artifact_record)
    registry.register_artifact(calibration_artifact_record)
    # 3. Register the backtest scorecard summary.
    registry.register_scorecard(scorecard)


__all__ = ["register_backtest_run"]
