# The Similarity — Multi-Instance Coordination

## Git Workflow (MANDATORY)
1. **NEVER commit directly to `main`.** Always create a feature branch first.
2. You are running inside a **git worktree**. Stay in your worktree directory — do NOT `cd` into other worktrees.
3. To start a new task, create a feature branch **within your worktree**:
   ```bash
   git checkout -b feat/<descriptive-name>
   ```
   This is safe because each worktree is isolated — your branch switch doesn't affect other worktrees.
4. **Commit granularly and continuously** — one logical change per commit, and create a commit after every meaningful completed step. Don't bundle unrelated changes or wait until the end of a long session to checkpoint work. A new method and its tests = one commit. A config change = separate commit. A documentation/comment pass = separate commit. This makes PRs easy to review, protects progress, and keeps `git bisect` useful.
5. When the task is DONE:
   ```bash
   python -m pytest the_similarity/tests/ -v          # all tests must pass
   git fetch origin main && git merge origin/main --no-edit  # catch up with main
   python -m pytest the_similarity/tests/ -v          # re-test after merge
   git push -u origin <branch-name>
   gh pr create --title "<type>: <summary>" --body "<description of changes>"
   ```
6. Share the PR URL with the user when done.
7. Do NOT add Co-Authored-By trailers to commits.

## Active Worktrees
| Directory | Scope | What goes here |
|-----------|-------|----------------|
| `Projects/14` | main | Main repo — coordination, engine core |
| `Projects/14-front` | frontend | `the-similarity-app/` — Next.js UI |
| `Projects/14-backend` | backend | `the-similarity-api/`, `the_similarity/` — API + engine |
| `Projects/14-data` | data | `the-similarity-data/` — datasets, pipelines |
| `Projects/14-playground` | jupyter | `the-similarity-playground/` — Jupyter notebooks |

## Parallel Development Rules
- Multiple Claude Code instances may be running at the same time.
- Each instance works in its OWN worktree directory. Never touch another worktree.
- Do NOT modify files outside your scope — ask the user if you need to.
- If you encounter merge conflicts, stop and tell the user.

## Tests
- 347 tests across 30 test files. All must pass before shipping.
- Test command: `python -m pytest the_similarity/tests/ -v`
- Slow tests: `python -m pytest the_similarity/tests/ -v -m slow` (integration backtester tests)

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

### TradingView Pine Script mirror (`tradingview/`)
- `tradingview/similarity_indicator.pine` — Indicator: analogue search + weighted top-K forecast cone
- `tradingview/similarity_strategy.pine` — Strategy: P50 signals, P10/P75 exits, professional risk layer (ATR pads, time stops, HTF filter)
- `the_similarity/core/pine_mirror.py` — Python↔Pine parity utilities

### 3D visualization
- `the_similarity/core/terrain_generator.py` — Fractal terrain engine
- `the_similarity/core/terrain_params.py` — Terrain configuration

### Other
- `the_similarity/viz/` — Plotting (plotter.py)
- `the_similarity/contracts/` — Data contracts
- `the_similarity/io/` — I/O utilities
- `vision/` — Product vision and roadmap docs

## Current State (Phase 1-7 complete)
- All 9 methods + 2D variants (bempedelis_2d, emd_2d, wavelet_leaders_2d)
- Tiered pipeline: SAX+MASS prefilter → DTW+Pearson → Tier 2 enrichment → final rank
- Ensemble forecasting: Monte Carlo, regime-conditional, conformal
- Strategy builder, portfolio scanner, alerts, auth, explainability
- TradingView Pine Script mirror with full strategy (indicator + strategy)
- Fractal terrain 3D engine with FPS controls
- Obsidian research wiki (`obsidian_thesim/`) for LLM-maintained knowledge base
- 1.13M+ rows of data, daily refresh via GitHub Actions
- Next.js frontend with lightweight-charts, resizable split pane

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

## Obsidian research wiki (`obsidian_thesim/`)

The vault **`obsidian_thesim/`** is the project’s **LLM-maintained research and learning base** (ingest → compiled markdown wiki → Obsidian as viewer). It also holds **engineering onboarding** notes (API snippets, matcher/config maps, tests) — start at **`obsidian_thesim/Engineers start here.md`**. Agents should **add and update notes** as research and coding produce durable insights. **Conventions and folder layout:** `.claude/OBSIDIAN_KB.md`. Cursor loads the same policy via `.cursor/rules/obsidian-knowledge-base.mdc`.

## Available skills

- `/plan-ceo-review` — CEO/founder-mode plan review
- `/plan-eng-review` — Eng manager-mode plan review
- `/review` — Pre-landing PR review
- `/ship` — Ship workflow (merge, test, review, bump, push, PR)
- `/browse` — Fast headless browser for QA testing and site dogfooding
- `/qa` — Systematic QA testing of web applications
- `/setup-browser-cookies` — Import cookies from your real browser for authenticated testing
- `/retro` — Weekly engineering retrospective
