# The Similarity — Multi-Instance Coordination

## Git Workflow (MANDATORY)
1. **NEVER commit directly to `main`.** Always create a feature branch first.
2. At the START of any coding task:
   ```bash
   git checkout main && git pull origin main
   git checkout -b <descriptive-branch-name>
   ```
3. Commit often with clear messages as you work.
4. When the task is DONE:
   ```bash
   python -m pytest the_similarity/tests/ -v          # all tests must pass
   git fetch origin main && git merge origin/main --no-edit  # catch up with main
   python -m pytest the_similarity/tests/ -v          # re-test after merge
   git push -u origin <branch-name>
   gh pr create --title "<type>: <summary>" --body "<description of changes>"
   ```
5. Share the PR URL with the user when done.

## Parallel Development Rules
- Multiple Claude Code instances may be running at the same time.
- Each instance should only modify files in its assigned scope.
- Do NOT modify files outside your scope — ask the user if you need to.
- If you encounter merge conflicts, stop and tell the user.

## Tests
- 115 tests across 16 test files. All must pass before shipping.
- Test command: `python -m pytest the_similarity/tests/ -v`

## Architecture
- `the_similarity/core/matcher.py` — Full 9-method tiered pipeline (SAX+MASS prefilter → DTW+Pearson → Tier 2 enrichment)
- `the_similarity/config.py` — All hyperparameters. Default: all 9 methods active.
- `the_similarity/core/scorer.py` — ScoreBreakdown (9 fields), MatchResult, dynamic weight renormalization
- `the_similarity/api.py` — Public API: load(), search(), project(), plot()
- `the_similarity/methods/` — One file per method (bempedelis, dtw, sax, matrix_profile, wavelet_leaders, koopman, emd, tda, transfer_entropy)
- `the_similarity/core/` — Shared utilities (normalizer, windower, projector, embedding, regime)

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
