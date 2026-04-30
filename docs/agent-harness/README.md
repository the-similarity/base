# Agent Harness

This directory is the operating manual for agent-first development in The
Similarity. It turns human taste, workflow expectations, and quality gates into
versioned artifacts that Codex and Claude workers can inspect, update, and
validate.

## Start Here

- `operating-model.md` — how humans steer and agents execute.
- `agent-legibility.md` — what must be visible to agents before work scales.
- `quality-scorecard.md` — current harness maturity and gaps.
- `golden-principles.md` — durable constraints that should become tooling.
- `exec-plans/` — versioned execution plans for non-trivial work.
- `templates/exec-plan-template.md` — copy this for complex initiatives.

## Agent Workflow

1. Read this file, then open only the linked file that matches the task.
2. Use `exec-plans/active/` for multi-step work that spans more than one PR.
3. Update `quality-scorecard.md` when a task materially changes harness quality.
4. Run `python scripts/check_agent_harness.py` before opening harness-related PRs.

## Boundaries

- Do not duplicate all project rules here; `CLAUDE.md` remains the root map.
- Do not edit `obsidian_thesim/_MOC.md`; durable wiki updates belong in
  `obsidian_thesim/concepts/` or `obsidian_thesim/topics/`.
- Avoid shared hot files in parallel worker tasks: `.gitignore`, `CHANGELOG.md`,
  and `pyproject.toml`. Note needed changes in PR descriptions unless the task
  explicitly owns that file.
- Do not encode aspirational rules as prose forever. If a rule catches recurring
  drift, promote it into a script, test, lint, or CI check.
