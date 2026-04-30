#!/usr/bin/env python3
"""
Autonomous orchestrator for The Similarity.

Reads tasks from a YAML file, spawns parallel Claude or Codex CLI sessions in
isolated git worktrees, tracks progress, retries on failure, and
reports results.

Usage:
    python orchestrator/run.py                          # run all pending tasks
    python orchestrator/run.py --tasks orchestrator/tasks.yaml
    python orchestrator/run.py --max-parallel 10
    python orchestrator/run.py --dry-run                # print what would run

Each task gets:
    1. Its own git worktree
    2. A full worker session with autonomous permissions
    3. Auto-commit, push, and PR creation
    4. pr-gate.yml handles review-agent + auto-merge

The orchestrator only tracks: spawned → succeeded/failed/retrying.
The PR pipeline handles quality gates.
"""

import argparse
import asyncio
import json
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path

import yaml

from config import CLAUDE_BIN, CODEX_BIN, RESULTS_DIR, TASKS_FILE, OrchestratorConfig


# ── Task model ──────────────────────────────────────────────────────


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    RETRYING = "retrying"


class AgentKind(str, Enum):
    CLAUDE = "claude"
    CODEX = "codex"


@dataclass
class Task:
    """
    A single unit of work for a worktree agent.

    id:      Unique slug used for branch naming (e.g. "add-moving-average").
    title:   Human-readable title for the PR.
    agent:   Worker CLI to run: "claude" or "codex".
    prompt:  Full prompt sent to the worker CLI. Should be self-contained —
             the agent has no context beyond this prompt + the repo.
    status:  Tracks lifecycle. Only the orchestrator mutates this.
    attempt: Current attempt number (0-indexed). Incremented on retry.
    error:   Last error message, appended to prompt on retry so the agent
             can self-correct.
    pr_url:  Set on success if the agent opened a PR.
    """

    id: str
    title: str
    prompt: str
    agent: AgentKind = AgentKind.CLAUDE
    status: TaskStatus = TaskStatus.PENDING
    attempt: int = 0
    error: str = ""
    pr_url: str = ""
    start_time: float = 0
    end_time: float = 0

    @property
    def branch_name(self) -> str:
        """Git branch name derived from task id."""
        return f"auto/{self.id}"

    @property
    def worktree_dir_name(self) -> str:
        """Filesystem-safe directory name for explicit worktree workers."""
        return self.branch_name.replace("/", "-")

    @property
    def duration_seconds(self) -> float:
        if self.start_time and self.end_time:
            return self.end_time - self.start_time
        return 0


# ── Task file parsing ───────────────────────────────────────────────


def load_tasks(path: Path, default_agent: AgentKind = AgentKind.CLAUDE) -> list[Task]:
    """
    Parse tasks.yaml into Task objects.

    Expected format:
        tasks:
          - id: add-moving-average
            title: "feat: add moving average similarity method"
            prompt: |
              Add a moving average method to the_similarity/methods/...
    """
    with open(path) as f:
        data = yaml.safe_load(f)

    tasks = []
    for entry in data.get("tasks", []):
        tasks.append(
            Task(
                id=entry["id"],
                title=entry["title"],
                prompt=entry["prompt"],
                agent=AgentKind(entry.get("agent", default_agent.value)),
            )
        )
    return tasks


# ── Build worker CLI commands ───────────────────────────────────────


# System prompt injected into every worker agent. Gives it the
# operational context: you're autonomous, commit, push, open PR.
WORKER_SYSTEM_PROMPT = """\
You are an autonomous worker agent for The Similarity project.
You are running in an isolated git worktree with your own branch.

Your job:
1. Read the task prompt carefully.
2. Implement the changes — code, tests, docs as needed.
3. Run tests: python -m pytest the_similarity/tests/ -v
4. If tests fail, fix them. Do not open a PR with failing tests.
5. Commit granularly (one logical change per commit). Do NOT add Co-Authored-By trailers.
6. Push your branch: git push -u origin HEAD
7. Open a PR: gh pr create --title "<title>" --body "<description>"
8. Print the PR URL as your final output.

KNOWLEDGE BASE — MANDATORY:
If your work produces durable knowledge (new method, architecture decision,
non-obvious bug fix, research insight, data source), you MUST write or update
a note in obsidian_thesim/. See .claude/OBSIDIAN_KB.md for conventions.
- New methods/modules → obsidian_thesim/concepts/<name>.md
- Decisions/insights → obsidian_thesim/topics/<topic>.md
- Research → obsidian_thesim/research/<name>.md
- DO NOT edit obsidian_thesim/_MOC.md — the orchestrator updates it post-merge.
- Use [[wikilinks]] to cross-link. Keep notes concise.
Skip this for purely mechanical changes (renames, dep bumps, formatting).

SHARED-FILE RULES:
- DO NOT edit: _MOC.md, CHANGELOG.md, pyproject.toml, .gitignore
  (these cause merge conflicts when multiple agents touch them in parallel).
- If you need a .gitignore entry, note it in your PR description instead.

If you cannot complete the task, explain what went wrong clearly.
Do NOT ask for human input — you are fully autonomous.
"""


def build_prompt(task: Task) -> str:
    """
    Build the user-facing task prompt.

    On retry, the previous error is appended to the prompt
    so the agent can learn from the failure.
    """
    prompt = task.prompt.strip()
    if task.attempt > 0 and task.error:
        prompt += (
            f"\n\n---\nPREVIOUS ATTEMPT FAILED (attempt {task.attempt}):\n"
            f"{task.error}\n\n"
            f"Fix the issues above and try again."
        )
    return prompt


def build_command(task: Task, cfg: OrchestratorConfig) -> list[str]:
    """Build the worker CLI command for a task."""
    if task.agent == AgentKind.CLAUDE:
        return build_claude_command(task, cfg)
    if task.agent == AgentKind.CODEX:
        return build_codex_command(task, cfg)
    raise ValueError(f"Unsupported agent: {task.agent}")


def build_claude_command(task: Task, cfg: OrchestratorConfig) -> list[str]:
    """
    Build the Claude CLI command for a task.

    Uses --worktree for automatic git worktree isolation, --print for
    non-interactive mode, and --permission-mode for autonomous operation.
    """
    prompt = build_prompt(task)
    cmd = [
        CLAUDE_BIN,
        "--print",
        "--worktree", task.branch_name,
        "--model", cfg.model,
        "--permission-mode", cfg.permission_mode,
        "--append-system-prompt", WORKER_SYSTEM_PROMPT,
        *cfg.extra_flags,
        prompt,
    ]
    return cmd


def build_codex_command(task: Task, cfg: OrchestratorConfig) -> list[str]:
    """
    Build the Codex CLI command for a task.

    Codex does not provide Claude's `--worktree` flag, so the orchestrator
    creates the git worktree explicitly before launching this command.
    """
    prompt = f"{WORKER_SYSTEM_PROMPT}\n\nTASK:\n{build_prompt(task)}"
    cmd = [
        CODEX_BIN,
        "exec",
        "--full-auto",
        "--sandbox",
        cfg.codex_sandbox,
        "-C",
        str(codex_worktree_path(task, cfg)),
    ]
    if cfg.codex_model:
        cmd.extend(["--model", cfg.codex_model])
    cmd.extend(cfg.codex_extra_flags)
    cmd.append(prompt)
    return cmd


def codex_worktree_path(task: Task, cfg: OrchestratorConfig) -> Path:
    """Return the explicit git worktree path used by Codex workers."""
    return cfg.codex_worktree_root / task.worktree_dir_name


def prepare_task_worktree(task: Task, cfg: OrchestratorConfig) -> None:
    """
    Ensure the task has an isolated worktree before launching the worker.

    Claude workers use Claude CLI's built-in `--worktree`. Codex workers need
    an explicit git worktree because Codex CLI runs inside a given directory.
    """
    if task.agent != AgentKind.CODEX:
        return

    worktree_path = codex_worktree_path(task, cfg)
    if worktree_path.exists():
        return

    cfg.codex_worktree_root.mkdir(parents=True, exist_ok=True)
    branch_exists = _git_branch_exists(task.branch_name)
    if branch_exists:
        cmd = ["git", "worktree", "add", str(worktree_path), task.branch_name]
    else:
        cmd = [
            "git",
            "worktree",
            "add",
            "-b",
            task.branch_name,
            str(worktree_path),
            "origin/main",
        ]

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=str(Path(__file__).resolve().parent.parent),
        timeout=60,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise RuntimeError(f"Failed to create Codex worktree: {detail}")


def _git_branch_exists(branch_name: str) -> bool:
    """Return whether a local branch already exists."""
    result = subprocess.run(
        ["git", "show-ref", "--verify", "--quiet", f"refs/heads/{branch_name}"],
        cwd=str(Path(__file__).resolve().parent.parent),
        timeout=30,
    )
    return result.returncode == 0


# ── Run a single task ───────────────────────────────────────────────


async def run_task(task: Task, cfg: OrchestratorConfig, sem: asyncio.Semaphore) -> Task:
    """
    Execute a single task in a worktree agent.

    Acquires the semaphore (concurrency limiter), spawns the claude CLI
    process, captures output, and determines success/failure.

    Returns the task with updated status, pr_url, and error fields.
    """
    async with sem:
        task.status = TaskStatus.RUNNING
        task.start_time = time.time()
        print(f"  [{task.id}] Starting {task.agent.value} (attempt {task.attempt + 1})...")

        timeout_sec = cfg.timeout_minutes * 60

        try:
            prepare_task_worktree(task, cfg)
            cmd = build_command(task, cfg)
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                # Run from repo root so Claude --worktree can find .git.
                # Codex also receives an explicit -C worktree path.
                cwd=str(Path(__file__).resolve().parent.parent),
            )

            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(), timeout=timeout_sec
            )
            stdout = stdout_bytes.decode(errors="replace")
            stderr = stderr_bytes.decode(errors="replace")

        except asyncio.TimeoutError:
            proc.kill()
            await proc.communicate()
            task.status = TaskStatus.FAILED
            task.error = f"Timed out after {cfg.timeout_minutes} minutes"
            task.end_time = time.time()
            print(f"  [{task.id}] TIMEOUT after {cfg.timeout_minutes}m")
            return task

        except Exception as e:
            task.status = TaskStatus.FAILED
            task.error = str(e)
            task.end_time = time.time()
            print(f"  [{task.id}] ERROR: {e}")
            return task

        task.end_time = time.time()
        duration = task.duration_seconds

        # Determine success: check for PR URL in output.
        # Non-interactive worker CLIs output the final response as text.
        if proc.returncode == 0:
            # Try to extract PR URL from output
            pr_url = _extract_pr_url(stdout)
            if pr_url:
                task.status = TaskStatus.SUCCEEDED
                task.pr_url = pr_url
                print(f"  [{task.id}] SUCCESS in {duration:.0f}s -> {pr_url}")
            else:
                # Agent completed but may not have opened a PR
                # Still count as success if exit code 0
                task.status = TaskStatus.SUCCEEDED
                task.pr_url = "(no PR URL found in output)"
                print(f"  [{task.id}] DONE in {duration:.0f}s (no PR URL detected)")
        else:
            task.status = TaskStatus.FAILED
            # Capture last 2000 chars of output as error context for retry
            combined = (stdout + "\n" + stderr).strip()
            task.error = combined[-2000:]
            print(f"  [{task.id}] FAILED in {duration:.0f}s (exit {proc.returncode})")

        # Save raw output for debugging
        _save_output(task, stdout, stderr)

        return task


def _extract_pr_url(output: str) -> str:
    """
    Extract a GitHub PR URL from worker output.

    Looks for patterns like:
        https://github.com/<org>/<repo>/pull/<number>
    """
    import re

    match = re.search(r"https://github\.com/[^\s]+/pull/\d+", output)
    return match.group(0) if match else ""


def _save_output(task: Task, stdout: str, stderr: str) -> None:
    """Save raw agent output to results/ for post-mortem debugging."""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out_file = RESULTS_DIR / f"{task.id}_attempt{task.attempt}.json"
    out_file.write_text(
        json.dumps(
            {
                "task_id": task.id,
                "attempt": task.attempt,
                "status": task.status.value,
                "duration_seconds": task.duration_seconds,
                "pr_url": task.pr_url,
                "error": task.error,
                "stdout_tail": stdout[-5000:],
                "stderr_tail": stderr[-2000:],
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
            indent=2,
        )
    )


# ── Retry logic ─────────────────────────────────────────────────────


async def run_with_retries(
    task: Task, cfg: OrchestratorConfig, sem: asyncio.Semaphore
) -> Task:
    """
    Run a task with automatic retries on failure.

    Each retry appends the previous error to the prompt, giving the
    agent context to self-correct. Max retries controlled by config.
    """
    for attempt in range(cfg.max_retries + 1):
        task.attempt = attempt
        task = await run_task(task, cfg, sem)

        if task.status == TaskStatus.SUCCEEDED:
            return task

        if attempt < cfg.max_retries:
            task.status = TaskStatus.RETRYING
            print(f"  [{task.id}] Retrying ({attempt + 1}/{cfg.max_retries})...")

    return task


# ── Orchestrator main loop ──────────────────────────────────────────


async def orchestrate(tasks: list[Task], cfg: OrchestratorConfig) -> list[Task]:
    """
    Run all tasks in parallel up to max_parallel concurrency.

    Uses an asyncio.Semaphore to limit concurrent worktree agents.
    All tasks are launched immediately but the semaphore queues them.
    """
    sem = asyncio.Semaphore(cfg.max_parallel)

    print(f"\n{'='*60}")
    print(f"  Orchestrator: {len(tasks)} tasks, {cfg.max_parallel} parallel")
    print(f"  Model: {cfg.model}, retries: {cfg.max_retries}, timeout: {cfg.timeout_minutes}m")
    print(f"{'='*60}\n")

    # Launch all tasks — semaphore handles queuing
    results = await asyncio.gather(
        *[run_with_retries(task, cfg, sem) for task in tasks]
    )

    return list(results)


def print_summary(results: list[Task]) -> None:
    """Print a summary table of all task results."""
    succeeded = [t for t in results if t.status == TaskStatus.SUCCEEDED]
    failed = [t for t in results if t.status == TaskStatus.FAILED]

    print(f"\n{'='*60}")
    print(f"  RESULTS: {len(succeeded)}/{len(results)} succeeded, {len(failed)} failed")
    print(f"{'='*60}\n")

    for t in results:
        icon = "OK" if t.status == TaskStatus.SUCCEEDED else "FAIL"
        dur = f"{t.duration_seconds:.0f}s" if t.duration_seconds else "n/a"
        pr = t.pr_url or t.error[:80]
        print(f"  [{icon}] {t.id} ({dur}) — {pr}")

    if failed:
        print("\n  Failed tasks:")
        for t in failed:
            print(f"    - {t.id}: {t.error[:200]}")

    # Save summary to results/
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    summary_file = RESULTS_DIR / f"run_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.json"
    summary_file.write_text(
        json.dumps(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "total": len(results),
                "succeeded": len(succeeded),
                "failed": len(failed),
                "tasks": [
                    {
                        "id": t.id,
                        "status": t.status.value,
                        "pr_url": t.pr_url,
                        "duration_seconds": t.duration_seconds,
                        "attempts": t.attempt + 1,
                        "error": t.error[:500] if t.error else "",
                    }
                    for t in results
                ],
            },
            indent=2,
        )
    )
    print(f"\n  Results saved to {summary_file}")


# ── CLI entrypoint ──────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        description="Autonomous orchestrator — spawns parallel Claude/Codex worktree agents"
    )

    # ── Task source (mutually exclusive) ──
    source = parser.add_mutually_exclusive_group()
    source.add_argument(
        "--tasks",
        type=Path,
        default=None,
        help="Path to tasks YAML file (default: orchestrator/tasks.yaml)",
    )
    source.add_argument(
        "--auto",
        action="store_true",
        help="Autonomous mode: discover tasks from GitHub issues, codebase, and planner",
    )

    # ── Auto-discovery options ──
    parser.add_argument(
        "--sources",
        type=str,
        default="issues,codebase,planner",
        help="Comma-separated discovery sources for --auto (default: issues,codebase,planner)",
    )
    parser.add_argument(
        "--loop",
        type=int,
        default=None,
        metavar="MINUTES",
        help="Loop mode: re-discover and execute every N minutes (use with --auto)",
    )

    # ── Execution options ──
    parser.add_argument(
        "--max-parallel",
        type=int,
        default=None,
        help="Max concurrent agents (default: 5)",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="Claude model (default: sonnet)",
    )
    parser.add_argument(
        "--codex-model",
        type=str,
        default=None,
        help="Codex model override (default: Codex CLI profile default)",
    )
    parser.add_argument(
        "--agent",
        type=str,
        choices=[AgentKind.CLAUDE.value, AgentKind.CODEX.value],
        default=AgentKind.CLAUDE.value,
        help="Default agent for discovered tasks or tasks without an agent field",
    )
    parser.add_argument(
        "--codex-worktree-root",
        type=Path,
        default=None,
        help="Directory for Codex-created worktrees",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=None,
        help="Timeout per task in minutes (default: 30)",
    )
    parser.add_argument(
        "--retries",
        type=int,
        default=None,
        help="Max retries per task (default: 1)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print tasks and commands without executing",
    )
    args = parser.parse_args()

    # Load config with CLI overrides
    cfg = OrchestratorConfig()
    if args.max_parallel is not None:
        cfg.max_parallel = args.max_parallel
    if args.model is not None:
        cfg.model = args.model
    if args.codex_model is not None:
        cfg.codex_model = args.codex_model
    if args.codex_worktree_root is not None:
        cfg.codex_worktree_root = args.codex_worktree_root
    if args.timeout is not None:
        cfg.timeout_minutes = args.timeout
    if args.retries is not None:
        cfg.max_retries = args.retries

    if args.auto:
        # ── Autonomous mode ──
        _run_auto(args, cfg)
    else:
        # ── Manual mode (tasks.yaml) ──
        tasks_path = args.tasks or TASKS_FILE
        if not tasks_path.exists():
            print(f"ERROR: Tasks file not found: {tasks_path}")
            print(f"Create one at {TASKS_FILE} — see tasks.example.yaml for format.")
            print("Or use --auto for autonomous task discovery.")
            sys.exit(1)

        tasks = load_tasks(tasks_path, default_agent=AgentKind(args.agent))
        if not tasks:
            print("No tasks found in file.")
            sys.exit(0)

        print(f"Loaded {len(tasks)} tasks from {tasks_path}")
        _execute_tasks(tasks, cfg, args.dry_run)


def _run_auto(args, cfg: OrchestratorConfig):
    """
    Autonomous mode: discover tasks and execute them.

    With --loop, repeats every N minutes indefinitely.
    Without --loop, runs once and exits.
    """
    from discover import discover_all

    sources = [s.strip() for s in args.sources.split(",")]

    if args.loop:
        # ── Continuous loop mode ──
        loop_minutes = args.loop
        print(f"Autonomous loop mode: every {loop_minutes} minutes")
        print(f"Sources: {', '.join(sources)}")
        print("Press Ctrl+C to stop\n")

        cycle = 0
        while True:
            cycle += 1
            print(f"\n{'#'*60}")
            print(f"  CYCLE {cycle} — {datetime.now(timezone.utc).isoformat()}")
            print(f"{'#'*60}")

            # Pull latest main before discovering
            _git_pull()

            task_dicts = asyncio.run(discover_all(cfg, sources))
            if task_dicts:
                tasks = [
                    Task(
                        id=t["id"],
                        title=t["title"],
                        prompt=t["prompt"],
                        agent=AgentKind(t.get("agent", args.agent)),
                    )
                    for t in task_dicts
                ]
                if args.dry_run:
                    _print_dry_run(tasks, cfg)
                else:
                    results = asyncio.run(orchestrate(tasks, cfg))
                    print_summary(results)
            else:
                print("  No tasks discovered. Sleeping...")

            print(f"\n  Next cycle in {loop_minutes} minutes...")
            time.sleep(loop_minutes * 60)
    else:
        # ── Single auto run ──
        _git_pull()
        task_dicts = asyncio.run(discover_all(cfg, sources))
        if not task_dicts:
            print("No tasks discovered.")
            sys.exit(0)

        tasks = [
            Task(
                id=t["id"],
                title=t["title"],
                prompt=t["prompt"],
                agent=AgentKind(t.get("agent", args.agent)),
            )
            for t in task_dicts
        ]
        _execute_tasks(tasks, cfg, args.dry_run)


def _execute_tasks(tasks: list[Task], cfg: OrchestratorConfig, dry_run: bool):
    """Execute a list of tasks (shared by manual and auto modes)."""
    if dry_run:
        _print_dry_run(tasks, cfg)
        return

    results = asyncio.run(orchestrate(tasks, cfg))
    print_summary(results)

    failed = [t for t in results if t.status == TaskStatus.FAILED]
    sys.exit(1 if failed else 0)


def _print_dry_run(tasks: list[Task], cfg: OrchestratorConfig):
    """Print what would execute without running anything."""
    print("\n--- DRY RUN ---\n")
    for t in tasks:
        cmd = build_command(t, cfg)
        print(f"  [{t.id}] {t.title}")
        print(f"    agent: {t.agent.value}")
        print(f"    branch: {t.branch_name}")
        if t.agent == AgentKind.CODEX:
            print(f"    worktree: {codex_worktree_path(t, cfg)}")
        preview = [_preview_arg(arg) for arg in cmd[:-1]]
        preview.append("<prompt>")
        print(f"    cmd: {' '.join(preview)}")
        print()


def _preview_arg(arg: str) -> str:
    """Compact long command arguments for dry-run output."""
    if "\n" in arg:
        return "<multiline>"
    if len(arg) > 120:
        return f"{arg[:117]}..."
    return arg


def _git_pull():
    """Pull latest main before discovering tasks, to avoid stale state."""
    try:
        subprocess.run(
            ["git", "fetch", "origin", "main"],
            capture_output=True,
            cwd=str(Path(__file__).resolve().parent.parent),
            timeout=30,
        )
    except Exception:
        pass  # Non-fatal — discovery works on whatever state we have


if __name__ == "__main__":
    main()
