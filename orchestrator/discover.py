"""
Autonomous task discovery for the orchestrator.

Three discovery sources, run in sequence:
1. GitHub Issues — pulls open issues labeled "auto" or "agent"
2. Codebase scan — finds TODOs, FIXMEs, missing tests, lint errors
3. Planner agent — asks Claude to analyze the repo and propose tasks

Each source produces Task objects that feed into run.py's execution pipeline.
"""

import asyncio
import json
import re
import subprocess
from pathlib import Path

from config import CLAUDE_BIN, OrchestratorConfig, REPO_ROOT


# ── Source 1: GitHub Issues ─────────────────────────────────────────


def discover_from_issues(labels: list[str] | None = None) -> list[dict]:
    """
    Pull open GitHub issues and convert them to task dicts.

    By default, pulls issues with labels "auto" or "agent".
    Each issue becomes one task. The issue body is the prompt.

    Uses `gh` CLI — requires auth.
    """
    labels = labels or ["auto", "agent"]
    label_filter = ",".join(labels)

    try:
        result = subprocess.run(
            [
                "gh", "issue", "list",
                "--state", "open",
                "--label", label_filter,
                "--json", "number,title,body,labels",
                "--limit", "50",
            ],
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
            timeout=30,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        print("  [discover] gh CLI not available or timed out, skipping issues")
        return []

    if result.returncode != 0:
        print(f"  [discover] gh issue list failed: {result.stderr[:200]}")
        return []

    issues = json.loads(result.stdout) if result.stdout.strip() else []
    tasks = []

    for issue in issues:
        task_id = f"issue-{issue['number']}"
        # Build a rich prompt from the issue
        prompt = (
            f"GitHub Issue #{issue['number']}: {issue['title']}\n\n"
            f"{issue.get('body', '(no description)')}\n\n"
            f"---\n"
            f"Implement this issue. Read the relevant code first, make changes, "
            f"write tests, run all tests, commit, push, and open a PR.\n"
            f"In the PR body, include 'Closes #{issue['number']}' so it auto-closes the issue."
        )
        tasks.append({
            "id": task_id,
            "title": issue["title"],
            "prompt": prompt,
            "source": "github-issues",
        })

    print(f"  [discover] Found {len(tasks)} tasks from GitHub issues")
    return tasks


# ── Source 2: Codebase scan ─────────────────────────────────────────


def discover_from_codebase() -> list[dict]:
    """
    Scan the codebase for actionable items:
    - TODO/FIXME comments in Python files
    - Python files in methods/ without corresponding test files
    - Ruff lint errors

    Groups related items and creates one task per category.
    """
    tasks = []

    # ── TODOs and FIXMEs ──
    todos = _find_todos()
    if todos:
        # Group by file, create one task per file with TODOs
        by_file: dict[str, list[str]] = {}
        for filepath, line_num, text in todos:
            rel = str(Path(filepath).relative_to(REPO_ROOT))
            by_file.setdefault(rel, []).append(f"  Line {line_num}: {text}")

        # Create one batch task for all TODOs (not one per file — too noisy)
        todo_list = ""
        for filepath, items in list(by_file.items())[:10]:  # Cap at 10 files
            todo_list += f"\n{filepath}:\n" + "\n".join(items[:5]) + "\n"

        if todo_list.strip():
            tasks.append({
                "id": "resolve-todos",
                "title": "fix: resolve TODO/FIXME comments",
                "prompt": (
                    f"The following TODO/FIXME comments need to be resolved:\n"
                    f"{todo_list}\n\n"
                    f"For each TODO: read the surrounding code, implement what's needed, "
                    f"remove the TODO comment, add tests if the change is non-trivial. "
                    f"Run all tests before opening a PR."
                ),
                "source": "codebase-todos",
            })

    # ── Missing tests ──
    missing = _find_untested_methods()
    if missing:
        method_list = "\n".join(f"  - {m}" for m in missing)
        tasks.append({
            "id": "add-missing-tests",
            "title": "test: add tests for untested methods",
            "prompt": (
                f"The following method files have no corresponding test file:\n"
                f"{method_list}\n\n"
                f"For each, create a test file following the existing test patterns. "
                f"Test basic functionality, edge cases, and type handling. "
                f"Run all tests before opening a PR."
            ),
            "source": "codebase-coverage",
        })

    # ── Lint errors ──
    lint_errors = _find_lint_errors()
    if lint_errors:
        tasks.append({
            "id": "fix-lint-errors",
            "title": "fix: resolve ruff lint errors",
            "prompt": (
                f"Ruff found the following lint errors:\n\n"
                f"{lint_errors[:3000]}\n\n"
                f"Fix all errors. Do NOT just add noqa comments — fix the actual issues. "
                f"Run `ruff check the_similarity/` to verify, then run all tests."
            ),
            "source": "codebase-lint",
        })

    print(f"  [discover] Found {len(tasks)} tasks from codebase scan")
    return tasks


def _find_todos() -> list[tuple[str, int, str]]:
    """Find TODO/FIXME comments in Python source files."""
    results = []
    src_dir = REPO_ROOT / "the_similarity"
    if not src_dir.exists():
        return results

    for py_file in src_dir.rglob("*.py"):
        if "test" in py_file.name:
            continue
        try:
            for i, line in enumerate(py_file.read_text().splitlines(), 1):
                if re.search(r"#\s*(TODO|FIXME|HACK|XXX)", line, re.IGNORECASE):
                    results.append((str(py_file), i, line.strip()))
        except (OSError, UnicodeDecodeError):
            continue

    return results


def _find_untested_methods() -> list[str]:
    """Find method files without corresponding test files."""
    methods_dir = REPO_ROOT / "the_similarity" / "methods"
    tests_dir = REPO_ROOT / "the_similarity" / "tests"

    if not methods_dir.exists() or not tests_dir.exists():
        return []

    test_files = {f.stem for f in tests_dir.glob("test_*.py")}
    missing = []

    for method_file in methods_dir.glob("*.py"):
        if method_file.name == "__init__.py":
            continue
        # Expected test file: test_<method_name>.py
        expected_test = f"test_{method_file.stem}"
        if expected_test not in test_files:
            missing.append(str(method_file.relative_to(REPO_ROOT)))

    return missing


def _find_lint_errors() -> str:
    """Run ruff and capture errors."""
    try:
        result = subprocess.run(
            ["ruff", "check", "the_similarity/", "--output-format=text"],
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
            timeout=60,
        )
        return result.stdout.strip() if result.returncode != 0 else ""
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return ""


# ── Source 3: Planner agent ─────────────────────────────────────────


PLANNER_PROMPT = """\
You are a senior engineer analyzing The Similarity codebase to find high-value tasks.

Look at:
- Recent git log (last 20 commits) for momentum and context
- Open issues or known gaps
- Code quality: any modules that are thin, untested, or have stale patterns
- The project's CLAUDE.md for architecture and current state

Output ONLY a JSON array of task objects. Each task:
{
  "id": "kebab-case-slug",
  "title": "type: short PR title",
  "prompt": "Full detailed prompt for an autonomous agent..."
}

Rules:
- Max 5 tasks. Quality over quantity.
- Each task must be completable in <30 minutes by an autonomous agent.
- Focus on: test coverage, bug fixes, small features, documentation gaps.
- Do NOT propose large refactors or architectural changes.
- Do NOT propose tasks that duplicate recent commits.
- Prompts must be self-contained — the agent only has the prompt + repo.
"""


async def discover_from_planner(cfg: OrchestratorConfig) -> list[dict]:
    """
    Ask Claude to analyze the repo and propose tasks.

    Runs claude CLI in --print mode (no worktree needed — read-only analysis).
    Parses the JSON output into task dicts.
    """
    cmd = [
        CLAUDE_BIN,
        "--print",
        "--model", cfg.model,
        "--permission-mode", "bypassPermissions",
        "--output-format", "json",
        PLANNER_PROMPT,
    ]

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(REPO_ROOT),
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)
    except (asyncio.TimeoutError, Exception) as e:
        print(f"  [discover] Planner agent failed: {e}")
        return []

    if proc.returncode != 0:
        print(f"  [discover] Planner agent exited {proc.returncode}")
        return []

    # Parse JSON from claude's output
    # The --output-format json wraps the response, so extract the text content
    raw = stdout.decode(errors="replace")
    tasks = _parse_planner_output(raw)
    print(f"  [discover] Planner proposed {len(tasks)} tasks")
    return tasks


def _parse_planner_output(raw: str) -> list[dict]:
    """
    Extract task JSON from planner output.

    Handles both raw JSON arrays and JSON wrapped in the claude
    --output-format json envelope.
    """
    # Try to parse as claude JSON output format first
    try:
        envelope = json.loads(raw)
        # Claude JSON format: {"result": "...", ...} or {"content": [...]}
        text = ""
        if isinstance(envelope, dict):
            text = envelope.get("result", "") or envelope.get("text", "") or raw
        elif isinstance(envelope, list):
            # Might be the task array directly
            return _validate_tasks(envelope)
        else:
            text = raw
    except json.JSONDecodeError:
        text = raw

    # Find JSON array in the text
    # Look for [...] pattern
    match = re.search(r"\[[\s\S]*\]", text)
    if not match:
        return []

    try:
        tasks = json.loads(match.group(0))
        return _validate_tasks(tasks)
    except json.JSONDecodeError:
        return []


def _validate_tasks(tasks: list) -> list[dict]:
    """Validate and normalize task dicts from the planner."""
    valid = []
    for t in tasks:
        if not isinstance(t, dict):
            continue
        if not all(k in t for k in ("id", "title", "prompt")):
            continue
        # Sanitize id to be branch-safe
        task_id = re.sub(r"[^a-z0-9-]", "-", t["id"].lower()).strip("-")
        if not task_id:
            continue
        valid.append({
            "id": f"plan-{task_id}",
            "title": t["title"][:70],
            "prompt": t["prompt"],
            "source": "planner",
        })
    return valid[:5]  # Cap at 5


# ── Combined discovery ──────────────────────────────────────────────


async def discover_all(
    cfg: OrchestratorConfig,
    sources: list[str] | None = None,
) -> list[dict]:
    """
    Run all discovery sources and merge results.

    sources: list of enabled sources. Default: all three.
             Options: "issues", "codebase", "planner"

    Returns deduplicated task dicts ready for Task() construction.
    """
    sources = sources or ["issues", "codebase", "planner"]
    all_tasks: list[dict] = []

    print("\n  Discovering tasks...")

    if "issues" in sources:
        all_tasks.extend(discover_from_issues())

    if "codebase" in sources:
        all_tasks.extend(discover_from_codebase())

    if "planner" in sources:
        planner_tasks = await discover_from_planner(cfg)
        all_tasks.extend(planner_tasks)

    # Deduplicate by id
    seen: set[str] = set()
    unique: list[dict] = []
    for t in all_tasks:
        if t["id"] not in seen:
            seen.add(t["id"])
            unique.append(t)

    print(f"  Total: {len(unique)} unique tasks from {len(sources)} sources\n")
    return unique
