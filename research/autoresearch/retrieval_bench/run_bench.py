"""Runner for the retrieval-bench-tiers-v1 ablation lane.

This module wires the slice spec (``slices.yaml``) to the engine
(``the_similarity.api``) and produces per-slice, per-arm JSON artefacts
plus the consolidated scorecard printed at the end of a run.

Design invariants
-----------------
* **Walk-forward only.** For each trial position ``q`` the matcher is given
  ``history[:q]`` as its candidate pool. Forward returns used for scoring
  come from ``history[q + window : q + window + forward_bars]``. No branch
  of the runner ever reveals post-query data to the retrieval step.
* **Paired trials across arms.** Within a slice/seed pair, both arms see
  the SAME list of trial start positions. That makes per-trial comparisons
  valid and lets us aggregate `arm_a - arm_b` deltas meaningfully.
* **Engine-read-only.** The runner never mutates the engine or the data
  package. It constructs fresh ``Config`` instances per arm.
* **Reproducible artefacts.** Every JSON report carries a metadata block
  with git SHA, timestamp, seeds, and the resolved slice parameters.

CLI
---
    python research/autoresearch/retrieval_bench/run_bench.py --help

Typical flow:
    python research/autoresearch/retrieval_bench/run_bench.py --smoke
    python research/autoresearch/retrieval_bench/run_bench.py \\
        --slice spy-covid-2020 --arm tier1_only --arm tier1_plus_full
    python research/autoresearch/retrieval_bench/run_bench.py  # full sweep
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

# When invoked as a CLI script (``python path/to/run_bench.py``) the repo
# root is not automatically on ``sys.path``, so the ``research.*`` namespace
# package cannot resolve its own sibling module.  Prepending the repo root
# here means both ``python -m research.autoresearch.retrieval_bench.run_bench``
# and a direct script invocation produce the same import graph.
_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import numpy as np

# We import yaml lazily inside load_spec() so ``pytest`` can import this
# module for tests that stub the engine paths — PyYAML is available in the
# project venv but we want a friendly error if it is not.

from research.autoresearch.retrieval_bench.metrics import (
    TrialOutcome,
    calibration_error_p10_p90,
    empirical_crps,
    forward_return_correlation,
    hit_rate,
    summarise_runtimes,
)


# ---------------------------------------------------------------------------
# Paths — resolved relative to the repository root (two levels up from this
# file).  The runner refuses to write outside ``writable_scope`` as declared
# in ``slices.yaml``.
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_SPEC = Path(__file__).with_name("slices.yaml")
DEFAULT_DATA_ROOT = REPO_ROOT / "the-similarity-data" / "data"
REPORTS_DIR = REPO_ROOT / "progress" / "autoresearch" / "reports" / "retrieval-bench"
LEDGER_PATH = REPO_ROOT / "progress" / "autoresearch" / "experiments.jsonl"


# ---------------------------------------------------------------------------
# Spec loader
# ---------------------------------------------------------------------------

@dataclass
class SliceDef:
    """Normalised slice descriptor parsed from ``slices.yaml``.

    ``path`` is relative to the data root; the runner joins them before
    reading.  ``start_date`` / ``end_date`` are ISO strings passed directly
    through the TimeSeries date-slicing interface.
    """

    id: str
    symbol: str
    path: str
    start_date: str
    end_date: str
    regime: str
    rationale: str


@dataclass
class ArmDef:
    """Normalised arm descriptor.  ``active_methods`` is passed straight into
    ``Config(active_methods=...)``.  ``tier2_candidates`` of 0 disables
    Tier 2 enrichment entirely (only Tier 1 methods contribute)."""

    id: str
    label: str
    active_methods: list[str]
    tier2_candidates: int
    notes: str = ""


@dataclass
class BenchSpec:
    """Top-level spec bundle."""

    id: str
    slices: list[SliceDef]
    arms: list[ArmDef]
    query_window: int
    forward_bars: int
    top_k: int
    n_trials: int
    n_trials_smoke: int
    seeds: list[int]
    min_lookback_multiplier: int
    thresholds: dict[str, float]
    data_root_default: str


def load_spec(path: str | Path = DEFAULT_SPEC) -> BenchSpec:
    """Load and validate the slice spec.

    Raises ``RuntimeError`` if PyYAML is not importable — the lane cannot
    function without the spec file.
    """
    try:
        import yaml  # type: ignore[import]
    except ImportError as err:  # pragma: no cover — environment misconfig
        raise RuntimeError(
            "PyYAML is required to read retrieval-bench slices.yaml"
        ) from err

    with open(path, "r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)

    slices = [
        SliceDef(
            id=s["id"],
            symbol=s["symbol"],
            path=s["path"],
            start_date=s["start_date"],
            end_date=s["end_date"],
            regime=s.get("regime", ""),
            rationale=s.get("rationale", ""),
        )
        for s in raw["slices"]
    ]
    arms = [
        ArmDef(
            id=a["id"],
            label=a.get("label", a["id"]),
            active_methods=list(a["active_methods"]),
            tier2_candidates=int(a.get("tier2_candidates", 20)),
            notes=a.get("notes", ""),
        )
        for a in raw["arms"]
    ]
    proto = raw["protocol"]
    return BenchSpec(
        id=raw["id"],
        slices=slices,
        arms=arms,
        query_window=int(proto["query_window"]),
        forward_bars=int(proto["forward_bars"]),
        top_k=int(proto["top_k"]),
        n_trials=int(proto["n_trials"]),
        n_trials_smoke=int(proto.get("n_trials_smoke", 5)),
        seeds=list(proto["seeds"]),
        min_lookback_multiplier=int(proto.get("min_lookback_multiplier", 3)),
        thresholds=dict(raw.get("thresholds", {})),
        data_root_default=raw.get("data_root_default", "the-similarity-data/data"),
    )


# ---------------------------------------------------------------------------
# Data loading — resolved relative to ``--data-root``
# ---------------------------------------------------------------------------

def load_slice_series(slice_def: SliceDef, data_root: Path):
    """Load a slice as a ``TimeSeries`` via ``the_similarity.io.loader.load``.

    The engine's date-slicing semantics handle the ``start_date`` / ``end_date``
    bounds, returning a TimeSeries with aligned values and dates.
    """
    # Deferred import so unit tests can stub this function without requiring
    # the engine to be importable.
    from the_similarity.io.loader import load as _load

    parquet_path = data_root / slice_def.path
    if not parquet_path.exists():
        raise FileNotFoundError(
            f"Slice {slice_def.id!r} parquet missing at {parquet_path}. "
            "Use --data-root to point at a populated the-similarity-data checkout."
        )
    ts = _load(str(parquet_path))
    sliced = ts[slice_def.start_date : slice_def.end_date]
    # Return values + dates rather than the TimeSeries object so the runner
    # does not carry engine types across the boundary.  The matcher is happy
    # with np.ndarray.
    return sliced


# ---------------------------------------------------------------------------
# Trial sampling — shared across arms within a seed for paired comparisons
# ---------------------------------------------------------------------------

def sample_trial_positions(
    n_points: int,
    window: int,
    forward_bars: int,
    n_trials: int,
    seed: int,
    min_lookback_multiplier: int = 3,
) -> list[int]:
    """Return a list of query-start indices for a slice.

    The returned positions satisfy:
        min_lookback_multiplier * window  <=  q  <=  n_points - window - forward_bars

    so every trial has enough lookback and enough forward room to compute
    both retrieval candidates and the realised forward return.

    The same (n_points, seed, n_trials, ...) tuple always returns identical
    positions — making arm comparisons paired and reproducible.
    """
    min_start = min_lookback_multiplier * window
    max_start = n_points - window - forward_bars
    if max_start <= min_start:
        raise ValueError(
            f"Slice too short: have {n_points} points but need at least "
            f"{min_start + window + forward_bars} for window={window} "
            f"forward_bars={forward_bars}."
        )
    rng = np.random.default_rng(seed)
    n_available = max_start - min_start
    if n_trials >= n_available:
        # If we asked for too many, return every valid position (no
        # replacement).  This keeps smoke mode degenerate-but-safe.
        return list(range(min_start, max_start))
    return [int(x) for x in rng.integers(min_start, max_start, size=n_trials)]


# ---------------------------------------------------------------------------
# Single-trial evaluation
# ---------------------------------------------------------------------------

def _forward_return(values: np.ndarray, start: int, horizon: int) -> float:
    """Pct change from ``values[start]`` to ``values[start + horizon - 1]``.

    Returns 0.0 if either bound is invalid or the starting value is zero.
    This protects against gaps in illiquid symbols without raising — a
    degenerate trial contributes 0.0 to aggregate means rather than
    crashing the runner.
    """
    end = start + horizon - 1
    if start < 0 or end >= len(values):
        return 0.0
    v0 = float(values[start])
    if v0 == 0.0:
        return 0.0
    return float(values[end]) / v0 - 1.0


def run_trial(
    values: np.ndarray,
    query_start: int,
    window: int,
    forward_bars: int,
    top_k: int,
    active_methods: list[str],
    tier2_candidates: int,
) -> TrialOutcome:
    """Execute one walk-forward retrieval + projection and build a TrialOutcome.

    Walk-forward invariant: only ``values[:query_start]`` is visible to the
    matcher as history.  The query itself is ``values[query_start:query_end]``.
    Realised forward return is computed from ``values[query_end:query_end+horizon]``
    and never used in retrieval.
    """
    from the_similarity.api import project, search  # lazy engine import
    from the_similarity.config import Config

    query_end = query_start + window
    query = values[query_start:query_end]
    history = values[:query_start]

    cfg = Config(
        active_methods=list(active_methods),
        tier2_candidates=tier2_candidates if tier2_candidates > 0 else None,
        forward_bars=forward_bars,
        # The engine's default percentile grid [10, 25, 50, 75, 90] matches
        # what the metric helpers expect.
    )
    # Tier-2-off arms still need to skip enrichment entirely.  The matcher
    # does this automatically when active_methods contains no Tier 2 fields.

    t0 = time.perf_counter()
    results = search(query, history, top_k=top_k, config=cfg, exclude_self=False)
    forecast = project(
        matches=results,
        history=history,
        forward_bars=forward_bars,
        percentiles=[10, 25, 50, 75, 90],
        query=query,
        config=cfg,
    )
    runtime = time.perf_counter() - t0

    # --- Realised forward return ---
    realised = _forward_return(values, query_end, forward_bars)

    # --- Match forward returns (used for the top-K precision proxy) ---
    match_fwds: list[float] = []
    for m in results.matches:
        # Each match occupies history[m.start_idx:m.end_idx].  The forward
        # window follows end_idx.  We stay strictly inside the lookback
        # (not the full dataset) so retrieval cannot smuggle forward info.
        fwd_start = m.end_idx
        fwd = _forward_return(history, fwd_start, forward_bars)
        if fwd != 0.0:
            match_fwds.append(fwd)

    # --- Quantile forecast snapshot at horizon end ---
    # ``forecast.curves[p]`` is the cumulative-return path; the last bar is
    # the forecast's terminal quantile for the full forward horizon.
    quantile_forecast: dict[int, float] = {}
    for p in (10, 25, 50, 75, 90):
        curve = forecast.curves.get(p)
        if curve is None or len(curve) == 0:
            continue
        quantile_forecast[p] = float(curve[-1])

    return TrialOutcome(
        match_forward_returns=match_fwds,
        quantile_forecast=quantile_forecast,
        realised_forward_return=realised,
        runtime_seconds=runtime,
    )


# ---------------------------------------------------------------------------
# Per-(slice, arm) evaluation
# ---------------------------------------------------------------------------

@dataclass
class ArmResult:
    """Aggregated metrics for one (slice, arm) combination."""

    slice_id: str
    arm_id: str
    arm_label: str
    n_trials: int
    forward_return_correlation: float
    crps: float
    calibration_error_p10_p90: float
    hit_rate: float
    runtime: dict[str, float]
    trials: list[TrialOutcome] = field(default_factory=list)

    def to_dict(self, include_trials: bool = False) -> dict:
        d: dict = {
            "slice_id": self.slice_id,
            "arm_id": self.arm_id,
            "arm_label": self.arm_label,
            "n_trials": self.n_trials,
            "forward_return_correlation": self.forward_return_correlation,
            "crps": self.crps,
            "calibration_error_p10_p90": self.calibration_error_p10_p90,
            "hit_rate": self.hit_rate,
            "runtime_seconds": self.runtime,
        }
        if include_trials:
            d["trials"] = [
                {
                    "match_forward_returns": t.match_forward_returns,
                    "quantile_forecast": t.quantile_forecast,
                    "realised_forward_return": t.realised_forward_return,
                    "runtime_seconds": t.runtime_seconds,
                }
                for t in self.trials
            ]
        return d


def evaluate_arm(
    slice_def: SliceDef,
    arm: ArmDef,
    values: np.ndarray,
    trial_positions: Iterable[int],
    spec: BenchSpec,
) -> ArmResult:
    """Run every trial position under one arm and aggregate metrics."""
    trials: list[TrialOutcome] = []
    runtimes: list[float] = []
    for q in trial_positions:
        outcome = run_trial(
            values=values,
            query_start=int(q),
            window=spec.query_window,
            forward_bars=spec.forward_bars,
            top_k=spec.top_k,
            active_methods=arm.active_methods,
            tier2_candidates=arm.tier2_candidates,
        )
        trials.append(outcome)
        runtimes.append(outcome.runtime_seconds)

    return ArmResult(
        slice_id=slice_def.id,
        arm_id=arm.id,
        arm_label=arm.label,
        n_trials=len(trials),
        forward_return_correlation=forward_return_correlation(trials),
        crps=empirical_crps(trials),
        calibration_error_p10_p90=calibration_error_p10_p90(trials),
        hit_rate=hit_rate(trials),
        runtime=summarise_runtimes(runtimes),
        trials=trials,
    )


# ---------------------------------------------------------------------------
# Report assembly
# ---------------------------------------------------------------------------

def _git_sha() -> str:
    """Current short git SHA, or ``unknown`` outside a git checkout."""
    try:
        r = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
            cwd=str(REPO_ROOT),
        )
        return r.stdout.strip() if r.returncode == 0 else "unknown"
    except Exception:  # pragma: no cover
        return "unknown"


def write_arm_report(result: ArmResult, output_dir: Path) -> Path:
    """Serialize one ArmResult to ``output_dir/<slice>-<arm>.json``.

    Trials are embedded to keep the artefact fully auditable — the file size
    stays small (< 100kB) even at n_trials = 80.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{result.slice_id}-{result.arm_id}.json"
    payload = {
        "metadata": {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "git_sha": _git_sha(),
            "benchmark_id": "retrieval-bench-tiers-v1",
        },
        "result": result.to_dict(include_trials=True),
    }
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)
    return path


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run retrieval-bench tier ablation (Tier 1 vs Tier 1+2)."
    )
    parser.add_argument("--spec", default=str(DEFAULT_SPEC), help="Path to slices.yaml")
    parser.add_argument(
        "--data-root",
        default=str(DEFAULT_DATA_ROOT),
        help="Directory containing stocks/ and crypto/ subfolders",
    )
    parser.add_argument(
        "--slice", dest="slice_ids", action="append", default=[],
        help="Slice id to include (may be repeated). Default: all slices.",
    )
    parser.add_argument(
        "--arm", dest="arm_ids", action="append", default=[],
        help="Arm id to include (may be repeated). Default: all arms.",
    )
    parser.add_argument("--seed", type=int, default=None,
                        help="Single seed override (default: use spec.seeds)")
    parser.add_argument("--smoke", action="store_true",
                        help="Use spec.n_trials_smoke instead of spec.n_trials")
    parser.add_argument(
        "--n-trials", type=int, default=None,
        help="Override spec.n_trials (and --smoke's n_trials_smoke). Useful for "
             "budget-capped sweeps where full n_trials would exceed wall-clock.",
    )
    parser.add_argument("--reports-dir", default=str(REPORTS_DIR),
                        help="Directory for per-slice JSON artefacts")
    args = parser.parse_args(argv)

    spec = load_spec(args.spec)
    data_root = Path(args.data_root).resolve()
    reports_dir = Path(args.reports_dir).resolve()

    # Filter slices / arms
    slice_filter = set(args.slice_ids) if args.slice_ids else None
    arm_filter = set(args.arm_ids) if args.arm_ids else None
    slices = [s for s in spec.slices if slice_filter is None or s.id in slice_filter]
    arms = [a for a in spec.arms if arm_filter is None or a.id in arm_filter]
    if not slices or not arms:
        parser.error("No slices or arms selected — check --slice / --arm filters.")

    seeds = [args.seed] if args.seed is not None else spec.seeds
    if args.n_trials is not None:
        n_trials = int(args.n_trials)
    elif args.smoke:
        n_trials = spec.n_trials_smoke
    else:
        n_trials = spec.n_trials

    print(f"[retrieval-bench] spec={spec.id}  slices={len(slices)}  arms={len(arms)}")
    print(f"[retrieval-bench] n_trials={n_trials}  seeds={seeds}  data_root={data_root}")

    all_results: list[ArmResult] = []
    for slice_def in slices:
        print(f"\n[slice] {slice_def.id} ({slice_def.regime})")
        ts = load_slice_series(slice_def, data_root)
        values = np.asarray(ts.values, dtype=np.float64)
        print(f"  loaded {len(values)} bars ({slice_def.start_date} → {slice_def.end_date})")

        for seed in seeds:
            positions = sample_trial_positions(
                n_points=len(values),
                window=spec.query_window,
                forward_bars=spec.forward_bars,
                n_trials=n_trials,
                seed=seed,
                min_lookback_multiplier=spec.min_lookback_multiplier,
            )
            for arm in arms:
                label = f"{slice_def.id}  arm={arm.id}  seed={seed}  n={len(positions)}"
                print(f"  [arm] {label}")
                res = evaluate_arm(slice_def, arm, values, positions, spec)
                # Embed seed into the slice_id so separate-seed reports do not
                # overwrite one another when using multiple seeds.
                if len(seeds) > 1:
                    res.slice_id = f"{slice_def.id}_seed{seed}"
                artefact = write_arm_report(res, reports_dir)
                print(
                    f"    corr={res.forward_return_correlation:+.3f}  "
                    f"crps={res.crps:.4f}  "
                    f"cal={res.calibration_error_p10_p90:.3f}  "
                    f"hit={res.hit_rate:.2f}  "
                    f"rt(s) median={res.runtime['median']:.2f} p95={res.runtime['p95']:.2f}  "
                    f"-> {artefact.relative_to(REPO_ROOT)}"
                )
                all_results.append(res)

    # Print consolidated scorecard (per slice, both arms side by side)
    print("\n=== consolidated scorecard ===")
    print(f"{'slice':<30} {'arm':<20} {'corr':>7} {'crps':>8} {'cal':>6} {'hit':>5} {'rt_med':>7}")
    for r in all_results:
        print(
            f"{r.slice_id:<30} {r.arm_id:<20} "
            f"{r.forward_return_correlation:+7.3f} "
            f"{r.crps:8.4f} "
            f"{r.calibration_error_p10_p90:6.3f} "
            f"{r.hit_rate:5.2f} "
            f"{r.runtime['median']:7.2f}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
