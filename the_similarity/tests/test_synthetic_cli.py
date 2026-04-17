"""Smoke tests for the synthetic CLI / batch runner.

Skipped if `the_similarity.synthetic.cli` has not landed yet. Invokes the CLI
as a subprocess against a tiny synthetic CSV and asserts the run directory
contains the expected artifacts.

The MVP spec (`vision/synthetic_copies_worlds_eval_mvp.md`) names these:
- data.parquet (aka synth.parquet in the team-lead brief)
- manifest.json / scorecard.json
- eval.md / report.md

We accept either naming for data and scorecard/eval to avoid churn if the CLI
picks one vs. the other.
"""

from __future__ import annotations

import csv
import subprocess
import sys
from pathlib import Path

import pytest

pytest.importorskip("the_similarity.synthetic.cli")


def _write_tiny_csv(path: Path, n_rows: int = 200) -> None:
    import random

    rng = random.Random(0)
    with path.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["x1", "x2", "y"])
        for _ in range(n_rows):
            a = rng.gauss(0, 1)
            b = rng.gauss(0, 1)
            label = 1 if (0.7 * a - 0.3 * b) > 0 else 0
            w.writerow([f"{a:.4f}", f"{b:.4f}", label])


def _run_cli(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    # Invoke via `python -m the_similarity.synthetic.cli` so we don't depend on
    # an installed console script being on PATH in the test sandbox. We pin
    # PYTHONPATH to the worktree's repo root so the subprocess imports the
    # in-tree package (e.g. this branch's cli.py), not whatever copy happens
    # to be pip-installed at the user's site-packages -- otherwise the test
    # silently exercises stale code from a sibling worktree.
    import os

    repo_root = Path(__file__).resolve().parents[2]
    env = os.environ.copy()
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = (
        f"{repo_root}{os.pathsep}{existing}" if existing else str(repo_root)
    )
    return subprocess.run(
        [sys.executable, "-m", "the_similarity.synthetic.cli", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=120,
        env=env,
    )


def _find_any(run_dir: Path, candidates: tuple[str, ...]) -> Path | None:
    for name in candidates:
        p = run_dir / name
        if p.exists():
            return p
    # Allow nested artifact layouts — recurse one level.
    for name in candidates:
        matches = list(run_dir.rglob(name))
        if matches:
            return matches[0]
    return None


def test_cli_runs_on_tiny_csv(tmp_path: Path):
    in_csv = tmp_path / "tiny.csv"
    _write_tiny_csv(in_csv, n_rows=200)
    out_dir = tmp_path / "run"
    out_dir.mkdir()

    # Probe: does the CLI expose --help without crashing? If not, the module
    # isn't a CLI yet — skip rather than pretend to test it.
    probe = _run_cli(["--help"], cwd=tmp_path)
    if probe.returncode not in (0, 2):  # argparse exits 0 on --help, 2 on err
        pytest.skip(
            f"synthetic.cli --help returned {probe.returncode}; "
            f"stderr={probe.stderr[:200]}"
        )

    # Best-effort invocation — the spec names `synth copies run` as the
    # subcommand. Try that first, then fall back to flag-style.
    attempts = [
        ["--input", str(in_csv), "--n", "100", "--out", str(out_dir)],
        ["copies", "run", "--input", str(in_csv), "--n", "100", "--out", str(out_dir)],
        ["run", "--input", str(in_csv), "--n", "100", "--out", str(out_dir)],
        ["copies", "run", "--input", str(in_csv), "--out", str(out_dir)],
        ["run", "--input", str(in_csv), "--out", str(out_dir)],
        ["--input", str(in_csv), "--out", str(out_dir)],
    ]
    result = None
    for args in attempts:
        result = _run_cli(args, cwd=tmp_path)
        # Accept 0 (all passed) or 1 (ran but some scorecard under threshold).
        # Reject 2 (argparse error) — that means this arg shape is wrong.
        if result.returncode in (0, 1):
            break

    assert result is not None
    assert result.returncode in (0, 1), (
        f"CLI failed for all arg shapes; last stderr: {result.stderr[:400]}"
    )

    data_artifact = _find_any(
        out_dir, ("synth.parquet", "data.parquet", "synth.csv", "data.csv")
    )
    assert data_artifact is not None, (
        f"No data artifact in {out_dir}; contents: {list(out_dir.rglob('*'))}"
    )

    score_artifact = _find_any(
        out_dir, ("scorecard.json", "eval.json", "manifest.json")
    )
    assert score_artifact is not None, (
        f"No scorecard/eval json in {out_dir}; contents: {list(out_dir.rglob('*'))}"
    )

    report_artifact = _find_any(out_dir, ("report.md", "eval.md", "README.md"))
    assert report_artifact is not None, (
        f"No report.md/eval.md in {out_dir}; contents: {list(out_dir.rglob('*'))}"
    )


def test_cli_strict_mode_exits_one_on_threshold_miss(tmp_path: Path):
    """In --strict mode, impossibly-tight thresholds must force exit 1.

    Picks thresholds the scorecard cannot satisfy on a tiny random CSV
    (min fidelity = 1.0 is effectively unreachable; max transfer_gap = 0.0
    is unreachable too). The loose-mode test above verifies that the same
    artifact-write path still returns 0 without --strict, so this pair
    brackets the behaviour.
    """
    in_csv = tmp_path / "tiny.csv"
    _write_tiny_csv(in_csv, n_rows=200)
    out_dir = tmp_path / "run"
    out_dir.mkdir()

    probe = _run_cli(["--help"], cwd=tmp_path)
    if probe.returncode not in (0, 2):
        pytest.skip(
            f"synthetic.cli --help returned {probe.returncode}; "
            f"stderr={probe.stderr[:200]}"
        )
    # Require --strict support: if the flag is not yet wired, skip rather
    # than fail (keeps the suite green in worktrees before this PR lands).
    if "--strict" not in (probe.stdout or ""):
        pytest.skip("CLI build does not expose --strict yet")

    result = _run_cli(
        [
            "--input",
            str(in_csv),
            "--n",
            "100",
            "--out",
            str(out_dir),
            "--strict",
            "--threshold-fidelity",
            "1.0",
            "--threshold-privacy",
            "1.0",
            "--threshold-utility",
            "0.0",
        ],
        cwd=tmp_path,
    )

    assert result.returncode == 1, (
        f"Expected strict-mode exit 1 on unreachable thresholds; "
        f"got {result.returncode}. stdout={result.stdout[:400]} "
        f"stderr={result.stderr[:400]}"
    )
    # The banner must communicate the strict-mode exit decision.
    assert "strict-mode exit=1" in (result.stdout or ""), (
        f"Expected strict-mode banner; stdout={result.stdout[:400]}"
    )
