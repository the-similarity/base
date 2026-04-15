# Synthetic Data Platform — Internal Launch Memo

**Date:** 2026-04-15
**Author:** Buba (orchestrated via 14 parallel worktree agents across two waves)
**Audience:** Internal team

## TL;DR

The synthetic data lane exists today. Two runnable products — **Synthetic Copies** and **Synthetic Worlds** — plus a shared **Eval** scaffold, all landed on `main` in one afternoon. Spec matches implementation, CLI exit semantics are clean, demos are frozen, 66 synthetic tests green.

## What works today (verified live)

### Synthetic Copies — privacy-audited, realism-first dataset generator

```bash
python -m the_similarity.synthetic.cli \
  --input the_similarity/synthetic/demos/sample.csv \
  --n 500 --seed 42 --out artifacts/demo-copies
```

Produces `real.parquet`, `synth.parquet`, `scorecard.json`, `report.md`, `provenance.json` under `block_bootstrap-42-<ts>/`. Deterministic byte-for-byte across runs at the same seed. Scorecards are real, not stubs:

- **Fidelity** — KS, Wasserstein, mean/std/skew/kurt diffs per column; ACF/PACF deltas at lags [1, 5, 10]; cross-series correlation Frobenius diff; tail ratios (p01/p99) and CVaR differences.
- **Privacy** — DCR (distance to closest record) vs real-vs-real baseline; exact and near-duplicate counts; membership-inference AUC proxy from distance-to-synth as a one-dimensional score.
- **Utility** — Ridge one-step-ahead forecasting with lags 1..5; chronological 70/30 split; TRTS + TSTR + real-baseline MAE/RMSE/R²; transfer gap.

### Synthetic Worlds — controllable headless environments

```bash
cd the-similarity-fractal
npm run sim:headless -- \
  --scenario scenarios/small_village.json \
  --seed 42 --steps 500 --out artifacts/demo-worlds.jsonl
```

502-line JSONL: provenance header, 500 tick metrics (alive/dead/energy/food/deaths/eaten), summary totals + wall time. No renderer import. Deterministic across repeat runs, diverges on seed change.

### World Eval — sweep runner with real controllability statistics

```bash
node the-similarity-fractal/src/eval/run-example-sweep.js
```

Produces a `worlds` scorecard: 9-bin regime coverage (population × energy), permutation-tested effect sizes per (knob × metric). Validated signals on the example grid:

- `energy_decay → alive` r = -0.75, p = 0.002
- `energy_decay → cumulative_deaths` r = +0.75, p = 0.002
- `food_spawn_rate → food_count` r = +0.87, p = 0.002

These match physical intuition — faster metabolism kills more agents, more food spawn raises food stock.

## How to test it yourself

Five-minute end-to-end on a fresh clone:

```bash
# 1. Tests
python -m pytest the_similarity/tests/test_synthetic_cli.py \
  the_similarity/tests/test_synthetic_contracts.py \
  the_similarity/tests/test_synthetic_copies.py \
  the_similarity/tests/test_synthetic_fidelity.py \
  the_similarity/tests/test_synthetic_privacy.py \
  the_similarity/tests/test_synthetic_utility.py -v
# Expect: 66 passed.

# 2. Copies demo (deterministic fixture committed at the_similarity/synthetic/demos/sample.csv)
python -m the_similarity.synthetic.cli \
  --input the_similarity/synthetic/demos/sample.csv \
  --n 500 --seed 42 --out artifacts/demo-copies
# Inspect artifacts/demo-copies/block_bootstrap-42-*/report.md and scorecard.json
# Default exit is 0 on artifact write. Pass --strict to gate exit code on threshold pass.

# 3. Worlds demo
cd the-similarity-fractal
npm run sim:headless -- \
  --scenario scenarios/small_village.json \
  --seed 42 --steps 500 --out /tmp/demo-worlds.jsonl
head -1 /tmp/demo-worlds.jsonl | python -m json.tool   # provenance
tail -1 /tmp/demo-worlds.jsonl | python -m json.tool   # summary

# 4. World eval sweep
node src/eval/run-example-sweep.js
cat artifacts/sweep-example/sweep-example/scorecard.json | python -m json.tool | head -80
```

Determinism check: run the copies demo twice with `--seed 42` and diff the resulting `synth.parquet` — they must be byte-identical.

## What's honest

- **Privacy is heuristic auditing, not formal guarantees.** No differential privacy, no full membership-inference attack framework — DCR, dupe counts, and a distance-to-synth AUC proxy. The module docstring says so. Useful for catching gross leaks; not a compliance claim.
- **Copies generator is block bootstrap, not Gaussian copula.** Spec originally named copula; shipped moving-block + regime-aware block bootstrap because they were fastest to ship realistically. Spec was patched in PR #137 to match reality. Gaussian copula is a named follow-up.
- **Scorecard thresholds are arbitrary first-pass values** (fidelity ≥ 0.7, privacy ≥ 0.6, utility gap < 0.3). Not calibrated against real datasets yet. Default CLI exit is loose; `--strict` is opt-in CI gating.
- **One scenario, one world.** `small_village.json` on a 64×64 torus with 20 agents. Real physics (food, energy decay, death), but one biome of one size.

## What's next (priority order)

1. **Gaussian copula generator** — the missing MVP promise; unblocks cross-series dependence benchmarks.
2. **Calibrated thresholds** — run scorecards against known-good and known-bad reference pairs; set thresholds from percentiles, not guesses.
3. **Second world scenario** — a markedly different dynamics profile (e.g. `queue.mm1`) to prove the eval scaffold isn't shaped to one world.
4. **Real privacy attack** — at minimum a shadow-model MIA; at best a DP-SGD comparison baseline.
5. **Dataset cards** — when we share synthetic outputs, each needs a provenance-backed datasheet (source, seed, generator, scorecard summary). Provenance dataclass captures the fields; we need a renderer.
6. **Consolidated MOC update in `obsidian_thesim/`** — all agents deferred this to the orchestrator.

## What it cost

- **Wave 1 (MVP):** 10 parallel agents → PRs #126–#135 merged + 1 post-merge fix (#136).
- **Wave 2 (polish):** 4 parallel agents → PRs #137–#140 merged.
- Two shared-worktree incidents flagged during wave 1 (both recoverable via reflog).
- Wall clock: ~90 min build, ~30 min polish, ~30 min verification and memo.
- Net code: ~3,300 lines under `the_similarity/synthetic/` + TS worlds runner and eval.

## The wedge, one sentence each

- **Synthetic Copies:** generate privacy-audited, realism-first datasets for training, testing, and sharing.
- **Synthetic Worlds:** generate controllable headless environments for stress testing and agent/world-model evaluation.

The lane exists now.
