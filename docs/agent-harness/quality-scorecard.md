# Harness Quality Scorecard

This scorecard tracks how ready the repository is for long-running autonomous
agent work. Grades should move only when backed by concrete docs, scripts,
tests, or CI checks.

| Area | Grade | Evidence | Next Upgrade |
| --- | --- | --- | --- |
| Worktree isolation | B+ | `orchestrator/run.py` supports Claude and Codex workers. | Add cleanup/status commands for stale worker worktrees. |
| Local CI feedback | B | `scripts/ci_local.sh` mirrors core Python CI. | Include harness checks and app/package smoke checks. |
| Repo knowledge map | B- | `CLAUDE.md`, `docs/`, and `obsidian_thesim/` exist. | Shrink root instructions into a shorter map with indexed docs. |
| Execution planning | C+ | Planning docs exist, but active agent plans are not standardized. | Require `docs/agent-harness/exec-plans/active/` for complex work. |
| Architecture enforcement | C | Architecture docs exist. | Add structural lint rules for package/domain boundaries. |
| App legibility | C | Smoke scripts exist for some domains. | Make per-worktree app boot, UI journeys, logs, and metrics agent-readable. |
| Knowledge freshness | C | Durable notes are required by prompt. | Add doc freshness and cross-link checks. |
| PR feedback loop | C | Workers can open PRs and retries are recorded. | Automate review-comment fetching and fix loops. |

## Update Rules

- Update this file when adding or removing a harness capability.
- Keep grades conservative; prose without enforcement rarely deserves more than
  `C`.
- Link new evidence from this scorecard or from `README.md`.
