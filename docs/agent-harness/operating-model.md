# Agent Operating Model

The Similarity treats agent work as a controlled production system. Humans
choose goals, constraints, acceptance criteria, and merge sequencing. Agents do
the implementation, testing, documentation, and PR mechanics inside isolated
worktrees.

## Roles

- Humans define intent, prioritize work, review judgment-heavy tradeoffs, and
  decide when to expand or tighten the harness.
- Agents execute scoped tasks, gather context from the repo, write code and
  tests, run checks, open PRs, and update durable knowledge.
- The orchestrator assigns independent work, prevents shared-file conflicts,
  records results, and keeps throughput from overwhelming review attention.

## Default Loop

1. Convert user intent into small, independently mergeable tasks.
2. Assign each task to an isolated Claude or Codex worker.
3. Require each worker to validate locally before opening a PR.
4. Merge PRs as they land, not in a batch.
5. Convert recurring failure patterns into docs, scripts, lints, or tests.

## Local Agent Fleet

Use `scripts/agent_fleet.py` as the local cockpit for worktrees, terminals,
tasks, previews, and cleanup.

Create the standard three-Codex, three-Claude worktree fleet with:

```bash
scripts/agent_fleet.py setup --codex 3 --claude 3 --link-node-modules
```

This creates `../14-codex-1` through `../14-codex-3` and `../14-claude-1`
through `../14-claude-3`, each on its own branch. The `--link-node-modules`
flag avoids duplicating frontend dependencies when `package-lock.json` matches
the main worktree.

Open agent sessions automatically:

```bash
scripts/agent_fleet.py launch --codex 3 --claude 3 --terminal tmux --link-node-modules
```

Supported launchers:

- `--terminal tmux` — one tmux window per agent.
- `--terminal iterm` — one iTerm tab per agent.
- `--terminal ghostty` — one Ghostty window per agent.
- `--terminal print` — print copy-paste commands only.

Useful management commands:

```bash
scripts/agent_fleet.py status --codex 3 --claude 3
scripts/agent_fleet.py tasks --codex 3 --claude 3 --out orchestrator/tasks.yaml
scripts/agent_fleet.py preview --codex 3 --claude 3
scripts/agent_fleet.py clean --codex 3 --claude 3
```

`clean` should only run after PRs are merged or intentionally abandoned. Use
`--force` only when throwing work away.

## When Agents Struggle

Do not simply retry with a louder prompt. Ask which capability is missing:

- Context: add or update repo-local documentation.
- Feedback: add a test, smoke check, log query, or UI validation path.
- Boundary: add a structural rule or lint.
- Tooling: expose the app, data, logs, or metrics in a way agents can inspect.
- Task shape: split the work into smaller execution plans.

## Merge Philosophy

Throughput is useful only when corrections are cheap and visible. Keep PRs
small, merge continuously, and prefer follow-up cleanup PRs over long-lived
branches that accumulate conflicts.
