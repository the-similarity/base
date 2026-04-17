"""Batch CLI runner for the synthetic pipeline.

Invoke as ``python -m the_similarity.synthetic.cli``. Loads a source series,
fits a generator, samples ``n`` synthetic rows, runs Fidelity / Privacy /
Utility scorecards, and writes artifacts (real/synth parquet, scorecard.json,
report.md, provenance.json) under a run directory keyed by
``<generator>-<seed>-<YYYYMMDD-HHMMSS>``.

Exit code
---------
- ``0`` (default / loose mode) whenever artifacts are successfully written,
  regardless of scorecard pass/fail. The scorecard outcome is surfaced in
  stdout as ``passed=True|False`` for programmatic consumers.
- ``1`` only when ``--strict`` is passed AND at least one scorecard fails
  its threshold. Lets callers opt into treating scorecard miss as a
  pipeline failure without making it the default.
- ``2`` reserved for argparse/pipeline errors (argparse emits this
  automatically on bad CLI args; pipeline exceptions surface as non-zero
  via Python's default ``SystemExit``).
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from the_similarity.synthetic.contracts import (
    FidelityReport,
    PrivacyReport,
    Provenance,
    Scorecard,
    SyntheticDataset,
    UtilityReport,
    iso_now,
)

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------


GENERATOR_CHOICES = ("block_bootstrap", "regime_block_bootstrap")


def build_parser() -> argparse.ArgumentParser:
    """Construct the argparse parser for the batch CLI.

    Exposed at module scope so tests can exercise parsing without invoking
    :func:`main` or touching the filesystem.
    """
    p = argparse.ArgumentParser(
        prog="python -m the_similarity.synthetic.cli",
        description=(
            "Run the synthetic-data pipeline: load source -> fit generator -> "
            "sample -> score fidelity/privacy/utility -> write artifacts."
        ),
    )
    p.add_argument(
        "--input",
        required=True,
        type=Path,
        help="Path to source data (.csv or .parquet). Rows are timesteps.",
    )
    p.add_argument(
        "--n",
        required=True,
        type=int,
        help="Number of synthetic rows (timesteps) to generate.",
    )
    p.add_argument(
        "--seed",
        type=int,
        default=0,
        help="RNG seed for reproducible sampling (default: 0).",
    )
    p.add_argument(
        "--generator",
        choices=GENERATOR_CHOICES,
        default="block_bootstrap",
        help="Which generator to use (default: block_bootstrap).",
    )
    p.add_argument(
        "--out",
        required=True,
        type=Path,
        help="Output root directory. A run subdir is created under it.",
    )
    p.add_argument(
        "--threshold-fidelity",
        type=float,
        default=None,
        help=(
            "Optional. Minimum FidelityReport.overall_score; thresholds used "
            "for the `passed` banner and for `--strict` exit gating."
        ),
    )
    p.add_argument(
        "--threshold-privacy",
        type=float,
        default=None,
        help=(
            "Optional. Minimum PrivacyReport.overall_score; thresholds used "
            "for the `passed` banner and for `--strict` exit gating."
        ),
    )
    p.add_argument(
        "--threshold-utility",
        type=float,
        default=None,
        help=(
            "Optional. Maximum UtilityReport.transfer_gap (lower = better); "
            "thresholds used for the `passed` banner and for `--strict` "
            "exit gating."
        ),
    )
    p.add_argument(
        "--strict",
        action="store_true",
        default=False,
        help=(
            "If set, exit 1 when any scorecard fails its threshold. "
            "By default, exit 0 on successful artifact write regardless "
            "of scorecard pass/fail."
        ),
    )
    p.add_argument(
        "--register",
        action="store_true",
        default=False,
        help=(
            "If set, register the resulting run in the platform registry via "
            "the_similarity.platform.adapters.copies.register_copies_run. "
            "Off by default for backward compatibility — opting in writes a "
            "row to $THE_SIMILARITY_REGISTRY_DB (or "
            "~/.the_similarity/registry.db) and also emits artifact.json "
            "inside the run dir."
        ),
    )
    return p


# ---------------------------------------------------------------------------
# I/O helpers
# ---------------------------------------------------------------------------


def load_source(path: Path) -> "Any":
    """Load a .csv or .parquet file into a pandas DataFrame.

    pandas is a first-party dep (see pyproject.toml); importing here keeps
    the module import cheap for tools that only parse ``--help``.
    """
    import pandas as pd

    suffix = path.suffix.lower()
    if suffix == ".csv":
        return pd.read_csv(path)
    if suffix in (".parquet", ".pq"):
        return pd.read_parquet(path)
    raise ValueError(f"Unsupported input suffix {suffix!r}; use .csv or .parquet")


def run_dir_name(generator: str, seed: int, now: Optional[datetime] = None) -> str:
    """Canonical run-directory name: ``<generator>-<seed>-<YYYYMMDD-HHMMSS>``.

    UTC timestamp, seconds resolution. ``now`` is injectable so tests can
    pin a deterministic value.
    """
    ts = (now or datetime.now(timezone.utc)).strftime("%Y%m%d-%H%M%S")
    return f"{generator}-{seed}-{ts}"


# ---------------------------------------------------------------------------
# Lazy imports for parallel-PR dependencies
# ---------------------------------------------------------------------------


_MISSING_DEPS_MSG = (
    "Synthetic pipeline dependency not found: {name}. "
    "Run after dependent PRs merge (generator/fidelity/privacy/utility)."
)


def build_generator(name: str) -> "Any":
    """Resolve a generator name to an instantiated generator object.

    Imports are deferred so this module stays importable even when sibling
    PRs have not yet landed -- the failure surfaces as a clear message at
    pipeline run time rather than at ``python -m`` load time.
    """
    try:
        # Standard names agreed with the sibling generator agent.
        from the_similarity.synthetic.copies import (  # type: ignore[import-not-found]
            BlockBootstrapGenerator,
            RegimeBlockBootstrapGenerator,
        )
    except ImportError as exc:  # pragma: no cover - exercised only before merge
        raise RuntimeError(_MISSING_DEPS_MSG.format(name="generators")) from exc

    if name == "block_bootstrap":
        return BlockBootstrapGenerator()
    if name == "regime_block_bootstrap":
        return RegimeBlockBootstrapGenerator()
    raise ValueError(f"Unknown generator {name!r}")


def run_scorecards(
    real: SyntheticDataset, synth: SyntheticDataset
) -> (
    "tuple[Optional[FidelityReport], Optional[PrivacyReport], Optional[UtilityReport]]"
):
    """Run Fidelity/Privacy/Utility scorecards, tolerating missing siblings.

    Each scorecard is imported and executed independently so one missing
    dependency does not cascade -- the returned tuple has ``None`` for any
    scorecard whose implementation is not yet available.
    """
    fidelity: Optional[FidelityReport] = None
    privacy: Optional[PrivacyReport] = None
    utility: Optional[UtilityReport] = None

    try:
        from the_similarity.synthetic.fidelity import (  # type: ignore[import-not-found]
            FidelityScorecard,
        )

        fidelity = FidelityScorecard().evaluate(real, synth)
    except ImportError:
        print(_MISSING_DEPS_MSG.format(name="fidelity"), file=sys.stderr)

    try:
        from the_similarity.synthetic.privacy import (  # type: ignore[import-not-found]
            PrivacyScorecard,
        )

        privacy = PrivacyScorecard().evaluate(real, synth)
    except ImportError:
        print(_MISSING_DEPS_MSG.format(name="privacy"), file=sys.stderr)

    try:
        from the_similarity.synthetic.utility import (  # type: ignore[import-not-found]
            UtilityScorecard,
        )

        utility = UtilityScorecard().evaluate(real, synth)
    except ImportError:
        print(_MISSING_DEPS_MSG.format(name="utility"), file=sys.stderr)

    return fidelity, privacy, utility


# ---------------------------------------------------------------------------
# Writers
# ---------------------------------------------------------------------------


def _df_from_dataset(ds: SyntheticDataset) -> "Any":
    """Coerce a SyntheticDataset to a pandas DataFrame for parquet output.

    Accepts both numpy arrays and DataFrames -- the contract explicitly
    allows either. Numpy arrays use ``ds.columns`` when provided, otherwise
    falls back to positional ``col_<i>`` names.
    """
    import numpy as np
    import pandas as pd

    if isinstance(ds.data, pd.DataFrame):
        return ds.data
    arr = np.asarray(ds.data)
    if arr.ndim == 1:
        arr = arr.reshape(-1, 1)
    cols = ds.columns or [f"col_{i}" for i in range(arr.shape[1])]
    return pd.DataFrame(arr, columns=cols, index=ds.index)


def write_parquets(
    run_dir: Path, real: SyntheticDataset, synth: SyntheticDataset
) -> None:
    """Persist real and synthetic datasets side-by-side as parquet.

    We always materialize real too (instead of a path reference) so a run
    dir is self-contained for downstream auditing -- the source file may
    move or be rewritten between the run and any later review.
    """
    _df_from_dataset(real).to_parquet(run_dir / "real.parquet", index=False)
    _df_from_dataset(synth).to_parquet(run_dir / "synth.parquet", index=False)


def _scorecard_to_dict(sc: Scorecard) -> dict[str, Any]:
    """Serialize a Scorecard to a JSON-safe dict.

    ``SyntheticDataset.data`` is large and not JSON-serializable, so the
    embedded dataset is reduced to provenance + shape metadata -- the raw
    payload lives in ``synth.parquet`` alongside.
    """
    import numpy as np
    import pandas as pd

    ds = sc.dataset
    if isinstance(ds.data, pd.DataFrame):
        shape = list(ds.data.shape)
    else:
        arr = np.asarray(ds.data)
        shape = list(arr.shape)

    return {
        "dataset": {
            "shape": shape,
            "columns": ds.columns,
            "provenance": dataclasses.asdict(ds.provenance) if ds.provenance else None,
        },
        "fidelity": dataclasses.asdict(sc.fidelity) if sc.fidelity else None,
        "privacy": dataclasses.asdict(sc.privacy) if sc.privacy else None,
        "utility": dataclasses.asdict(sc.utility) if sc.utility else None,
        "passed": sc.passed,
    }


def write_scorecard(run_dir: Path, scorecard: Scorecard) -> None:
    """Write ``scorecard.json`` -- the machine-readable evaluation record."""
    payload = _scorecard_to_dict(scorecard)
    (run_dir / "scorecard.json").write_text(json.dumps(payload, indent=2, default=str))


def write_provenance(run_dir: Path, provenance: Provenance) -> None:
    """Write ``provenance.json`` -- standalone reproducibility record.

    Duplicated from scorecard.json by design: provenance is the single most
    important audit artifact and consumers should not have to parse the
    full scorecard to reach it.
    """
    (run_dir / "provenance.json").write_text(
        json.dumps(dataclasses.asdict(provenance), indent=2, default=str)
    )


# ---------------------------------------------------------------------------
# Human-readable report
# ---------------------------------------------------------------------------


def _render_metric_block(title: str, metrics: dict[str, float]) -> list[str]:
    """Markdown bullet list for a single metric dict; collapses empties."""
    if not metrics:
        return [f"- **{title}**: _(none)_"]
    lines = [f"- **{title}**:"]
    for k, v in metrics.items():
        lines.append(f"  - `{k}`: {v}")
    return lines


def render_report(scorecard: Scorecard, provenance: Provenance) -> str:
    """Build the ``report.md`` body from a Scorecard + Provenance.

    Pure string construction -- no filesystem side effects -- so tests can
    assert on the rendered text directly.
    """
    lines: list[str] = []
    lines.append(f"# Synthetic run report -- {provenance.generator_name}")
    lines.append("")
    lines.append(f"- source: `{provenance.source_id}`")
    lines.append(
        f"- generator: `{provenance.generator_name}` v{provenance.generator_version}"
    )
    lines.append(f"- seed: `{provenance.seed}`")
    lines.append(f"- created_at: `{provenance.created_at}`")
    lines.append(f"- **overall passed: {scorecard.passed}**")
    lines.append("")

    if scorecard.fidelity is not None:
        f = scorecard.fidelity
        lines.append("## Fidelity")
        lines.append(f"- overall_score: `{f.overall_score}` -- passed: `{f.passed}`")
        lines.extend(_render_metric_block("marginals", f.marginals))
        lines.extend(_render_metric_block("temporal", f.temporal))
        lines.extend(_render_metric_block("tails", f.tails))
        if f.cross_series:
            lines.extend(_render_metric_block("cross_series", f.cross_series))
        lines.append("")

    if scorecard.privacy is not None:
        p = scorecard.privacy
        lines.append("## Privacy")
        lines.append(f"- overall_score: `{p.overall_score}` -- passed: `{p.passed}`")
        lines.extend(_render_metric_block("nn_leakage", p.nn_leakage))
        lines.extend(_render_metric_block("memorization", p.memorization))
        lines.extend(_render_metric_block("membership_proxy", p.membership_proxy))
        lines.append("")

    if scorecard.utility is not None:
        u = scorecard.utility
        lines.append("## Utility")
        lines.append(f"- transfer_gap: `{u.transfer_gap}` -- passed: `{u.passed}`")
        lines.extend(_render_metric_block("trts", u.trts))
        lines.extend(_render_metric_block("tstr", u.tstr))
        lines.extend(_render_metric_block("real_baseline", u.real_baseline))
        lines.append("")

    return "\n".join(lines) + "\n"


def write_report(run_dir: Path, scorecard: Scorecard, provenance: Provenance) -> None:
    """Render and persist ``report.md``."""
    (run_dir / "report.md").write_text(render_report(scorecard, provenance))


# ---------------------------------------------------------------------------
# Pass/fail gate
# ---------------------------------------------------------------------------


def evaluate_thresholds(scorecard: Scorecard, args: argparse.Namespace) -> bool:
    """Return True iff all scorecards passed AND CLI thresholds are satisfied.

    Semantics:
    - Fidelity / Privacy: require ``overall_score >= threshold``.
    - Utility: require ``transfer_gap <= threshold`` (lower is better).
    A threshold set for a scorecard that was not produced is a failure --
    the caller asked for a gate we cannot evaluate.
    """
    if not scorecard.passed:
        return False

    if args.threshold_fidelity is not None:
        if scorecard.fidelity is None:
            return False
        if scorecard.fidelity.overall_score < args.threshold_fidelity:
            return False

    if args.threshold_privacy is not None:
        if scorecard.privacy is None:
            return False
        if scorecard.privacy.overall_score < args.threshold_privacy:
            return False

    if args.threshold_utility is not None:
        if scorecard.utility is None:
            return False
        if scorecard.utility.transfer_gap > args.threshold_utility:
            return False

    return True


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------


def _real_provenance(source_id: str) -> Provenance:
    """Provenance record for the real (input) dataset.

    ``generator_name="real"`` is the contract convention for non-synthetic
    data; seed/version are placeholders since real data has no sampler.
    """
    return Provenance(
        source_id=source_id,
        generator_name="real",
        generator_version="0",
        seed=0,
        created_at=iso_now(),
    )


def run(args: argparse.Namespace) -> int:
    """End-to-end: load -> fit -> sample -> score -> write. Returns exit code.

    Each stage is a pure function call -- failures propagate so the CLI
    never writes a partial run directory. The run dir is created only
    after the generator has produced a dataset.
    """
    df = load_source(args.input)
    source_id = args.input.stem

    real = SyntheticDataset(
        data=df,
        columns=list(df.columns),
        provenance=_real_provenance(source_id),
    )

    generator = build_generator(args.generator)
    generator.fit(real)
    synth = generator.sample(args.n, seed=args.seed)

    # Backfill provenance if the generator did not populate it -- CLI
    # callers rely on it for auditing and report rendering.
    if synth.provenance is None:
        synth = SyntheticDataset(
            data=synth.data,
            index=synth.index,
            columns=synth.columns,
            provenance=Provenance(
                source_id=source_id,
                generator_name=getattr(generator, "name", args.generator),
                generator_version=getattr(generator, "version", "0"),
                seed=args.seed,
                created_at=iso_now(),
            ),
        )

    fidelity, privacy, utility = run_scorecards(real, synth)
    scorecard = Scorecard(
        dataset=synth, fidelity=fidelity, privacy=privacy, utility=utility
    )

    run_dir = args.out / run_dir_name(args.generator, args.seed)
    run_dir.mkdir(parents=True, exist_ok=True)

    write_parquets(run_dir, real, synth)
    write_scorecard(run_dir, scorecard)
    write_provenance(run_dir, synth.provenance)
    write_report(run_dir, scorecard, synth.provenance)

    # Opt-in platform registration. Kept behind a flag so the CLI's
    # default behavior is byte-identical to what pre-registry callers got.
    # Import is deferred to the flag branch so the CLI doesn't gain an
    # unconditional import of the registry (sqlite3 is cheap but the
    # adapter package is layered above CLI).
    if getattr(args, "register", False):
        try:
            from the_similarity.platform.adapters.copies import (
                register_copies_run,
            )

            run_id = register_copies_run(
                run_dir,
                source_id=source_id,
                n=args.n,
                seed=args.seed,
                generator=args.generator,
            )
            print(f"registry run_id: {run_id}")
        except (
            ImportError
        ) as exc:  # pragma: no cover - platform package always ships today
            # We prefer a loud warning over a silent skip: the user asked
            # for registration and the platform package is missing. The
            # run itself still succeeded, so we don't raise.
            print(
                f"warning: --register requested but platform adapter unavailable: {exc}",
                file=sys.stderr,
            )

    passed = evaluate_thresholds(scorecard, args)
    print(f"run_dir: {run_dir}")
    # Exit-semantics contract:
    #   Default (loose): artifact write is the success criterion. The
    #   `passed` flag is informational -- we print it but exit 0 so that
    #   CI pipelines that chain artifact-producing steps don't treat a
    #   soft scorecard miss as a pipeline failure.
    #   --strict: the caller has opted into treating scorecard miss as
    #   a failure; propagate `passed` into the exit code.
    if args.strict:
        exit_code = 0 if passed else 1
        print(f"passed={passed} strict-mode exit={exit_code}")
        return exit_code
    print(f"passed={passed} (use --strict to gate exit code on this)")
    return 0


def main(argv: Optional[list[str]] = None) -> int:
    """CLI entry point. Returns a process exit code.

    Dispatches to the catalog subcommand handler when the first argument
    is ``"catalog"``, otherwise falls through to the original pipeline
    parser. This two-layer dispatch preserves backward compatibility: the
    existing ``python -m the_similarity.synthetic.cli --input ...`` invocation
    continues to work unchanged.
    """
    effective_argv = argv if argv is not None else sys.argv[1:]

    # Dispatch to catalog subcommands when the first positional arg is "catalog"
    if effective_argv and effective_argv[0] == "catalog":
        return _catalog_main(effective_argv[1:])

    parser = build_parser()
    args = parser.parse_args(argv)
    return run(args)


# ---------------------------------------------------------------------------
# Catalog subcommands
# ---------------------------------------------------------------------------


def _catalog_build_parser() -> argparse.ArgumentParser:
    """Build the argparse parser for catalog subcommands.

    Supports three subcommands:
    - ``catalog list`` — list registered synthetic datasets.
    - ``catalog show <dataset_id>`` — print a dataset card.
    - ``catalog register`` — register a synthetic run as a dataset.
    """
    p = argparse.ArgumentParser(
        prog="python -m the_similarity.synthetic.cli catalog",
        description="Manage the synthetic dataset catalog.",
    )
    sub = p.add_subparsers(dest="catalog_cmd")

    # -- catalog list -------------------------------------------------------
    list_p = sub.add_parser("list", help="List registered synthetic datasets.")
    list_p.add_argument(
        "--promoted-only",
        action="store_true",
        default=False,
        help="Only show promoted datasets.",
    )
    list_p.add_argument(
        "--db",
        type=Path,
        default=None,
        help="Path to registry DB (default: $THE_SIMILARITY_REGISTRY_DB or "
        "~/.the_similarity/registry.db).",
    )

    # -- catalog show -------------------------------------------------------
    show_p = sub.add_parser("show", help="Print a dataset card.")
    show_p.add_argument(
        "dataset_id",
        help="The dataset_id to look up.",
    )
    show_p.add_argument(
        "--db",
        type=Path,
        default=None,
        help="Path to registry DB.",
    )

    # -- catalog register ---------------------------------------------------
    reg_p = sub.add_parser("register", help="Register a synthetic run as a dataset.")
    reg_p.add_argument(
        "--run-dir",
        required=True,
        type=Path,
        help="Path to the completed run directory (must contain synth.parquet).",
    )
    reg_p.add_argument(
        "--name",
        required=True,
        help="Human-readable dataset name.",
    )
    reg_p.add_argument(
        "--version",
        default="v1",
        help="Dataset version string (default: v1).",
    )
    reg_p.add_argument(
        "--run-id",
        default=None,
        help="Run ID to embed in source. Generated if omitted.",
    )
    reg_p.add_argument(
        "--no-checksum",
        action="store_true",
        default=False,
        help="Skip SHA-256 checksum computation (faster for large files).",
    )
    reg_p.add_argument(
        "--db",
        type=Path,
        default=None,
        help="Path to registry DB.",
    )

    return p


def _resolve_db(db_arg: Optional[Path]) -> Path:
    """Resolve the registry DB path from CLI arg, env var, or default.

    Priority: CLI ``--db`` > ``$THE_SIMILARITY_REGISTRY_DB`` >
    ``~/.the_similarity/registry.db``.
    """
    import os

    if db_arg is not None:
        return db_arg
    env_val = os.environ.get("THE_SIMILARITY_REGISTRY_DB")
    if env_val:
        return Path(env_val)
    return Path.home() / ".the_similarity" / "registry.db"


def _catalog_main(argv: list[str]) -> int:
    """Dispatch catalog subcommands. Returns exit code."""
    from the_similarity.platform.artifacts import new_run_id as gen_run_id
    from the_similarity.platform.registry import RunRegistry
    from the_similarity.synthetic.catalog import (
        get_dataset_card,
        list_catalog,
        register_synthetic_dataset,
    )

    parser = _catalog_build_parser()
    args = parser.parse_args(argv)

    if args.catalog_cmd is None:
        parser.print_help()
        return 2

    db_path = _resolve_db(getattr(args, "db", None))

    if args.catalog_cmd == "list":
        with RunRegistry(db_path) as registry:
            datasets = list_catalog(
                registry, promoted_only=args.promoted_only
            )
        if not datasets:
            print("No synthetic datasets found.")
            return 0
        for ds in datasets:
            promoted_tag = ""
            if ds.metadata.get("promoted", False):
                promoted_tag = " [promoted]"
            print(
                f"{ds.dataset_id}  {ds.name}  v={ds.version}  "
                f"rows={ds.n_rows}  cols={ds.n_columns}{promoted_tag}"
            )
        return 0

    if args.catalog_cmd == "show":
        with RunRegistry(db_path) as registry:
            try:
                card = get_dataset_card(args.dataset_id, registry)
            except KeyError as exc:
                print(f"Error: {exc}", file=sys.stderr)
                return 1
        print(json.dumps(card, indent=2, default=str))
        return 0

    if args.catalog_cmd == "register":
        run_id = args.run_id or gen_run_id()
        with RunRegistry(db_path) as registry:
            dataset_id = register_synthetic_dataset(
                run_id=run_id,
                name=args.name,
                version=args.version,
                run_dir=args.run_dir,
                registry=registry,
                compute_checksum=not args.no_checksum,
            )
        print(f"registered: {dataset_id}")
        return 0

    parser.print_help()
    return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
