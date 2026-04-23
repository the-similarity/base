"""
Orchestrator configuration.

Controls concurrency, retry policy, and claude CLI defaults.
"""

from dataclasses import dataclass, field
from pathlib import Path

# ── Root paths ──────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).resolve().parent.parent
TASKS_FILE = REPO_ROOT / "orchestrator" / "tasks.yaml"
RESULTS_DIR = REPO_ROOT / "orchestrator" / "results"

# ── Claude CLI binary ──────────────────────────────────────────────
CLAUDE_BIN = "claude"


@dataclass
class OrchestratorConfig:
    """
    Tunable knobs for the orchestrator.

    max_parallel: How many worktree agents run simultaneously.
                  Each agent is a separate claude CLI process with its own
                  git worktree. Memory cost is ~100MB per worktree (working
                  tree files) + ~200MB per claude process.
                  Safe range: 3-10. Beyond 10, git object-store lock contention
                  and API rate limits become the bottleneck.

    max_retries:  How many times to retry a task after review-agent rejection
                  or test failure. Each retry gets the previous error context
                  appended to the prompt so the agent can self-correct.

    timeout_minutes: Hard kill after this many minutes. Prevents runaway agents.
                     Most tasks should complete in 10-15 min. Set higher for
                     large refactors.

    model:        Claude model to use for worker agents. Sonnet is the default
                  for throughput. Switch to opus for complex architectural work.

    permission_mode: Claude CLI permission mode. "bypassPermissions" lets agents
                     run without interactive approval. Only safe in sandboxed
                     repos — this is a local dev repo, so it's fine.
    """

    max_parallel: int = 5
    max_retries: int = 1
    timeout_minutes: int = 30
    model: str = "sonnet"
    # bypassPermissions maps to --dangerously-skip-permissions which is blocked
    # when running as root. acceptEdits auto-approves file edits; bash and
    # other tools are covered via --allowed-tools in build_command.
    permission_mode: str = "acceptEdits"

    # Extra CLI flags passed to every claude invocation
    extra_flags: list[str] = field(default_factory=list)
