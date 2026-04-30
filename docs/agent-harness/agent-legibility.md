# Agent Legibility

Agents can only reason about what they can inspect during a run. Any important
decision, invariant, data shape, workflow, or operational signal that lives only
in a chat thread or a human memory is invisible to the system.

## Current Legibility Surfaces

- `CLAUDE.md` maps the repo, workflow, and shared-file rules.
- `docs/` stores architecture, planning, design, theory, and reference docs.
- `obsidian_thesim/` stores durable concept and topic notes.
- `orchestrator/` runs parallel worktree agents and records results.
- `scripts/ci_local.sh` gives workers a clean-room CI mirror.
- `scripts/preview_worktree.sh` boots a worktree-local API and UI preview on
  isolated ports before merge.

## Worktree Preview

Run one worktree before merging UI/API-facing PRs:

```bash
scripts/preview_worktree.sh <worktree-path> <slot>
```

Run the preview fleet dashboard for multiple agent worktrees:

```bash
scripts/preview_fleet.py
```

Then open:

```text
http://localhost:3999
```

Slot numbers map to ports so multiple demos can run at once:

- Slot `1` → API `8001`, UI `3001`
- Slot `2` → API `8002`, UI `3002`
- Slot `6` → API `8006`, UI `3006`

## Local Review Gate

The preferred deployment path is:

1. Agent worktree opens a PR.
2. Preview that worktree locally on its assigned `localhost:300X` port.
3. Review behavior in the dashboard.
4. Merge approved PRs into staging.
5. Deploy to Vercel only after staging passes local review and CI.

## Target Legibility Surfaces

- Agent-readable smoke checks for critical UI and API journeys.
- Local logs and metrics that can be queried from a worker task.
- Generated references for schemas, API routes, platform contracts, and data
  catalogs.
- Quality scorecards that make known gaps explicit and mechanically checked.

## Rule Of Thumb

If a new engineer would need it during onboarding, an agent needs it in the
repository. Prefer short maps that point to focused sources of truth over large
instruction blobs.

## Promotion Path

1. Capture new knowledge in the smallest durable doc.
2. Cross-link it from the relevant index.
3. Add a checker when stale or missing knowledge would cause real drift.
4. Move repeated remediation instructions into the checker error message.
