"""Generate, validate, save, and compare standardized experiment reports.

This module produces reports conforming to the experiment-report.schema.json
schema.  Every autoresearch experiment (baseline or JEPA variant) must pass
through ``generate_report`` so that results are auditable, machine-readable,
and diffable across runs.

Lifecycle
---------
1.  An experiment runner (e.g. ``run_baseline_backtest.py``) collects
    ``metrics_before`` and ``metrics_after`` dicts — each keyed by dataset
    name, with values being per-dataset metric dicts.
2.  ``generate_report(...)`` assembles those into the canonical schema,
    computes deltas, and emits a recommendation.
3.  ``validate_report(report)`` checks the dict against the JSON Schema.
4.  ``save_report(report, output_dir)`` persists to
    ``progress/autoresearch/reports/<run_id>.json``.
5.  ``compare_reports(a, b)`` produces a side-by-side diff of two reports.

Immutability: generated reports are intended to be write-once.  ``save_report``
will *overwrite* an existing file at the same path (idempotent re-run), but
the caller should treat persisted reports as append-only artifacts.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[3]
SCHEMA_PATH = REPO_ROOT / "research" / "autoresearch" / "ledger" / "experiment-report.schema.json"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "progress" / "autoresearch" / "reports"

# Metric keys that appear in every per-dataset and aggregate block.
_METRIC_KEYS = ("crps", "calibration_error", "hit_rate", "mean_error", "runtime_seconds")

# Thresholds for the automated recommendation heuristic.
# A CRPS improvement (negative delta) beyond this triggers "keep".
_CRPS_IMPROVEMENT_THRESHOLD = -0.005
# A CRPS regression beyond this triggers "discard".
_CRPS_REGRESSION_THRESHOLD = 0.02


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def generate_report(
    run_id: str,
    benchmark_id: str,
    metrics_before: dict[str, dict[str, float]],
    metrics_after: dict[str, dict[str, float]],
    *,
    retrieval_metrics: dict[str, Any] | None = None,
    lane_id: str = "jepa-retrieval-lane-v1",
    branch: str | None = None,
    commit: str | None = None,
    artifacts: list[str] | None = None,
) -> dict[str, Any]:
    """Build a report dict conforming to experiment-report.schema.json.

    Parameters
    ----------
    run_id:
        Unique run identifier, matching the experiment-ledger entry.
    benchmark_id:
        Benchmark manifest id (e.g. ``jepa-retrieval-core-v1``).
    metrics_before:
        ``{dataset_name: {crps, calibration_error, hit_rate, mean_error, runtime_seconds}}``
        for the baseline.
    metrics_after:
        Same shape as *metrics_before* for the experiment.
    retrieval_metrics:
        Optional dict with ``top_k_overlap``, ``rank_correlation``, and/or
        ``rank_lift_summary``.
    lane_id:
        Autoresearch lane id.
    branch:
        Git branch name (informational).
    commit:
        Git commit SHA (informational).
    artifacts:
        Repo-relative paths to related output files.

    Returns
    -------
    dict conforming to experiment-report.schema.json.
    """
    # --- per-dataset breakdown ---
    datasets_used = sorted(set(list(metrics_before.keys()) + list(metrics_after.keys())))

    before_list = _build_dataset_metrics_list(metrics_before, datasets_used)
    after_list = _build_dataset_metrics_list(metrics_after, datasets_used)

    # --- aggregates ---
    agg_before = _aggregate_metrics(before_list)
    agg_after = _aggregate_metrics(after_list)
    agg_deltas = {k: agg_after[k] - agg_before[k] for k in _METRIC_KEYS}

    # --- recommendation ---
    recommendation, rationale = _recommend(agg_deltas)

    # --- retrieval comparison ---
    retrieval_comparison: dict[str, Any] | None = None
    if retrieval_metrics is not None:
        retrieval_comparison = {}
        if "top_k_overlap" in retrieval_metrics:
            retrieval_comparison["top_k_overlap"] = float(retrieval_metrics["top_k_overlap"])
        if "rank_correlation" in retrieval_metrics:
            retrieval_comparison["rank_correlation"] = float(retrieval_metrics["rank_correlation"])
        if "rank_lift_summary" in retrieval_metrics:
            retrieval_comparison["rank_lift_summary"] = str(retrieval_metrics["rank_lift_summary"])

    report: dict[str, Any] = {
        "report_id": str(uuid.uuid4()),
        "run_id": run_id,
        "benchmark_id": benchmark_id,
        "lane_id": lane_id,
        "timestamp": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "branch": branch,
        "commit": commit,
        "datasets_used": datasets_used,
        "retrieval_comparison": retrieval_comparison,
        "backtest_metrics": {
            "before": before_list,
            "after": after_list,
        },
        "aggregate_metrics": {
            "before": agg_before,
            "after": agg_after,
            "deltas": agg_deltas,
        },
        "recommendation": recommendation,
        "rationale": rationale,
        "artifacts": artifacts or [],
    }
    return report


def save_report(report: dict[str, Any], output_dir: str | Path | None = None) -> Path:
    """Persist a report to ``<output_dir>/<run_id>.json``.

    Parameters
    ----------
    report:
        A dict produced by ``generate_report``.
    output_dir:
        Directory to write into.  Defaults to
        ``progress/autoresearch/reports/``.

    Returns
    -------
    Path to the written file.
    """
    out = Path(output_dir) if output_dir is not None else DEFAULT_OUTPUT_DIR
    out.mkdir(parents=True, exist_ok=True)
    # Sanitize run_id for filesystem safety — replace characters that are
    # problematic in filenames.
    safe_name = report["run_id"].replace("/", "_").replace(":", "-")
    path = out / f"{safe_name}.json"
    path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return path


def validate_report(report: dict[str, Any]) -> list[str]:
    """Validate a report dict against experiment-report.schema.json.

    Returns a list of error strings.  An empty list means the report is valid.

    Uses ``jsonschema`` if available, otherwise falls back to a lightweight
    structural check so this module works without optional dependencies.
    """
    errors: list[str] = []

    # Try jsonschema first for full validation.
    try:
        import jsonschema  # type: ignore[import-untyped]

        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        validator = jsonschema.Draft202012Validator(schema)
        for error in sorted(validator.iter_errors(report), key=lambda e: list(e.path)):
            errors.append(f"{'.'.join(str(p) for p in error.absolute_path) or '<root>'}: {error.message}")
        return errors
    except ImportError:
        pass

    # Lightweight fallback: check required top-level keys and basic types.
    required_keys = [
        "report_id", "run_id", "benchmark_id", "lane_id",
        "timestamp", "datasets_used", "backtest_metrics",
        "aggregate_metrics", "recommendation", "rationale",
    ]
    for key in required_keys:
        if key not in report:
            errors.append(f"Missing required key: {key}")

    if "recommendation" in report and report["recommendation"] not in ("keep", "discard", "needs_review"):
        errors.append(f"Invalid recommendation: {report['recommendation']}")

    if "datasets_used" in report:
        if not isinstance(report["datasets_used"], list) or len(report["datasets_used"]) == 0:
            errors.append("datasets_used must be a non-empty list")

    if "backtest_metrics" in report:
        bm = report["backtest_metrics"]
        if not isinstance(bm, dict):
            errors.append("backtest_metrics must be an object")
        else:
            for section in ("before", "after"):
                if section not in bm:
                    errors.append(f"backtest_metrics missing '{section}'")
                elif not isinstance(bm[section], list):
                    errors.append(f"backtest_metrics.{section} must be an array")

    if "aggregate_metrics" in report:
        am = report["aggregate_metrics"]
        if not isinstance(am, dict):
            errors.append("aggregate_metrics must be an object")
        else:
            for section in ("before", "after", "deltas"):
                if section not in am:
                    errors.append(f"aggregate_metrics missing '{section}'")

    return errors


def compare_reports(report_a: dict[str, Any], report_b: dict[str, Any]) -> dict[str, Any]:
    """Produce a side-by-side comparison of two experiment reports.

    Parameters
    ----------
    report_a, report_b:
        Dicts produced by ``generate_report``.

    Returns
    -------
    A comparison dict with per-metric deltas and metadata diffs.
    """
    comparison: dict[str, Any] = {
        "report_a_id": report_a.get("report_id"),
        "report_b_id": report_b.get("report_id"),
        "report_a_run_id": report_a.get("run_id"),
        "report_b_run_id": report_b.get("run_id"),
    }

    # Compare aggregate metrics (after vs after).
    agg_a = report_a.get("aggregate_metrics", {}).get("after", {})
    agg_b = report_b.get("aggregate_metrics", {}).get("after", {})
    metric_comparison: dict[str, dict[str, float | None]] = {}
    for key in _METRIC_KEYS:
        val_a = agg_a.get(key)
        val_b = agg_b.get(key)
        delta = None
        if val_a is not None and val_b is not None:
            delta = val_b - val_a
        metric_comparison[key] = {"report_a": val_a, "report_b": val_b, "delta": delta}
    comparison["aggregate_after_comparison"] = metric_comparison

    # Compare recommendations.
    comparison["recommendation_a"] = report_a.get("recommendation")
    comparison["recommendation_b"] = report_b.get("recommendation")

    # Dataset overlap.
    ds_a = set(report_a.get("datasets_used", []))
    ds_b = set(report_b.get("datasets_used", []))
    comparison["datasets_shared"] = sorted(ds_a & ds_b)
    comparison["datasets_only_a"] = sorted(ds_a - ds_b)
    comparison["datasets_only_b"] = sorted(ds_b - ds_a)

    return comparison


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _build_dataset_metrics_list(
    metrics: dict[str, dict[str, float]],
    datasets: list[str],
) -> list[dict[str, Any]]:
    """Convert a ``{dataset: {metric: value}}`` dict into the schema's array format.

    Datasets present in *datasets* but missing from *metrics* get zero-filled
    entries so before/after arrays always align.
    """
    result: list[dict[str, Any]] = []
    for ds in datasets:
        m = metrics.get(ds, {})
        result.append({
            "dataset": ds,
            "crps": float(m.get("crps", 0.0)),
            "calibration_error": float(m.get("calibration_error", 0.0)),
            "hit_rate": float(m.get("hit_rate", 0.0)),
            "mean_error": float(m.get("mean_error", 0.0)),
            "runtime_seconds": float(m.get("runtime_seconds", 0.0)),
        })
    return result


def _aggregate_metrics(dataset_list: list[dict[str, Any]]) -> dict[str, float]:
    """Mean-aggregate a list of per-dataset metric dicts."""
    n = len(dataset_list)
    if n == 0:
        return {k: 0.0 for k in _METRIC_KEYS}
    agg: dict[str, float] = {}
    for key in _METRIC_KEYS:
        # runtime_seconds sums rather than averages (total wall time).
        if key == "runtime_seconds":
            agg[key] = sum(d.get(key, 0.0) for d in dataset_list)
        else:
            agg[key] = sum(d.get(key, 0.0) for d in dataset_list) / n
    return agg


def _recommend(deltas: dict[str, float]) -> tuple[str, str]:
    """Derive a recommendation from aggregate metric deltas.

    Heuristic (intentionally simple — human override is expected):
    - If CRPS improved beyond threshold and no large regression in other
      metrics, recommend "keep".
    - If CRPS regressed beyond threshold, recommend "discard".
    - Otherwise "needs_review".

    Returns
    -------
    (recommendation, rationale) tuple.
    """
    crps_delta = deltas.get("crps", 0.0)
    hit_rate_delta = deltas.get("hit_rate", 0.0)
    calibration_delta = deltas.get("calibration_error", 0.0)

    parts: list[str] = []
    parts.append(f"CRPS delta: {crps_delta:+.4f}")
    parts.append(f"hit_rate delta: {hit_rate_delta:+.4f}")
    parts.append(f"calibration_error delta: {calibration_delta:+.4f}")

    if crps_delta <= _CRPS_IMPROVEMENT_THRESHOLD:
        # CRPS improved — check for large regressions elsewhere.
        if hit_rate_delta < -0.10:
            return "needs_review", f"CRPS improved but hit_rate regressed significantly. {'; '.join(parts)}"
        return "keep", f"CRPS improved beyond threshold. {'; '.join(parts)}"

    if crps_delta >= _CRPS_REGRESSION_THRESHOLD:
        return "discard", f"CRPS regressed beyond threshold. {'; '.join(parts)}"

    return "needs_review", f"Marginal change — manual review recommended. {'; '.join(parts)}"
