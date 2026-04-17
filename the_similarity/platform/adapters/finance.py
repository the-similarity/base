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
- **No file writing**: unlike copies/worlds, the finance pillar is fully
  in-process — there is no per-run directory on disk. ``artifact_paths`` is
  therefore empty and the registry row is the canonical record.
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

    artifact = RunArtifact(
        run_id=run_id or new_run_id(),
        kind=RunKind.FINANCE,
        config=config_payload,
        seed=seed,
        # Finance runs are fully in-process; no on-disk artifact files.
        # An empty dict is semantically "nothing to stream" rather than
        # None, which keeps the schema validator happy (required field).
        artifact_paths={},
        summary=summary,
        provenance=provenance,
        created_at=iso_now(),
    )

    # Two code paths: caller-provided registry (tests, long-running CLIs)
    # vs self-managed (one-shot programmatic use). In the self-managed
    # path we open + close inside a with-block to avoid leaking FDs.
    if registry is not None:
        return registry.register(artifact)

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
        return r.register(artifact)


__all__ = ["register_backtest_run"]
