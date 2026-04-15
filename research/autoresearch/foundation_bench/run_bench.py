"""Runner for the foundation-bench-v1 lane.

Walk-forward evaluation of foundation-model baselines (TimesFM, Chronos,
Moirai, MOMENT) and one classical wavelet baseline, measured on the
same ``retrieval-bench-tiers-v1`` slices so per-trial deltas are joinable
with 1A's artefacts.

Design invariants
-----------------
* **Walk-forward only.** Every adapter sees ``history[:query_start]``
  and produces a quantile forecast for the forward horizon. No branch of
  the runner reveals post-query bars to an adapter.
* **Paired trials.** Within a (slice, seed) pair, every model sees the
  identical trial-start indices so per-trial deltas are comparable.
* **Engine-read-only.** The runner imports from ``the_similarity`` only
  to load TimeSeries; engine config/methods are untouched.
* **Budget cap.** Each (model, slice) cell has a wall-clock cap
  (``--per-cell-budget-seconds``). Trials that would exceed the cap are
  recorded with ``status: "skipped_budget"`` and excluded from metric
  aggregation.
* **Metric parity.** Metric computations are delegated to
  ``research.autoresearch.retrieval_bench.metrics`` — no duplication.

CLI
---
    python research/autoresearch/foundation_bench/run_bench.py --help

Typical flow:
    python research/autoresearch/foundation_bench/run_bench.py --smoke
    python research/autoresearch/foundation_bench/run_bench.py \\
        --model wavelet_baseline --slice spy-covid-2020
    python research/autoresearch/foundation_bench/run_bench.py  # full sweep
"""
from __future__ import annotations

import argparse
import importlib
import json
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

# Repo root on sys.path so ``research.*`` resolves under both
# ``python script.py`` and ``python -m research.autoresearch.foundation_bench.run_bench``.
_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import numpy as np

# Metric helpers are REUSED from retrieval_bench — do not duplicate.
from research.autoresearch.retrieval_bench.metrics import (
    TrialOutcome,
    calibration_error_p10_p90,
    empirical_crps,
    hit_rate,
    summarise_runtimes,
)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_SPEC_SLICES = Path(__file__).with_name("slices.yaml")
DEFAULT_SPEC_MODELS = Path(__file__).with_name("models.yaml")
DEFAULT_DATA_ROOT = REPO_ROOT / "the-similarity-data" / "data"
REPORTS_DIR = REPO_ROOT / "progress" / "autoresearch" / "reports" / "foundation-bench"
REPORT_MD = REPO_ROOT / "progress" / "autoresearch" / "reports" / "foundation-bench-v1.md"
LEDGER_PATH = REPO_ROOT / "progress" / "autoresearch" / "experiments.jsonl"


# ---------------------------------------------------------------------------
# Spec loader
# ---------------------------------------------------------------------------

@dataclass
class SliceDef:
    """Normalised slice descriptor parsed from ``slices.yaml``."""

    id: str
    symbol: str
    path: str
    start_date: str
    end_date: str
    regime: str
    rationale: str


@dataclass
class ModelDef:
    """Normalised model descriptor parsed from ``models.yaml``.

    ``adapter_module`` / ``adapter_class`` are used by
    ``construct_adapter`` to dynamically load the adapter. The adapter is
    instantiated once per (model, slice) cell so heavy weights (when
    available) are amortised across trials.
    """

    id: str
    adapter_module: str
    adapter_class: str
    type: str
    default_config: dict
    expect_real_weights: bool
    explainability: str
    notes: str = ""


@dataclass
class BenchSpec:
    """Top-level bench spec bundle."""

    id: str
    slices: list[SliceDef]
    models: list[ModelDef]
    query_window: int
    forward_bars: int
    top_k: int
    n_trials: int
    n_trials_smoke: int
    seeds: list[int]
    min_lookback_multiplier: int
    per_cell_budget_seconds: float
    percentiles: list[int]
    thresholds: dict
    data_root_default: str


def load_spec(
    slices_path: str | Path = DEFAULT_SPEC_SLICES,
    models_path: str | Path = DEFAULT_SPEC_MODELS,
) -> BenchSpec:
    """Load and merge ``slices.yaml`` + ``models.yaml`` into a BenchSpec.

    Raises ``RuntimeError`` if PyYAML is not importable.
    """
    try:
        import yaml  # type: ignore[import]
    except ImportError as err:  # pragma: no cover
        raise RuntimeError("PyYAML required to load foundation-bench spec") from err

    with open(slices_path, "r", encoding="utf-8") as fh:
        slices_raw = yaml.safe_load(fh)
    with open(models_path, "r", encoding="utf-8") as fh:
        models_raw = yaml.safe_load(fh)

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
        for s in slices_raw["slices"]
    ]
    models = [
        ModelDef(
            id=m["id"],
            adapter_module=m["adapter_module"],
            adapter_class=m["adapter_class"],
            type=m.get("type", "foundation"),
            default_config=dict(m.get("default_config", {})),
            expect_real_weights=bool(m.get("expect_real_weights", False)),
            explainability=m.get("explainability", "low"),
            notes=m.get("notes", ""),
        )
        for m in models_raw["models"]
    ]
    proto = slices_raw["protocol"]
    return BenchSpec(
        id=slices_raw["id"],
        slices=slices,
        models=models,
        query_window=int(proto["query_window"]),
        forward_bars=int(proto["forward_bars"]),
        top_k=int(proto["top_k"]),
        n_trials=int(proto["n_trials"]),
        n_trials_smoke=int(proto.get("n_trials_smoke", 3)),
        seeds=list(proto["seeds"]),
        min_lookback_multiplier=int(proto.get("min_lookback_multiplier", 3)),
        per_cell_budget_seconds=float(proto.get("per_cell_budget_seconds", 180.0)),
        percentiles=list(proto.get("percentiles", [10, 25, 50, 75, 90])),
        thresholds=dict(slices_raw.get("thresholds", {})),
        data_root_default=slices_raw.get("data_root_default", "the-similarity-data/data"),
    )


# ---------------------------------------------------------------------------
# Adapter construction
# ---------------------------------------------------------------------------

def construct_adapter(model: ModelDef, seed: int):
    """Import the adapter module and instantiate the class.

    The adapter receives ``seed`` plus the model's ``default_config`` as
    kwargs.  Unknown kwargs are dropped (best-effort) so ``default_config``
    can document intended-but-unused parameters without breaking init.
    """
    mod = importlib.import_module(model.adapter_module)
    cls = getattr(mod, model.adapter_class)
    kwargs: dict = {"seed": seed}
    # Pass through any default_config key that the adapter's __init__ accepts.
    import inspect
    sig = inspect.signature(cls.__init__)
    for k, v in model.default_config.items():
        if k in sig.parameters:
            kwargs[k] = v
    return cls(**kwargs)


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_slice_values(slice_def: SliceDef, data_root: Path) -> np.ndarray:
    """Return the close-price array for a slice.

    Uses the same ``the_similarity.io.loader.load`` path as retrieval_bench
    so loaded bars and date bounds match exactly.
    """
    from the_similarity.io.loader import load as _load  # lazy engine import

    parquet_path = data_root / slice_def.path
    if not parquet_path.exists():
        raise FileNotFoundError(
            f"Slice {slice_def.id!r} parquet missing at {parquet_path}. "
            "Use --data-root to point at a populated the-similarity-data checkout."
        )
    ts = _load(str(parquet_path))
    sliced = ts[slice_def.start_date : slice_def.end_date]
    return np.asarray(sliced.values, dtype=np.float64)


def sample_trial_positions(
    n_points: int,
    window: int,
    forward_bars: int,
    n_trials: int,
    seed: int,
    min_lookback_multiplier: int = 3,
) -> list[int]:
    """Return query-start indices with enough lookback and forward room.

    The same (n_points, seed, n_trials, ...) tuple always returns the
    identical positions across models — so this lane's per-trial deltas
    line up with retrieval-bench-tiers-v1.
    """
    min_start = min_lookback_multiplier * window
    max_start = n_points - window - forward_bars
    if max_start <= min_start:
        raise ValueError(
            f"Slice too short: have {n_points} points; need at least "
            f"{min_start + window + forward_bars} for window={window} "
            f"forward_bars={forward_bars}."
        )
    rng = np.random.default_rng(seed)
    n_available = max_start - min_start
    if n_trials >= n_available:
        return list(range(min_start, max_start))
    return [int(x) for x in rng.integers(min_start, max_start, size=n_trials)]


# ---------------------------------------------------------------------------
# Single-trial evaluation
# ---------------------------------------------------------------------------

def _forward_return(values: np.ndarray, start: int, horizon: int) -> float:
    """Pct change from ``values[start]`` to ``values[start + horizon - 1]``.

    Safe degenerate semantics: returns 0.0 on bad bounds or zero start price.
    Mirrors ``retrieval_bench.run_bench._forward_return`` exactly so slices
    with identical positions produce identical realised returns.
    """
    end = start + horizon - 1
    if start < 0 or end >= len(values):
        return 0.0
    v0 = float(values[start])
    if v0 == 0.0:
        return 0.0
    return float(values[end]) / v0 - 1.0


@dataclass
class TrialRecord:
    """Per-trial bookkeeping: outcome + fallback flag.

    ``fallback_reason`` is None only when the adapter produced a real
    forecast (wavelet_baseline normally, other models only when their
    pretrained weights are actually reachable).
    """

    outcome: TrialOutcome
    fallback_reason: str | None
    adapter_metadata: dict = field(default_factory=dict)


def run_trial(
    adapter,
    values: np.ndarray,
    query_start: int,
    window: int,
    forward_bars: int,
    percentiles: list[int],
) -> TrialRecord:
    """Execute one walk-forward forecast and return a TrialRecord.

    The adapter sees ``history = values[:query_start]`` only; the
    realised forward return is computed from bars after the query window
    and never shown to the adapter.
    """
    query_end = query_start + window
    history = values[:query_start]

    t0 = time.perf_counter()
    forecast = adapter.predict_quantiles(history, forward_bars, percentiles)
    runtime = time.perf_counter() - t0

    realised = _forward_return(values, query_end, forward_bars)

    # Collapse path-level quantiles into a terminal-bar dict, matching the
    # shape retrieval_bench uses for its metrics.  The last forward bar is
    # the forecast's terminal quantile over the full horizon.
    quantile_forecast: dict[int, float] = {}
    for p, arr in forecast.quantiles.items():
        if arr is None or len(arr) == 0:
            continue
        quantile_forecast[int(p)] = float(arr[-1])

    outcome = TrialOutcome(
        match_forward_returns=[],  # foundation models don't expose "matches"
        quantile_forecast=quantile_forecast,
        realised_forward_return=realised,
        runtime_seconds=runtime,
    )
    return TrialRecord(
        outcome=outcome,
        fallback_reason=forecast.fallback_reason,
        adapter_metadata=dict(forecast.metadata or {}),
    )


# ---------------------------------------------------------------------------
# Per-(model, slice) cell
# ---------------------------------------------------------------------------

@dataclass
class CellResult:
    """Aggregated metrics for one (model, slice) cell.

    Fields mirror retrieval_bench's ArmResult plus fallback bookkeeping.
    """

    slice_id: str
    model_id: str
    n_trials: int
    n_skipped_budget: int
    any_fallback: bool
    fallback_ratio: float
    crps: float
    calibration_error_p10_p90: float
    hit_rate: float
    runtime: dict[str, float]
    records: list[TrialRecord] = field(default_factory=list)
    status: str = "ok"
    notes: str = ""

    def to_dict(self, include_trials: bool = True) -> dict:
        d: dict = {
            "slice_id": self.slice_id,
            "model_id": self.model_id,
            "n_trials": self.n_trials,
            "n_skipped_budget": self.n_skipped_budget,
            "any_fallback": self.any_fallback,
            "fallback_ratio": self.fallback_ratio,
            "crps": self.crps,
            "calibration_error_p10_p90": self.calibration_error_p10_p90,
            "hit_rate": self.hit_rate,
            "runtime_seconds": self.runtime,
            "status": self.status,
            "notes": self.notes,
        }
        if include_trials:
            d["trials"] = [
                {
                    "quantile_forecast": r.outcome.quantile_forecast,
                    "realised_forward_return": r.outcome.realised_forward_return,
                    "runtime_seconds": r.outcome.runtime_seconds,
                    "fallback_reason": r.fallback_reason,
                    "adapter_metadata": r.adapter_metadata,
                }
                for r in self.records
            ]
        return d


def evaluate_cell(
    slice_def: SliceDef,
    model: ModelDef,
    values: np.ndarray,
    trial_positions: Iterable[int],
    spec: BenchSpec,
    seed: int,
) -> CellResult:
    """Run all trials for one (model, slice) cell, enforcing budget cap.

    The budget cap is wall-clock across all trials. Once the cumulative
    runtime exceeds ``spec.per_cell_budget_seconds``, the remaining
    trials are NOT executed and the cell is annotated with
    ``status="skipped_budget"`` while still reporting metrics for the
    trials that did run.
    """
    adapter = construct_adapter(model, seed=seed)
    records: list[TrialRecord] = []
    runtimes: list[float] = []
    n_skipped = 0
    fallback_count = 0
    cumulative = 0.0
    budget = float(spec.per_cell_budget_seconds)

    positions = list(trial_positions)
    for i, q in enumerate(positions):
        # Budget check BEFORE we invoke the adapter — a cheap safeguard
        # that guarantees we never overrun by more than one trial's worth
        # of latency.
        if cumulative >= budget:
            n_skipped = len(positions) - i
            break
        rec = run_trial(
            adapter,
            values=values,
            query_start=int(q),
            window=spec.query_window,
            forward_bars=spec.forward_bars,
            percentiles=list(spec.percentiles),
        )
        records.append(rec)
        runtimes.append(rec.outcome.runtime_seconds)
        cumulative += rec.outcome.runtime_seconds
        if rec.fallback_reason is not None:
            fallback_count += 1

    n_done = len(records)
    outcomes = [r.outcome for r in records]
    any_fallback = fallback_count > 0
    ratio = (fallback_count / n_done) if n_done else 0.0

    # Status taxonomy:
    # - "skipped_budget" if any trials were dropped to stay under the cap
    # - "partial_synthetic_fallback" if every executed trial was fallback
    # - "partial_fallback" if some but not all executed trials were fallback
    # - "ok" if no fallbacks (wavelet_baseline real path)
    if n_skipped > 0 and ratio >= 1.0:
        status = "skipped_budget_synthetic"
    elif n_skipped > 0:
        status = "skipped_budget"
    elif ratio >= 1.0 and n_done > 0:
        status = "partial_synthetic_fallback"
    elif ratio > 0:
        status = "partial_fallback"
    else:
        status = "ok"

    notes = ""
    if n_skipped > 0:
        notes = (
            f"Skipped {n_skipped}/{len(positions)} trials to respect "
            f"{budget:.0f}s/cell budget (cumulative runtime was "
            f"{cumulative:.1f}s after trial {n_done})."
        )

    return CellResult(
        slice_id=slice_def.id,
        model_id=model.id,
        n_trials=n_done,
        n_skipped_budget=n_skipped,
        any_fallback=any_fallback,
        fallback_ratio=ratio,
        crps=empirical_crps(outcomes),
        calibration_error_p10_p90=calibration_error_p10_p90(outcomes),
        hit_rate=hit_rate(outcomes),
        runtime=summarise_runtimes(runtimes),
        records=records,
        status=status,
        notes=notes,
    )


# ---------------------------------------------------------------------------
# Artefact writer
# ---------------------------------------------------------------------------

def _git_sha() -> str:
    """Short git SHA, or ``unknown`` outside a checkout."""
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


def write_cell_artefact(result: CellResult, output_dir: Path) -> Path:
    """Serialize one CellResult to ``<slice>-<model>.json``.

    Per-cell JSON is the primary machine-readable artefact; the markdown
    report consolidates these for humans.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{result.slice_id}-{result.model_id}.json"
    payload = {
        "metadata": {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "git_sha": _git_sha(),
            "benchmark_id": "foundation-bench-v1",
        },
        "result": result.to_dict(include_trials=True),
    }
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, default=_json_default)
    return path


def _json_default(obj):
    """Fallback encoder for numpy scalar types that ``json`` can't handle."""
    if isinstance(obj, (np.floating,)):
        return float(obj)
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.ndarray,)):
        return obj.tolist()
    raise TypeError(f"Cannot serialise {type(obj).__name__} to JSON")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser.

    Exposed separately so unit tests can exercise the parser without
    invoking ``main``.
    """
    parser = argparse.ArgumentParser(
        description="Walk-forward foundation-model bench (TimesFM/Chronos/"
        "Moirai/MOMENT + wavelet baseline)."
    )
    parser.add_argument("--slices-spec", default=str(DEFAULT_SPEC_SLICES),
                        help="Path to slices.yaml")
    parser.add_argument("--models-spec", default=str(DEFAULT_SPEC_MODELS),
                        help="Path to models.yaml")
    parser.add_argument("--data-root", default=str(DEFAULT_DATA_ROOT),
                        help="Directory containing stocks/ and crypto/ subfolders")
    parser.add_argument("--slice", dest="slice_ids", action="append", default=[],
                        help="Slice id to include (may be repeated).")
    parser.add_argument("--slices", dest="slice_csv", default=None,
                        help="Comma-separated slice ids (alternative to repeated --slice).")
    parser.add_argument("--model", dest="model_ids", action="append", default=[],
                        help="Model id to include (may be repeated).")
    parser.add_argument("--seed", type=int, default=None,
                        help="Single seed override (default: spec.seeds).")
    parser.add_argument("--smoke", action="store_true",
                        help="Use spec.n_trials_smoke instead of spec.n_trials.")
    parser.add_argument("--n-trials", type=int, default=None,
                        help="Override trial count (useful for budget-capped sweeps).")
    parser.add_argument("--per-cell-budget-seconds", type=float, default=None,
                        help="Override spec.per_cell_budget_seconds.")
    parser.add_argument("--reports-dir", default=str(REPORTS_DIR),
                        help="Directory for per-cell JSON artefacts.")
    parser.add_argument("--report-md", default=str(REPORT_MD),
                        help="Path to consolidated markdown report.")
    parser.add_argument("--skip-ledger", action="store_true",
                        help="Do not append a row to experiments.jsonl.")
    parser.add_argument("--skip-report", action="store_true",
                        help="Do not write the markdown report.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    spec = load_spec(args.slices_spec, args.models_spec)
    data_root = Path(args.data_root).resolve()
    reports_dir = Path(args.reports_dir).resolve()

    # Slice / model filters
    slice_filter: set[str] | None
    if args.slice_csv:
        slice_filter = {s.strip() for s in args.slice_csv.split(",") if s.strip()}
    elif args.slice_ids:
        slice_filter = set(args.slice_ids)
    else:
        slice_filter = None
    model_filter = set(args.model_ids) if args.model_ids else None

    slices = [s for s in spec.slices if slice_filter is None or s.id in slice_filter]
    models = [m for m in spec.models if model_filter is None or m.id in model_filter]
    if not slices or not models:
        parser.error("No slices or models selected — check --slice / --model filters.")

    seeds = [args.seed] if args.seed is not None else spec.seeds
    if args.n_trials is not None:
        n_trials = int(args.n_trials)
    elif args.smoke:
        n_trials = spec.n_trials_smoke
    else:
        n_trials = spec.n_trials

    if args.per_cell_budget_seconds is not None:
        spec.per_cell_budget_seconds = float(args.per_cell_budget_seconds)

    print(f"[foundation-bench] spec={spec.id}  slices={len(slices)}  models={len(models)}")
    print(
        f"[foundation-bench] n_trials={n_trials}  seeds={seeds}  "
        f"budget={spec.per_cell_budget_seconds:.0f}s/cell  data_root={data_root}"
    )

    all_cells: list[CellResult] = []
    artefacts: list[Path] = []
    for slice_def in slices:
        print(f"\n[slice] {slice_def.id} ({slice_def.regime})")
        try:
            values = load_slice_values(slice_def, data_root)
        except FileNotFoundError as err:
            print(f"  [skip] {err}")
            continue
        print(f"  loaded {len(values)} bars "
              f"({slice_def.start_date} → {slice_def.end_date})")

        for seed in seeds:
            positions = sample_trial_positions(
                n_points=len(values),
                window=spec.query_window,
                forward_bars=spec.forward_bars,
                n_trials=n_trials,
                seed=seed,
                min_lookback_multiplier=spec.min_lookback_multiplier,
            )
            for model in models:
                label = f"{slice_def.id}  model={model.id}  seed={seed}  n={len(positions)}"
                print(f"  [cell] {label}")
                cell = evaluate_cell(slice_def, model, values, positions, spec, seed)
                # Per-seed disambiguation
                if len(seeds) > 1:
                    cell.slice_id = f"{slice_def.id}_seed{seed}"
                art = write_cell_artefact(cell, reports_dir)
                artefacts.append(art)
                try:
                    art_label = art.relative_to(REPO_ROOT)
                except ValueError:
                    art_label = art  # pragma: no cover — tmp dir in tests
                print(
                    f"    n={cell.n_trials} skipped={cell.n_skipped_budget} "
                    f"crps={cell.crps:.4f} cal={cell.calibration_error_p10_p90:.3f} "
                    f"hit={cell.hit_rate:.2f} rt_med={cell.runtime['median']:.3f}s "
                    f"status={cell.status} -> {art_label}"
                )
                all_cells.append(cell)

    # --- Consolidated markdown report -------------------------------------
    if not args.skip_report and all_cells:
        from research.autoresearch.foundation_bench.report import write_markdown_report

        md_path = Path(args.report_md).resolve()
        write_markdown_report(
            all_cells,
            md_path,
            benchmark_id=spec.id,
            n_trials=n_trials,
            seeds=seeds,
            git_sha=_git_sha(),
            per_cell_budget_seconds=spec.per_cell_budget_seconds,
        )
        try:
            md_label = md_path.relative_to(REPO_ROOT)
        except ValueError:
            md_label = md_path
        print(f"\n[report] wrote {md_label}")

    # --- Ledger append ----------------------------------------------------
    if not args.skip_ledger and all_cells:
        from research.autoresearch.foundation_bench.ledger import (
            append_ledger_entry,
            build_ledger_entry,
        )

        md_resolved = Path(args.report_md).resolve()
        try:
            art_str = str(md_resolved.relative_to(REPO_ROOT))
        except ValueError:
            art_str = str(md_resolved)
        entry = build_ledger_entry(
            all_cells,
            benchmark_id=spec.id,
            artefacts=[art_str],
            n_trials=n_trials,
            seeds=seeds,
        )
        append_ledger_entry(entry, LEDGER_PATH)
        try:
            ledger_label = LEDGER_PATH.relative_to(REPO_ROOT)
        except ValueError:
            ledger_label = LEDGER_PATH
        print(f"[ledger] appended to {ledger_label}  status={entry['status']}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
