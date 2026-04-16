"""Command-line interface for the run registry — ``python -m the_similarity.platform``.

This is the human / shell-script surface for the registry. It wraps
:class:`~the_similarity.platform.registry.RunRegistry` with argparse and
prints results to stdout in formats that pipe well (run ids on their own
line, JSON for ``show``, tabular for ``list``).

Subcommands
-----------
- ``register <artifact.json>`` — load and register an artifact, print run_id.
- ``list [--kind KIND] [--limit N]`` — newest-first table of runs.
- ``show <run_id>`` — pretty-printed JSON of the full artifact.
- ``compare <run_id_a> <run_id_b>`` — pretty-printed diff dict.

Exit codes
----------
- ``0`` — success.
- ``1`` — runtime error (missing run_id, missing artifact file, etc.).
- ``2`` — argparse error (unrecognized flag, missing positional). This is
  argparse's default and we let it stand so behavior matches every other
  ``python -m`` tool in the repo.

DB path resolution (in order)
-----------------------------
1. ``--db PATH`` global flag, if given.
2. ``THE_SIMILARITY_REGISTRY_DB`` environment variable, if set.
3. Default ``~/.the_similarity/registry.db`` (parent dir auto-created).

The default lives under the user's home so it survives across worktrees and
across project clones — the registry is meant to outlive any single check-out.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Optional, Sequence

from the_similarity.platform.artifacts import RunArtifact, RunKind
from the_similarity.platform.registry import RunRegistry


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

# Environment variable name for overriding the default DB location. Kept as a
# module constant so tests and downstream tooling can reference it without
# hard-coding the string.
ENV_DB_PATH = "THE_SIMILARITY_REGISTRY_DB"

# Default DB path when neither --db nor the env var is set. Under the user's
# home directory so the registry persists across worktrees / project clones.
DEFAULT_DB_PATH = Path("~/.the_similarity/registry.db")


def _resolve_db_path(cli_value: Optional[str]) -> Path:
    """Pick the DB path per the precedence rules documented in the module docstring.

    Centralizing the resolution here means every subcommand reads the same
    rules, and tests can monkeypatch ``ENV_DB_PATH`` without touching argparse.
    """
    if cli_value:
        return Path(cli_value).expanduser()
    env_value = os.environ.get(ENV_DB_PATH)
    if env_value:
        return Path(env_value).expanduser()
    return DEFAULT_DB_PATH.expanduser()


# ---------------------------------------------------------------------------
# Subcommand handlers — each returns an int exit code.
# ---------------------------------------------------------------------------


def _cmd_register(args: argparse.Namespace) -> int:
    """Read an artifact.json, register it, print the run_id on stdout."""
    artifact_path = Path(args.artifact).expanduser()
    if not artifact_path.exists():
        # Print to stderr so callers piping stdout into a `xargs run_id` chain
        # do not silently consume the error message as input.
        print(f"error: artifact file not found: {artifact_path}", file=sys.stderr)
        return 1
    payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    artifact = RunArtifact.from_dict(payload)
    with RunRegistry(_resolve_db_path(args.db)) as registry:
        run_id = registry.register(artifact)
    # Print the run_id on its own line — convention so shell pipelines like
    # `python -m the_similarity.platform register a.json | xargs ...` work.
    print(run_id)
    return 0


def _cmd_list(args: argparse.Namespace) -> int:
    """Print a tabular newest-first listing of runs, optionally filtered by kind."""
    kind_filter: Optional[RunKind] = RunKind(args.kind) if args.kind else None
    with RunRegistry(_resolve_db_path(args.db)) as registry:
        rows = registry.list(kind=kind_filter, limit=args.limit)

    if not rows:
        # Empty result is not an error — exit 0, no output. Lets shell
        # callers test with `[ -z "$(... list)" ]`.
        return 0

    # Tabular output. We do not pull in a tabulate dependency — a single
    # f-string with column widths is enough and keeps the CLI stdlib-only.
    # Columns: run_id (8 char prefix), kind, seed, created_at, summary-head.
    # The 8-char run_id prefix matches `git log --oneline` ergonomics; the
    # full id is available via `show`.
    header = f"{'RUN_ID':<10} {'KIND':<8} {'SEED':<8} {'CREATED_AT':<22} SUMMARY"
    print(header)
    print("-" * len(header))
    for artifact in rows:
        # `summary-head` is a single-line preview of the summary dict —
        # truncated at 60 chars so the row stays terminal-friendly. The
        # full summary is available via `show` and `compare`.
        summary_preview = json.dumps(artifact.summary, separators=(",", ":"))
        if len(summary_preview) > 60:
            summary_preview = summary_preview[:57] + "..."
        seed_str = "-" if artifact.seed is None else str(artifact.seed)
        print(
            f"{artifact.run_id[:8]:<10} {artifact.kind.value:<8} "
            f"{seed_str:<8} {artifact.created_at:<22} {summary_preview}"
        )
    return 0


def _cmd_show(args: argparse.Namespace) -> int:
    """Pretty-print the full artifact JSON for one run_id."""
    with RunRegistry(_resolve_db_path(args.db)) as registry:
        artifact = registry.get(args.run_id)
    if artifact is None:
        print(f"error: run_id not found: {args.run_id}", file=sys.stderr)
        return 1
    # 2-space indent matches `write_artifact` on the artifacts module so the
    # output is byte-comparable to the on-disk representation.
    print(json.dumps(artifact.to_dict(), indent=2, sort_keys=False))
    return 0


def _cmd_compare(args: argparse.Namespace) -> int:
    """Pretty-print the summary diff between two runs."""
    with RunRegistry(_resolve_db_path(args.db)) as registry:
        try:
            result = registry.compare(args.run_id_a, args.run_id_b)
        except KeyError as exc:
            print(f"error: {exc.args[0]}", file=sys.stderr)
            return 1
    # The diff dict's tuple values are not JSON-serializable directly —
    # convert to lists so the output is valid JSON that downstream tools
    # (jq pipelines) can parse.
    serializable = {
        "a": result["a"],
        "b": result["b"],
        "diff": {k: list(v) for k, v in result["diff"].items()},
    }
    print(json.dumps(serializable, indent=2, sort_keys=False))
    return 0


# ---------------------------------------------------------------------------
# Argparse wiring
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    """Construct the top-level parser with one subparser per command.

    Kept as a separate function so tests can introspect the parser without
    invoking ``main()``.
    """
    parser = argparse.ArgumentParser(
        prog="python -m the_similarity.platform",
        description="Run registry — register, list, show, and compare platform runs.",
    )
    parser.add_argument(
        "--db",
        default=None,
        help=(
            "Path to the registry SQLite file. "
            f"Defaults to ${ENV_DB_PATH} or {DEFAULT_DB_PATH} if unset."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_register = sub.add_parser("register", help="Register an artifact.json file.")
    p_register.add_argument("artifact", help="Path to a RunArtifact JSON file.")
    p_register.set_defaults(func=_cmd_register)

    p_list = sub.add_parser("list", help="List runs newest-first.")
    p_list.add_argument(
        "--kind",
        choices=[k.value for k in RunKind],
        default=None,
        help="Filter by run kind.",
    )
    p_list.add_argument(
        "--limit", type=int, default=100, help="Maximum number of rows (default 100)."
    )
    p_list.set_defaults(func=_cmd_list)

    p_show = sub.add_parser("show", help="Print the full artifact for one run_id.")
    p_show.add_argument("run_id", help="The run_id to show.")
    p_show.set_defaults(func=_cmd_show)

    p_compare = sub.add_parser("compare", help="Diff the summaries of two runs.")
    p_compare.add_argument("run_id_a", help="First run_id.")
    p_compare.add_argument("run_id_b", help="Second run_id.")
    p_compare.set_defaults(func=_cmd_compare)

    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Module entry point. Returns an exit code; ``argv`` defaults to ``sys.argv[1:]``."""
    parser = _build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":  # pragma: no cover - thin wrapper
    raise SystemExit(main())
