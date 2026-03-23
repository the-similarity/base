# The Similarity — Multi-Instance Coordination

## Git Workflow (MANDATORY)
1. **NEVER commit directly to `main`.** Always create a feature branch first.
2. You are running inside a **git worktree**. Stay in your worktree directory — do NOT `cd` into other worktrees.
3. To start a new task, create a feature branch **within your worktree**:
   ```bash
   git checkout -b feat/<descriptive-name>
   ```
   This is safe because each worktree is isolated — your branch switch doesn't affect other worktrees.
4. **Commit granularly** — one logical change per commit. Don't bundle unrelated changes. A new method and its tests = one commit. A config change = separate commit. This makes PRs easy to review and `git bisect` useful.
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
- 315 tests across 28 test files. All must pass before shipping.
- Test command: `python -m pytest the_similarity/tests/ -v`
- Slow tests: `python -m pytest the_similarity/tests/ -v -m slow` (integration backtester tests)

## Architecture
- `the_similarity/core/matcher.py` — Full 9-method tiered pipeline (SAX+MASS prefilter → DTW+Pearson → Tier 2 enrichment)
- `the_similarity/config.py` — All hyperparameters. Default: all 9 methods active. Includes confidence_decay_rate, koopman_blend_weight.
- `the_similarity/core/scorer.py` — ScoreBreakdown (9 fields), MatchResult, dynamic weight renormalization
- `the_similarity/core/projector.py` — Weighted quantile forecast cone with confidence decay + Koopman blend
- `the_similarity/core/backtester.py` — Walk-forward backtester with hit_rate, calibration, CRPS
- `the_similarity/core/feature_store.py` — SQLite-backed cache for Tier 2 methods (opt-in via feature_store param)
- `the_similarity/core/metrics.py` — Backtest evaluation metrics (hit_rate, MAE, calibration, CRPS)
- `the_similarity/api.py` — Public API: load(), search(), project(), plot(), backtest()
- `the_similarity/methods/` — One file per method (bempedelis, dtw, sax, matrix_profile, wavelet_leaders, koopman, emd, tda, transfer_entropy)
- `the_similarity/core/` — Shared utilities (normalizer, windower, projector, embedding, regime)

## Current State (Phase 1-4 complete, 5a done)
- All 9 methods implemented and tested (DTW, Pearson, SAX, Matrix Profile, Bempedelis, Koopman, Wavelet, EMD, TDA, Transfer Entropy)
- Tiered pipeline: SAX+MASS prefilter → DTW+Pearson → Tier 2 enrichment (7 methods) → final rank
- Koopman forward evolution with eigenvalue clamping
- Forecast cone with confidence decay + Koopman blend
- Walk-forward backtester with CRPS, calibration, hit rate
- SQLite FeatureStore for caching expensive Tier 2 computations

# gstack

Use the `/browse` skill from gstack for all web browsing. Never use `mcp__claude-in-chrome__*` tools.

## Available skills

- `/plan-ceo-review` — CEO/founder-mode plan review
- `/plan-eng-review` — Eng manager-mode plan review
- `/review` — Pre-landing PR review
- `/ship` — Ship workflow (merge, test, review, bump, push, PR)
- `/browse` — Fast headless browser for QA testing and site dogfooding
- `/qa` — Systematic QA testing of web applications
- `/setup-browser-cookies` — Import cookies from your real browser for authenticated testing
- `/retro` — Weekly engineering retrospective
