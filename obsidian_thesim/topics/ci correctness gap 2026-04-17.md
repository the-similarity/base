# CI correctness gap (2026-04-17)

Topic note on the CI correctness gap discovered during
[[batch1 platform spine 2026-04-17|Batch 1]].

## What happened

Worktree agents reported "683 tests pass" locally but CI failed on clean
install. Multiple PRs were shipped with false-green local signals before
anyone noticed the CI gate was red.

## Root cause

**Polluted local dev environments + missing pyproject.toml declarations.**

Local development environments accumulate packages over time — `sklearn`,
`fastapi`, `uvicorn`, `httpx`, `pyarrow` were all installed in past sessions
but never declared as runtime dependencies in `pyproject.toml`. Local
`pytest` picks them up from the ambient env and passes. CI creates a fresh
venv with only declared deps and fails on import.

Agents cannot distinguish "my test passed because the code is correct" from
"my test passed because my env is polluted." They will confidently report
green.

## The poetry extras gotcha

An additional wrinkle: some deps were listed in `[tool.poetry.extras]`
(under an `api` extra group) but poetry-core strips extras from PEP 517
core metadata. So even `pip install -e .` skipped them unless
`pip install -e ".[api]"` was used explicitly. The fix was to remove the
redundant `api` extra and keep all runtime deps in the main
`[tool.poetry.dependencies]` section.

## Fix

Three measures landed in PR #154:

1. **`scripts/ci_local.sh`** — creates a throwaway venv, installs from
   `pyproject.toml` only, runs the full test suite, then deletes the venv.
   This mirrors what CI does. Agents and humans must run this before claiming
   a PR is green.

2. **`.github/workflows/main-health.yml`** — runs the full suite on `main`
   after every merge and daily at 07:00 UTC. If it fails, it opens an issue
   labeled `main-health-failure`. All parallel work stops until main is green
   again.

3. **CLAUDE.md "CI Correctness" section** — three mandatory rules: run
   `ci_local.sh` before PR creation, never merge on local-green alone, stop
   work if main-health is red.

## Lesson for future agents

- **Never trust local `pytest` as proof of CI-readiness.** The only reliable
  signal is `scripts/ci_local.sh` or the actual CI check on the PR.
- When adding a new import, check whether the package is in
  `pyproject.toml` `[tool.poetry.dependencies]`. If not, add it there (not
  in extras).

See also: `scripts/ci_local.sh`, `.github/workflows/main-health.yml`,
CLAUDE.md "CI Correctness (MANDATORY)" section.
