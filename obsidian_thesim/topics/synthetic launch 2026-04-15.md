# Synthetic launch 2026-04-15

Decision record for the one-day build of the synthetic data lane. Two runnable products (Copies + Worlds) and a shared Eval scaffold, landed on `main` in ~2.5 hours of wall clock via 14 parallel worktree agents across two waves.

## What shipped

- **Copies lane** — [[synthetic contracts]] · [[block_bootstrap_generator]] · [[fidelity_scorecard]] · [[privacy_scorecard]] · [[utility_scorecard]] · CLI (`the_similarity/synthetic/cli.py`) · tests (`the_similarity/tests/test_synthetic_*.py`).
- **Worlds lane** — [[synthetic worlds runner]] · [[synthetic worlds eval]].
- **Docs** — `vision/synthetic_data_platform.md`, `vision/synthetic_copies_worlds_eval_mvp.md`, `vision/synthetic_worlds_eval.md`, `vision/launch_memo_2026-04-15.md`.
- **Demo fixtures** — `the_similarity/synthetic/demos/sample.csv` (500-row deterministic seed), `the-similarity-fractal/scenarios/small_village.json`.

## Key architecture decisions

1. **Contracts first.** The contract PR (#126) landed before any downstream agent started. Field names were broadcast to the other 5 agents by name so they could code against specific attributes instead of guessing. This is what made 10 parallel agents coherent.
2. **Block bootstrap over Gaussian copula.** The spec originally named Gaussian copula as the MVP generator. We shipped block bootstrap + regime-aware block bootstrap because they were fastest to ship realistically with proper seeded determinism and multi-series support. Spec was patched in PR #137 to match reality; copula is a named follow-up.
3. **Privacy is heuristic, not formal.** DCR + dupes + distance-to-synth AUC proxy. Documented plainly. Not a compliance claim. See [[privacy_scorecard]].
4. **Worlds runner decoupled from renderer.** Headless JSONL output only. Enables deterministic sweeps and CI-friendly eval. See [[synthetic worlds runner]].
5. **CLI default exit is loose.** `passed={T|F}` banner always prints; exit code is 0 on artifact write. `--strict` gates exit code on the scorecard. This separates "pipeline ran" from "quality bar met" — crucial for demos.

## Non-obvious findings during the run

- **Shared-worktree isolation incidents.** Two agents (fidelity, utility) reported finding other agents' branches/commits in their checkouts mid-session. Recovered via reflog. Flagged as a harness-level concern — `isolation: "worktree"` should guarantee separate temp dirs. Not reproduced on the polish wave.
- **CLI lazy-import bug.** The CLI agent used placeholder module name `the_similarity.synthetic.generators` in its lazy imports. The actual module is `.copies`. Caught on first smoke after merge; fixed in PR #136. Lesson: lazy imports guard against missing modules, but guessing the name still lets you ship broken code. Verify names from the actual merged contract, not the task brief.
- **Generator name divergence.** Class names and `Provenance.generator_name` use snake_case (`block_bootstrap`), but the CLI initially accepted dash-kebab (`block`, `regime-block`). Normalized in PR #138 before artifacts accumulated with the old prefix.

## Honest limits

- One world scenario, one biome. Need a second dynamics profile to prove the eval scaffold isn't overfit to `small_village`.
- Scorecard thresholds are guesses (0.7 / 0.6 / 0.3). Not calibrated on real reference pairs yet.
- Privacy attacks are cheap proxies. Needs a real shadow-model MIA before any external claim.
- Univariate utility bench only. Multi-series lift is easy; just not done.

## What's next

1. Gaussian copula generator (the missing spec promise).
2. Calibrate thresholds on known-good/known-bad reference pairs.
3. Second world scenario (e.g. `queue.mm1` from the original spec draft).
4. Real privacy attack (shadow-model MIA minimum).
5. Dataset card renderer driven by `Provenance`.
6. Consolidated `_MOC.md` update (deferred to orchestrator per CLAUDE.md).

## PR ledger

- Wave 1 (MVP): #126–#135, plus fix #136.
- Wave 2 (polish): #137 spec patch, #138 naming normalization, #139 demos + fixture, #140 `--strict` flag.

See [[../../vision/launch_memo_2026-04-15.md|launch memo]] for the external-facing write-up.
