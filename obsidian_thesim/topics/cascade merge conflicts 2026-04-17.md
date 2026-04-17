# Cascade merge conflicts in parallel agent development (2026-04-17)

Topic note on cascade merge conflicts encountered during
[[batch1 platform spine 2026-04-17|Batch 1]].

Related: CLAUDE.md "Shared-file conflict prevention" and "Merge discipline"
sections document the rules that emerged from this experience.

## What happened

Batch 1 dispatched 5 feature agents in parallel. All 5 touched the same
files:

- `the_similarity/platform/__init__.py` (re-exports)
- `the_similarity/platform/artifacts.py` (enum extensions)
- `the_similarity/platform/artifacts_schema.json` (enum arrays)

The first PR merged cleanly. The second required a rebase to resolve
conflicts created by the first merge. The third required a rebase that
incorporated changes from both prior merges. By the fourth and fifth PRs,
the conflicts were compounding and each rebase was non-trivial.

## Why this happens

Worktree isolation guarantees no *runtime* interference between agents, but
it does not prevent *merge-time* interference. When multiple agents modify
the same lines in the same files, each merge to main invalidates the diff
of every remaining PR. The conflict surface grows quadratically with the
number of agents touching shared files.

## Strategies that work

### 1. Strict merge order with rebases
Merge PRs in dependency order. After each merge, rebase remaining PRs
against the updated main before merging the next. This is correct but
sequential — it eliminates the parallelism benefit for the shared-file
portions.

### 2. Consolidation branch
When conflicts cascade past 2-3 PRs, stop merging individually. Create a
consolidation branch, cherry-pick or merge all remaining PRs into it,
resolve conflicts once, and land the consolidated branch as a single PR.

### 3. Shared-file prohibition (preventive)
The best strategy is to prevent the problem. CLAUDE.md now lists known hot
files (`_MOC.md`, `.gitignore`, `CHANGELOG.md`, `pyproject.toml`,
`__init__.py` re-exports) and prohibits parallel agents from touching them.
Only one agent per batch may modify a shared file, or the orchestrator does
it post-merge.

### 4. One-agent-per-module rule
If a batch has N feature PRs that all extend the same module, assign the
shared-file edits (init re-exports, schema extensions, enum additions) to
exactly one agent. Other agents produce their module code but leave the
wiring to the designated agent or the orchestrator.

## What we added to CLAUDE.md

- "Shared-file conflict prevention" section listing hot files and the rule
  that only one agent per batch touches them.
- "Merge discipline" section: merge PRs as they land (not in batches), and
  if batch merging is unavoidable, merge in dependency order with conflict
  resolution between each merge.

## Lesson

Parallelism multiplies throughput only for independent work. For coupled
work (shared files, shared schemas), serial merge order or consolidation is
cheaper than N rounds of conflict resolution. Design the batch to maximize
independence — split by module boundary, not by feature slice.
