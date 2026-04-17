# The Similarity — Multi-Instance Coordination

## Git Workflow (MANDATORY)
1. **NEVER commit directly to `main`.** Always create a feature branch first.
2. Do NOT add Co-Authored-By trailers to commits.
3. **Commit granularly and continuously** — one logical change per commit, and create a commit after every meaningful completed step. Don't bundle unrelated changes or wait until the end of a long session to checkpoint work. A new method and its tests = one commit. A config change = separate commit. A documentation/comment pass = separate commit. This makes PRs easy to review, protects progress, and keeps `git bisect` useful.
4. When the task is DONE:
   ```bash
   python -m pytest the_similarity/tests/ -v          # all tests must pass
   git fetch origin main && git merge origin/main --no-edit  # catch up with main
   python -m pytest the_similarity/tests/ -v          # re-test after merge
   git push -u origin <branch-name>
   gh pr create --title "<type>: <summary>" --body "<description of changes>"
   ```
5. Share the PR URL with the user when done.

## Worktree-First Development (DEFAULT)
**Every task MUST run in an isolated worktree.** This is the default operating mode.

When the user gives you a task (or multiple tasks), spawn Agent subagents with `isolation: "worktree"`:
```
Agent(
  isolation: "worktree",
  prompt: "<full task description with context>",
  mode: "bypassPermissions"
)
```

Each worktree agent:
1. Gets its own copy of the repo with an auto-created branch
2. Does the work, writes tests, commits granularly
3. Runs `python -m pytest the_similarity/tests/ -v`
4. Pushes and opens a PR via `gh pr create`
5. The PR triggers `pr-gate.yml` → tests + lint + review-agent → auto-merge

**Parallel tasks = parallel worktree agents.** If the user gives you 5 tasks, spawn 5 worktree agents simultaneously. They cannot conflict because each has its own branch and working directory.

**When NOT to use a worktree:** Quick read-only questions, research, code review, planning, or anything that doesn't produce commits. Only the orchestrator session (this one) skips worktrees.

## Orchestrator (`orchestrator/`)
Autonomous task execution pipeline. Three modes:

```bash
# Manual: you write the tasks
cp orchestrator/tasks.example.yaml orchestrator/tasks.yaml
python orchestrator/run.py

# Autonomous: discovers tasks from GitHub issues, codebase TODOs, and a planner agent
python orchestrator/run.py --auto

# Continuous: discover + execute in a loop every 30 minutes
python orchestrator/run.py --auto --loop 30
```

Options:
```bash
--max-parallel 10           # concurrent worktree agents (default: 5)
--model opus                # use opus for complex tasks
--sources issues,codebase   # pick discovery sources (issues, codebase, planner)
--dry-run                   # preview without executing
```

Discovery sources (`--auto`):
1. **GitHub Issues** — open issues labeled `auto` or `agent`
2. **Codebase scan** — TODOs/FIXMEs, untested methods, ruff lint errors
3. **Planner agent** — Claude analyzes the repo and proposes up to 5 tasks

Pipeline: discover → worktree agents → commit + PR → pr-gate (tests + lint + review-agent) → auto-merge → branch-reaper cleanup. Results in `orchestrator/results/`.

## Active Worktrees (persistent)
| Directory | Scope | What goes here |
|-----------|-------|----------------|
| `Projects/14` | main | **Orchestrator** — coordination, task dispatch, planning |
| `Projects/14-front` | frontend | `the-similarity-app/` — Next.js UI |
| `Projects/14-backend` | backend | `the-similarity-api/`, `the_similarity/` — API + engine |
| `Projects/14-data` | data | `the-similarity-data/` — datasets, pipelines |
| `Projects/14-playground` | jupyter | `the-similarity-playground/` — Jupyter notebooks |

Temporary worktrees are created automatically by the Agent tool and cleaned up after merge.

## Parallel Development Rules
- Multiple Claude Code instances and worktree agents run at the same time.
- Each instance works in its OWN worktree directory. Never touch another worktree.
- Do NOT modify files outside your scope — ask the user if you need to.
- If you encounter merge conflicts, stop and tell the user.
- The orchestrator (Projects/14) dispatches work but does not make code changes directly — it spawns worktree agents for that.

### Shared-file conflict prevention
When multiple agents run in parallel, they WILL conflict on files that every agent edits. Known hot files:
- **`obsidian_thesim/_MOC.md`** — DO NOT edit from worktree agents. The orchestrator does one consolidated MOC update after all PRs merge.
- **`.gitignore`** — only one agent per batch should touch it; others note what they need added in their PR description.
- **`CHANGELOG.md`**, **`pyproject.toml`** — same rule: only one agent modifies, or the orchestrator does it post-merge.

### Merge discipline
- **Merge PRs as they land, not in batches.** Each merge changes main, creating cascading conflicts for later PRs. The orchestrator should merge each PR immediately when its agent finishes, not queue them all for a batch merge at the end.
- If batch merging is unavoidable, merge in dependency order and resolve MOC/shared-file conflicts between each merge.

## Tests
- 754 tests across 54 test files. All must pass before shipping.
- Test command: `python -m pytest the_similarity/tests/ -v`
- Slow tests: `python -m pytest the_similarity/tests/ -v -m slow` (integration backtester tests)

## CI Correctness (MANDATORY)

Three rules that prevent silent main breakage:

1. **Before `gh pr create`, run `scripts/ci_local.sh`.** This is the ONLY reliable signal that CI will pass. Local `pytest` in a polluted dev env lies — it picks up packages installed in past sessions that aren't in `pyproject.toml`. Never claim a PR is green without this script passing.

2. **Never merge on local-green alone.** Before merging a PR, poll `gh pr view <N> --json statusCheckRollup` and require every check (Python Tests, Python Lint, Data Package Tests, Frontend Tests) to be `SUCCESS`. The orchestrator is the one enforcement point; agents cannot self-merge without the gate.

3. **Main health is monitored.** `.github/workflows/main-health.yml` runs the full suite on main after every merge and daily at 07:00 UTC. If it opens an issue labeled `main-health-failure`, stop all parallel work until it's green again — merging new PRs on top of a red main compounds debt.

## Architecture

### Engine core
- `the_similarity/config.py` — All hyperparameters. Default: all 9 methods active. Includes confidence_decay_rate, koopman_blend_weight.
- `the_similarity/api.py` — Public API: load(), search(), project(), ensemble_project(), plot(), cross_timeframe_search(), backtest()
- `the_similarity/core/matcher.py` — Full 9-method tiered pipeline (SAX+MASS prefilter → DTW+Pearson → Tier 2 enrichment)
- `the_similarity/core/scorer.py` — ScoreBreakdown (9 fields), MatchResult, dynamic weight renormalization
- `the_similarity/core/projector.py` — Weighted quantile forecast cone with confidence decay + Koopman blend
- `the_similarity/core/backtester.py` — Walk-forward backtester with hit_rate, calibration, CRPS
- `the_similarity/core/feature_store.py` — SQLite-backed cache for Tier 2 methods (opt-in via feature_store param)
- `the_similarity/core/metrics.py` — Backtest evaluation metrics (hit_rate, MAE, calibration, CRPS)
- `the_similarity/core/` — Shared utilities (normalizer, windower, projector, embedding, regime, erosion)

### Methods (`the_similarity/methods/`)
- One file per method: bempedelis, bempedelis_2d, dtw, sax, matrix_profile, wavelet_leaders, wavelet_leaders_2d, koopman, emd, emd_2d, tda, transfer_entropy

### Intelligence layer (Phase 7)
- `the_similarity/core/ensemble.py` — Ensemble forecasting (Monte Carlo, regime-conditional, conformal)
- `the_similarity/core/strategy.py` — Strategy builder
- `the_similarity/core/portfolio.py` — Portfolio scanner
- `the_similarity/core/alerts.py` — Alert system
- `the_similarity/core/explainer.py` — Match explainability
- `the_similarity/core/auth.py` — Authentication

### Platform layer (`the_similarity/platform/`)
- `contracts.py` — Unified platform contracts: RunRecord, ArtifactRecord, ScorecardSummary, Provenance, ScenarioSpec, DatasetSpec + enums (RunKind, RunStatus, ScorecardKind)
- `artifacts.py` — RunArtifact on-disk format + RunKind enum + read/write helpers
- `artifacts_schema.json` / `platform_schema.json` — Draft-07 JSON schemas for TS consumers
- `registry.py` — SQLite-backed RunRegistry (WAL mode): runs, artifacts, scorecards, scenarios, datasets tables. CRUD + filters + cascade delete.
- `adapters/` — `finance.py` (backtest → RunRecord), `copies.py` (run dir → RunRecord), register into registry
- `api/` — Standalone FastAPI surface over registry (port 8787): /healthz, /runs, /runs/{id}/artifacts, /compare, etc.
- `__main__.py` — CLI: `python -m the_similarity.platform list/show/compare`

### Synthetic data (`the_similarity/synthetic/`)
- `contracts.py` — SyntheticDataset, Provenance, FidelityReport, PrivacyReport, UtilityReport, Scorecard
- `copies.py` — BlockBootstrapGenerator, RegimeBlockBootstrapGenerator
- `fidelity.py` — FidelityScorecard (KS, Wasserstein, ACF/PACF, tails, CVaR)
- `privacy.py` — PrivacyScorecard (DCR, memorization, membership-inference proxy)
- `utility.py` — UtilityScorecard (TRTS/TSTR Ridge forecasting, transfer gap)
- `cli.py` — `python -m the_similarity.synthetic.cli --input --n --seed --out [--register] [--strict]`
- `demos/` — sample.csv fixture + README

### Customer-facing API (`the-similarity-api/app/`)
- `main.py` — FastAPI app: search, dashboard, auth, alerts + platform routes
- `platform_routes.py` — `/platform/*` endpoints (runs, artifacts, scorecards, scenarios, datasets CRUD)
- `settings.py` — Registry DB path resolution

### Synthetic worlds (`the-similarity-fractal/`)
- `src/sim/headless/runner.js` — Headless world runner, JSONL telemetry output, `--register` flag
- `src/eval/` — Sweep runner, regime coverage, controllability (permutation p-values)
- `src/platform/registry-client.js` — HTTP client for registering world runs
- `scenarios/small_village.json` — 20-agent 64x64 torus scenario

### TradingView Pine Script mirror (`tradingview/`)
- `tradingview/similarity_indicator.pine` — Indicator: analogue search + weighted top-K forecast cone
- `tradingview/similarity_strategy.pine` — Strategy: P50 signals, P10/P75 exits, professional risk layer (ATR pads, time stops, HTF filter)
- `the_similarity/core/pine_mirror.py` — Python↔Pine parity utilities

### 3D visualization
- `the_similarity/core/terrain_generator.py` — Fractal terrain engine
- `the_similarity/core/terrain_params.py` — Terrain configuration

### CI / Infrastructure
- `.github/workflows/pr-gate.yml` — PR tests + lint + review agent + auto-merge
- `.github/workflows/main-health.yml` — Daily + post-merge clean-install test on main
- `.github/workflows/branch-reaper.yml` — Automated stale branch cleanup
- `.github/workflows/ci.yml` — Core CI pipeline
- `.github/workflows/refresh-data.yml` — Daily data refresh via GitHub Actions
- `scripts/ci_local.sh` — Throwaway-venv CI mirror for agents (MANDATORY before PR)
- `scripts/smoke_platform_spine.sh` — End-to-end platform smoke test

### Other
- `the_similarity/viz/` — Plotting (plotter.py)
- `the_similarity/contracts/` — Data contracts
- `the_similarity/io/` — I/O utilities
- `vision/` — Product vision and roadmap docs

## Current State (Phase 1-7 + Platform Spine)
- All 9 methods + 2D variants (bempedelis_2d, emd_2d, wavelet_leaders_2d)
- Tiered pipeline: SAX+MASS prefilter → DTW+Pearson → Tier 2 enrichment → final rank
- Ensemble forecasting: Monte Carlo, regime-conditional, conformal
- Strategy builder, portfolio scanner, alerts, auth, explainability
- TradingView Pine Script mirror with full strategy (indicator + strategy)
- Fractal terrain 3D engine with FPS controls
- Obsidian research wiki (`obsidian_thesim/`) for LLM-maintained knowledge base
- 1.13M+ rows of data, daily refresh via GitHub Actions
- Next.js frontend with lightweight-charts, resizable split pane
- Platform Spine (Batch 1) shipped 2026-04-17: unified contracts, registry, API, adapters for finance/copies/worlds
- Synthetic data pipeline: block-bootstrap generation, fidelity/privacy/utility scorecards, CLI with registry integration
- CI correctness infrastructure: main-health workflow, ci_local.sh throwaway-venv gate, platform smoke tests
- Next: Batch 2 (Finance Operating Product)

## Coding Standards
- **Claude Code Documentation Standard (MANDATORY)**:
  - DO NOT use informal "AI AGENT NOTES".
  - DO use formal Python, multi-line `"""..."""` block docstrings.
  - **Invariants and Lifecycles**: Explicitly document class/module lifecycles, state durability, and fail-closed edge cases.
  - **Architectural Guardrails & "Why"**: Use deep inline `#` comments to explain memory impact, thread handling (e.g. GIL release), and performance constraints.
  - **Immutability Notes**: Clearly state what is mutable, what must be idempotent, and strict boundaries.
  - **Mathematical Formulations**: Convert abstract algorithmic descriptions into rigorous mechanistic constraints (e.g., optimization limits, array dimensionality boundaries).
  - COMMENT everything in code so well (inside the code, not in separate files) BECAUSE it will be AI agents reading the code later.

# gstack

Use the `/browse` skill from gstack for all web browsing. Never use `mcp__claude-in-chrome__*` tools.

## Obsidian Knowledge Base — MANDATORY (`obsidian_thesim/`)

The vault **`obsidian_thesim/`** is the project’s **single source of truth for durable knowledge**. Every agent (interactive sessions, worktree agents, orchestrator workers) MUST update it when producing knowledge that has future reuse value. Full conventions: `.claude/OBSIDIAN_KB.md`.

### When to write to the vault (MANDATORY)

| Trigger | What to write | Where |
|---------|--------------|-------|
| **New method or module added** | Concept note explaining what it does, why, key parameters, tradeoffs | `obsidian_thesim/concepts/<method>.md` |
| **Bug fix with non-obvious root cause** | "What broke and why" note so future agents don’t repeat it | `obsidian_thesim/topics/<topic>.md` |
| **Architecture decision** | Decision record: what was decided, alternatives considered, why | `obsidian_thesim/topics/<decision>.md` |
| **Research or paper ingested** | Summary + key claims + limitations in compiled note, raw in `raw/` | `obsidian_thesim/research/` |
| **New data source or pipeline** | Data card: source, schema, refresh cadence, quirks | `obsidian_thesim/concepts/<source>.md` |
| **Config change with non-obvious rationale** | Why this value, what was tried, what broke | Update relevant concept note |
| **Test insight** | Edge case discovered, calibration finding, performance benchmark | Update relevant concept note or new topic |

### How to write

1. Use `[[wikilinks]]` to cross-link related concepts, methods, and code paths.
2. Use real relative paths from repo root when referencing code (e.g. `the_similarity/core/matcher.py`).
3. **DO NOT update `obsidian_thesim/_MOC.md`** — the orchestrator or human will do a single consolidated MOC update after merging. Parallel agents editing the same MOC line always causes merge conflicts.
4. Keep notes concise — aim for "what would a new agent need to know in 60 seconds."
5. Consolidate, don’t duplicate — check if a note already exists before creating a new one.

### When NOT to write

- Pure mechanical changes (rename, formatting, dependency bump) — the git log covers these.
- Information already in code docstrings — don’t duplicate, link instead.
- Ephemeral debugging notes — these die with the session.

### Vault structure
```
obsidian_thesim/
├── _MOC.md                    # Master index — update this when adding notes
├── concepts/                  # Method explainers, data cards, architecture
├── topics/                    # Cross-cutting topics, decisions, insights
├── research/                  # Paper summaries, literature reviews
│   └── full-text/notes/       # Detailed paper notes
├── raw/                       # Unprocessed clippings, PDFs, images
├── outputs/                   # Generated artifacts (diagrams, slides)
├── Engineers start here.md    # Onboarding entry point
└── *.md                       # Top-level explainers for non-technical readers
```

## Available skills

- `/plan-ceo-review` — CEO/founder-mode plan review
- `/plan-eng-review` — Eng manager-mode plan review
- `/review` — Pre-landing PR review
- `/ship` — Ship workflow (merge, test, review, bump, push, PR)
- `/browse` — Fast headless browser for QA testing and site dogfooding
- `/qa` — Systematic QA testing of web applications
- `/setup-browser-cookies` — Import cookies from your real browser for authenticated testing
- `/retro` — Weekly engineering retrospective
