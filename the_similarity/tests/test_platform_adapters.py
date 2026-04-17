"""Tests for the platform adapters — finance, copies, worlds.

Each adapter is exercised against an isolated tmp_path SQLite DB so runs
cannot bleed across tests. The worlds adapter is JavaScript, so we cover
it via ``node -e`` subprocess invocations driven from Python — the
fractal package ships with the runner and a small scenario we can use.

Why split tests across surfaces?
-------------------------------
- Finance and copies adapters are pure Python; the registry is Python-
  stdlib. A direct import + fixture is the cheapest way to assert
  behavior and fails loudly if the adapter shape drifts.
- The worlds adapter is Node-side and the HTTP transport is what we
  want to exercise. We spin up a tiny stdlib http.server in a thread,
  point THE_SIMILARITY_API_URL at it, and inspect the POST payload.
"""

from __future__ import annotations

import json
import shutil
import socket
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List

import pytest

from the_similarity.platform.adapters.copies import register_copies_run
from the_similarity.platform.adapters.finance import register_backtest_run
from the_similarity.platform.artifacts import RunKind
from the_similarity.platform.registry import RunRegistry


# ---------------------------------------------------------------------------
# Finance adapter — dict-backed BacktestReport stand-in
# ---------------------------------------------------------------------------


def _fake_backtest_dict() -> Dict[str, Any]:
    """Minimal backtest result that exercises every summary field the adapter
    projects. Dict form avoids importing numpy just to build a fake.
    """
    return {
        "hit_rate": 0.56,
        "mean_error": 0.031,
        "crps": 0.018,
        "coverage": 0.82,
        "interval_score": 0.25,
        "profit_factor": 1.37,
        "max_drawdown": -0.08,
        "sharpe": 1.42,
        "calibration": {10: 0.11, 50: 0.49, 90: 0.88},
        "window_size": 30,
        "forward_bars": 20,
        "n_valid_trials": 100,
        "n_skipped_trials": 0,
    }


def test_finance_adapter_registers_run_and_scorecard(tmp_path: Path) -> None:
    """Registering a fake backtest dict writes one FINANCE row with the
    expected summary, config, and provenance fields.
    """
    db_path = tmp_path / "registry.db"
    run_id = register_backtest_run(
        _fake_backtest_dict(),
        config={"n_trials": 100, "top_k": 10},
        seed=42,
        db_path=str(db_path),
        source_id="spy",
    )

    # Assertions: one row, kind=FINANCE, summary carries the headline
    # metrics, config merges callers+report echoes, provenance has the
    # generator + source_id stamped by the adapter.
    with RunRegistry(db_path) as registry:
        artifact = registry.get(run_id)

    assert artifact is not None
    assert artifact.kind is RunKind.FINANCE
    assert artifact.seed == 42

    # Summary: scorecard-like fields are present and pillar is stamped.
    assert artifact.summary["hit_rate"] == 0.56
    assert artifact.summary["crps"] == 0.018
    assert artifact.summary["pillar"] == "finance"
    # Calibration keys must be stringified so JSON round-trip is lossless.
    assert artifact.summary["calibration"] == {"10": 0.11, "50": 0.49, "90": 0.88}

    # Config echoes the caller's kwargs AND the report's window_size /
    # forward_bars so the artifact is self-describing.
    assert artifact.config["n_trials"] == 100
    assert artifact.config["top_k"] == 10
    assert artifact.config["window_size"] == 30
    assert artifact.config["forward_bars"] == 20

    # Provenance: generator_name pinned to the public API, source_id
    # propagated, created_at ISO-format.
    assert artifact.provenance["generator_name"] == "the_similarity.api.backtest"
    assert artifact.provenance["source_id"] == "spy"
    assert artifact.provenance["seed"] == 42


def test_finance_adapter_tolerates_missing_fields(tmp_path: Path) -> None:
    """A minimal dict (only hit_rate) still registers; absent fields are
    simply omitted from summary rather than raising.
    """
    db_path = tmp_path / "registry.db"
    run_id = register_backtest_run(
        {"hit_rate": 0.5},
        db_path=str(db_path),
    )
    with RunRegistry(db_path) as registry:
        artifact = registry.get(run_id)

    assert artifact is not None
    assert artifact.summary == {"hit_rate": 0.5, "pillar": "finance"}
    # No calibration was passed — must not appear as an empty dict.
    assert "calibration" not in artifact.summary


def test_finance_adapter_accepts_object_report(tmp_path: Path) -> None:
    """Duck-typed object with attributes mirrors the BacktestReport API —
    adapter must pull fields via getattr without touching numpy.
    """

    class _FakeReport:
        # We only set the fields the adapter projects; missing ones should
        # be silently skipped (returns None via getattr default).
        hit_rate = 0.6
        crps = 0.02
        calibration = {50: 0.5}
        window_size = 40
        forward_bars = 15
        n_valid_trials = 80
        n_skipped_trials = 2

    db_path = tmp_path / "registry.db"
    run_id = register_backtest_run(
        _FakeReport(),
        db_path=str(db_path),
    )
    with RunRegistry(db_path) as registry:
        artifact = registry.get(run_id)

    assert artifact is not None
    assert artifact.summary["hit_rate"] == 0.6
    assert artifact.summary["calibration"] == {"50": 0.5}
    assert artifact.summary["n_valid_trials"] == 80


# ---------------------------------------------------------------------------
# Copies adapter — synthetic run dir with stub artifacts
# ---------------------------------------------------------------------------


def _write_stub_copies_run(run_dir: Path, *, with_parquets: bool = True) -> None:
    """Populate ``run_dir`` with the file shape the synthetic CLI emits.

    The adapter only reads scorecard.json + provenance.json for its
    summary/config fields; the parquet + report files are listed in
    artifact_paths if present. We always write scorecard + provenance
    here so the adapter has data; parquets are opt-in so a test can
    prove the adapter tolerates their absence.
    """
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "scorecard.json").write_text(
        json.dumps(
            {
                "passed": True,
                "dataset": {
                    "shape": [500, 3],
                    "columns": ["open", "high", "low"],
                    "provenance": None,
                },
                "fidelity": {"overall_score": 0.87, "passed": True},
                "privacy": {"overall_score": 0.92, "passed": True},
                "utility": {"transfer_gap": 0.05, "passed": True},
            }
        )
    )
    (run_dir / "provenance.json").write_text(
        json.dumps(
            {
                "source_id": "spy",
                "generator_name": "block_bootstrap",
                "generator_version": "1",
                "seed": 42,
                "created_at": "2026-04-15T20:00:00Z",
            }
        )
    )
    if with_parquets:
        # Empty bytes are enough — the adapter only records the path, it
        # does not read parquet contents.
        (run_dir / "real.parquet").write_bytes(b"")
        (run_dir / "synth.parquet").write_bytes(b"")
        (run_dir / "report.md").write_text("# stub\n")


def test_copies_adapter_registers_run(tmp_path: Path) -> None:
    """Registering a stub run dir writes a COPIES row whose summary and
    artifact_paths mirror the files on disk.
    """
    run_dir = tmp_path / "block_bootstrap-42-20260415-200000"
    _write_stub_copies_run(run_dir)

    db_path = tmp_path / "registry.db"
    run_id = register_copies_run(
        run_dir,
        n=500,
        db_path=str(db_path),
    )

    with RunRegistry(db_path) as registry:
        artifact = registry.get(run_id)

    assert artifact is not None
    assert artifact.kind is RunKind.COPIES
    assert artifact.seed == 42
    # Summary captures fidelity / privacy / utility scores from the
    # scorecard and stamps the pillar label.
    assert artifact.summary["pillar"] == "copies"
    assert artifact.summary["passed"] is True
    assert artifact.summary["fidelity_score"] == 0.87
    assert artifact.summary["privacy_score"] == 0.92
    assert artifact.summary["utility_transfer_gap"] == 0.05
    assert artifact.summary["n"] == 500
    assert artifact.summary["shape"] == [500, 3]

    # artifact_paths lists every file that actually exists in the run dir,
    # keyed by the canonical logical names.
    assert artifact.artifact_paths == {
        "real": "real.parquet",
        "synth": "synth.parquet",
        "scorecard": "scorecard.json",
        "provenance": "provenance.json",
        "report": "report.md",
    }

    # The adapter also writes artifact.json into the run dir by default so
    # the run dir is self-contained (matches /runs/copies API behavior).
    assert (run_dir / "artifact.json").exists()


def test_copies_adapter_omits_missing_files(tmp_path: Path) -> None:
    """When parquets / report are missing, artifact_paths drops them
    instead of listing dead pointers.
    """
    run_dir = tmp_path / "run"
    _write_stub_copies_run(run_dir, with_parquets=False)

    db_path = tmp_path / "registry.db"
    run_id = register_copies_run(run_dir, db_path=str(db_path))

    with RunRegistry(db_path) as registry:
        artifact = registry.get(run_id)

    assert artifact is not None
    # Only scorecard + provenance survived — the adapter must not invent
    # paths that do not exist on disk.
    assert set(artifact.artifact_paths) == {"scorecard", "provenance"}


def test_copies_adapter_fails_on_missing_dir(tmp_path: Path) -> None:
    """Nonexistent run_dir must raise FileNotFoundError, not silently
    register an empty row.
    """
    with pytest.raises(FileNotFoundError):
        register_copies_run(tmp_path / "does-not-exist", db_path=str(tmp_path / "r.db"))


# ---------------------------------------------------------------------------
# Worlds adapter — JS client exercised via a stdlib HTTP server
# ---------------------------------------------------------------------------


class _CapturingHandler(BaseHTTPRequestHandler):
    """HTTP handler that stores POST bodies in a class-level list.

    We use a class-level sink so the worker thread can hand payloads back
    to the main test thread without extra plumbing. The server is
    single-use per test — instantiate, POST, tear down, inspect.
    """

    captured: List[Dict[str, Any]] = []

    def log_message(
        self, format: str, *args: Any
    ) -> None:  # pragma: no cover - stderr noise
        # Suppress default stderr logging from BaseHTTPRequestHandler so
        # pytest output stays quiet.
        return

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b""
        try:
            payload = json.loads(body.decode("utf-8")) if body else {}
        except json.JSONDecodeError:
            payload = {"_raw": body.decode("utf-8", errors="replace")}
        _CapturingHandler.captured.append({"path": self.path, "payload": payload})
        # Respond with 201 so the JS client treats the POST as success and
        # returns the run_id.
        resp = json.dumps({"ok": True}).encode("utf-8")
        self.send_response(201)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(resp)))
        self.end_headers()
        self.wfile.write(resp)


def _pick_free_port() -> int:
    """Bind a transient socket to port 0 and return the assigned port.

    Avoids the classic TOCTOU flake of picking a port and having it taken
    before the server binds — we hold the socket open only long enough
    to read its port, then close it so ThreadingHTTPServer can rebind.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def capturing_server():
    """Spin up a one-shot HTTP server on a free port, yield the URL.

    Resets the handler's captured list before each test so cross-test
    state never leaks. The server shuts down on fixture teardown.
    """
    _CapturingHandler.captured = []
    port = _pick_free_port()
    server = ThreadingHTTPServer(("127.0.0.1", port), _CapturingHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def _have_node() -> bool:
    return shutil.which("node") is not None


@pytest.mark.skipif(not _have_node(), reason="node not installed")
def test_worlds_adapter_posts_run_artifact(
    tmp_path: Path, capturing_server: str
) -> None:
    """registerWorldRun POSTs a RunArtifact-shaped payload to the API.

    We skip the runner itself (that's covered elsewhere) and drive the
    JS adapter directly via ``node -e``. The test server captures the
    POST body; we assert the schema shape and the summary passthrough.
    """
    # Build a minimal JSONL file with provenance and summary lines.
    jsonl = tmp_path / "run.jsonl"
    jsonl.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "type": "provenance",
                        "seed": 7,
                        "generator_name": "the-similarity-fractal-headless",
                        "version": "0.1.0",
                        "scenario_name": "small_village",
                        "created_at": "2026-04-15T20:00:00Z",
                    }
                ),
                json.dumps({"type": "tick", "tick": 1, "metrics": {"alive": 20}}),
                json.dumps(
                    {
                        "type": "summary",
                        "final_metrics": {"alive": 18, "dead": 2},
                        "totals": {"deaths": 2, "births": 0},
                        "wall_time_ms": 7,
                    }
                ),
            ]
        )
        + "\n"
    )

    # Resolve an absolute path to the adapter module so ``node -e`` can
    # import it regardless of the cwd we inherit from pytest.
    repo_root = Path(__file__).resolve().parents[2]
    adapter_js = (
        repo_root / "the-similarity-fractal" / "src" / "platform" / "registry-client.js"
    )
    assert adapter_js.exists(), f"adapter JS missing: {adapter_js}"

    # One-liner: import the adapter, call registerWorldRun, print the
    # returned run_id so the Python side can pair it with the captured
    # POST payload.
    script = (
        f"import('{adapter_js.as_uri()}').then(async (m) => {{"
        f"  const rid = await m.registerWorldRun({{"
        f"    runDir: '{tmp_path.as_posix()}',"
        f"    jsonlPath: '{jsonl.as_posix()}',"
        f"    scenario: 'scenarios/small_village.json',"
        f"    seed: 7,"
        f"    steps: 30,"
        f"    apiUrl: '{capturing_server}',"
        f"    log: () => {{}},"
        f"  }});"
        f"  process.stdout.write(String(rid));"
        f"}});"
    )
    proc = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        capture_output=True,
        text=True,
        timeout=15,
        check=True,
    )
    run_id = proc.stdout.strip()
    assert run_id and len(run_id) == 32, (
        f"unexpected run_id output: {proc.stdout!r} stderr={proc.stderr!r}"
    )

    # The server must have seen exactly one POST to /platform/runs with a
    # RunArtifact-shaped body.
    assert len(_CapturingHandler.captured) == 1
    captured = _CapturingHandler.captured[0]
    assert captured["path"] == "/platform/runs"
    payload = captured["payload"]
    assert payload["run_id"] == run_id
    assert payload["kind"] == "worlds"
    assert payload["seed"] == 7
    assert payload["config"] == {
        "scenario_path": "scenarios/small_village.json",
        "seed": 7,
        "steps": 30,
    }
    assert payload["artifact_paths"] == {"telemetry": "run.jsonl"}
    # Summary flows through from the JSONL's summary line, plus the
    # adapter's pillar stamp.
    assert payload["summary"]["pillar"] == "worlds"
    assert payload["summary"]["final_metrics"] == {"alive": 18, "dead": 2}
    assert payload["summary"]["wall_time_ms"] == 7
    # Provenance carries the scenario info from the JSONL header plus the
    # run_dir the adapter stamped.
    assert payload["provenance"]["seed"] == 7
    assert payload["provenance"]["scenario_name"] == "small_village"
    assert payload["provenance"]["run_dir"] == str(tmp_path)


@pytest.mark.skipif(not _have_node(), reason="node not installed")
def test_worlds_adapter_is_best_effort_on_server_down(tmp_path: Path) -> None:
    """When the API is unreachable, registerWorldRun must resolve to null
    rather than raising — the runner relies on this to exit 0.
    """
    jsonl = tmp_path / "run.jsonl"
    jsonl.write_text(
        json.dumps(
            {
                "type": "provenance",
                "seed": 1,
                "generator_name": "x",
                "version": "0",
            }
        )
        + "\n"
        + json.dumps(
            {"type": "summary", "final_metrics": {}, "totals": {}, "wall_time_ms": 0}
        )
        + "\n"
    )

    repo_root = Path(__file__).resolve().parents[2]
    adapter_js = (
        repo_root / "the-similarity-fractal" / "src" / "platform" / "registry-client.js"
    )

    # Port 1 is guaranteed unreachable from user-space on macOS/Linux;
    # ECONNREFUSED is the expected failure mode the adapter traps.
    script = (
        f"import('{adapter_js.as_uri()}').then(async (m) => {{"
        f"  const rid = await m.registerWorldRun({{"
        f"    runDir: '{tmp_path.as_posix()}',"
        f"    jsonlPath: '{jsonl.as_posix()}',"
        f"    seed: 1,"
        f"    steps: 1,"
        f"    apiUrl: 'http://127.0.0.1:1',"
        f"    log: () => {{}},"
        f"  }});"
        f"  process.stdout.write(rid === null ? 'null' : String(rid));"
        f"}});"
    )
    proc = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        capture_output=True,
        text=True,
        timeout=15,
        check=True,
    )
    assert proc.stdout.strip() == "null", (
        f"expected null on unreachable server, got {proc.stdout!r}"
    )
