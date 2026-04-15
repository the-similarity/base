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
    # an installed console script being on PATH in the test sandbox.
    return subprocess.run(
        [sys.executable, "-m", "the_similarity.synthetic.cli", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=120,
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
        ["copies", "run", "--input", str(in_csv), "--out", str(out_dir)],
        ["run", "--input", str(in_csv), "--out", str(out_dir)],
        ["--input", str(in_csv), "--out", str(out_dir)],
    ]
    result = None
    for args in attempts:
        result = _run_cli(args, cwd=tmp_path)
        if result.returncode == 0:
            break

    assert result is not None
    assert result.returncode == 0, (
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
        f"No scorecard/eval json in {out_dir}; "
        f"contents: {list(out_dir.rglob('*'))}"
    )

    report_artifact = _find_any(out_dir, ("report.md", "eval.md", "README.md"))
    assert report_artifact is not None, (
        f"No report.md/eval.md in {out_dir}; "
        f"contents: {list(out_dir.rglob('*'))}"
    )
