# Karpathy autoresearch and what it means for The Similarity

## Executive summary

In March 2026, Andrej Karpathy published `karpathy/autoresearch`, a deliberately small experiment in which an AI agent repeatedly modifies a bounded training file, runs a short experiment, keeps improvements, discards regressions, and logs results. The important idea is not the exact repo. The important idea is the **closed-loop research system**:

1. narrow the writable surface,
2. define a fixed experiment budget,
3. evaluate with one trustworthy metric,
4. log every run,
5. keep only improvements,
6. let the loop run autonomously.

That pattern is directly relevant to The Similarity. Our project already has:
- explicit metrics (`CRPS`, calibration, hit rate),
- modular methods,
- a backtester,
- a growing research surface,
- agent-assisted development.

So the question is not “should we copy autoresearch exactly?” The better question is: **which parts of the loop should we borrow to accelerate method discovery without damaging correctness?**

---

## What Karpathy’s autoresearch actually is

Primary source:
- Repository: https://github.com/karpathy/autoresearch

The repo README describes the core idea as giving an AI agent a small but real training setup and letting it iterate autonomously overnight: modify code, run a fixed 5-minute training job, keep or discard the change based on validation quality, and repeat.

The most important design decisions in the public repo are:

### 1. A tiny writable surface
Only `train.py` is edited by the agent. `prepare.py` stays fixed.

### 2. A fixed evaluation budget
Every experiment gets the same runtime budget, which makes comparisons fair.

### 3. One canonical metric
The run outcome is judged by `val_bpb`.

### 4. Results logging outside git history
A `results.tsv` ledger records experiments, including crashes and discarded ideas.

### 5. Human-written “research org code”
The human mainly edits `program.md`, which acts like a lightweight operating manual for the agent.

This is a research-operations pattern more than a single algorithm.

---

## Why this matters for The Similarity

The Similarity is not a one-metric language-model training repo, so a literal clone would be wrong. But the operating ideas are strong.

We already have a research loop hiding inside the codebase:

- hypothesis: a method or weighting change improves analog forecasting,
- implementation: edit one part of the engine,
- evaluation: run walk-forward backtests,
- acceptance: keep or revert based on metrics,
- memory: write down what worked and what failed.

Autoresearch gives that loop a **disciplined, agent-friendly shape**.

---

## The parts we should copy

## 1. Bounded experiment surfaces

Each autonomous research lane should own one narrow write-scope.

Examples:
- `the_similarity/config.py` weights only,
- `the_similarity/core/projector.py` cone logic only,
- one candidate method module only,
- one experiment notebook or benchmark harness only.

This keeps diffs reviewable and prevents accidental architectural drift.

## 2. Fixed evaluation budgets

We should define repeatable research budgets such as:
- 100 walk-forward samples on one asset family,
- 500 samples across a multi-asset benchmark,
- fixed random seeds where appropriate,
- fixed compute/time ceilings for candidate models.

Without a fixed budget, agents can accidentally “win” by spending more compute rather than being better.

## 3. Canonical acceptance metrics

For our system, likely primary metrics are:
- `CRPS`,
- calibration / coverage error,
- directional accuracy,
- top-k analog quality,
- runtime cost.

Every autonomous research run should name exactly which metrics decide keep/discard.

## 4. Explicit keep / discard discipline

Autonomous research gets dangerous when every experiment becomes permanent. We should adopt Karpathy’s explicit rule:
- improvement: keep,
- no improvement: revert,
- crash: log and move on.

That rule should apply not just to model code, but to:
- new methods,
- weight changes,
- prefilters,
- confidence-decay variants,
- retrieval heuristics.

## 5. A research ledger

We need a durable experiment ledger outside informal chat logs.

A good first version would record:
- run id,
- branch / commit,
- task scope,
- dataset slice,
- metrics before,
- metrics after,
- keep/discard,
- notes on why.

This is the main defense against agents re-running dead ends forever.

---

## The parts we should **not** copy blindly

## 1. Single-file mutation as a universal rule

That worked for `autoresearch` because the repo was intentionally tiny. The Similarity is a larger, modular system. We should preserve bounded scope, but not force all work through one file.

## 2. One scalar metric only

Our domain is more pluralistic. A lower CRPS with much worse calibration may not be a true win. We likely need a small scorecard rather than a single scalar.

## 3. Endless unsupervised looping on production code

Autoresearch is optimized for autonomous iteration. Our engine serves research, product, and explanation goals. We should isolate heavy autonomous loops into:
- sandboxes,
- experiment branches,
- notebooks,
- dedicated benchmark worktrees,
- or generated candidate patches.

---

## A concrete adaptation for this repo

## Lane A — method ablation loop

Purpose: test whether one method helps.

Loop:
1. toggle one method / weight / feature flag,
2. run a fixed walk-forward benchmark,
3. log metrics,
4. keep only if scorecard improves.

Good targets:
- JEPA lens on/off,
- Koopman blend on/off,
- confidence decay variants,
- different candidate counts per tier.

## Lane B — projector optimization loop

Purpose: improve cone quality without changing retrieval.

Loop:
1. modify cone logic in a bounded scope,
2. run calibration benchmark,
3. log CRPS + coverage,
4. keep or discard.

Good targets:
- percentile interpolation,
- horizon-dependent decay,
- regime-conditioned widening.

## Lane C — latent model research loop

Purpose: evaluate JEPA or related learned representations.

Loop:
1. modify training config / objective / feature set,
2. train within a fixed budget,
3. compute retrieval and walk-forward metrics,
4. retain only winning configurations.

This is the closest analogue to Karpathy’s original repo.

---

## How JEPA and autoresearch fit together

The most compelling combination is this:

- use **JEPA** to propose a new latent-regime signal,
- use an **autoresearch-style loop** to evaluate it systematically,
- only promote it into the engine after it wins against the current baseline.

That pairing is powerful because JEPA increases model capacity while autoresearch increases experimentation speed. One without the other is risky:

- JEPA without disciplined evaluation becomes research theater.
- Autoresearch without good hypotheses becomes benchmark hacking.

Together they can form a serious research pipeline.

---

## Recommended infrastructure additions

## 1. Research program files

Create human-maintained markdown playbooks that tell agents:
- what surface they may edit,
- which benchmark to run,
- which metrics matter,
- when to revert,
- how to log results.

This is the closest local analogue to Karpathy’s `program.md`.

## 2. Benchmark manifests

Codify reusable benchmark slices:
- daily equities,
- intraday futures,
- crypto regimes,
- crisis periods,
- calm periods.

Agents should reference benchmark ids, not invent ad hoc datasets each run.

## 3. Experiment ledger

Add a machine-readable ledger under something like `progress/` or `research/results/`.

## 4. Safe autonomy boundaries

Require autonomous research lanes to:
- avoid main branches,
- avoid dependency changes unless explicitly allowed,
- avoid touching evaluation harnesses,
- avoid overwriting accepted baselines.

---

## Recommended first experiments

1. **JEPA retrieval-only pilot**
   - frozen embedding similarity added as a Tier 2 score,
   - evaluate whether top-k analog quality improves.

2. **JEPA novelty penalty**
   - predictor residual used to reduce confidence in unfamiliar regimes.

3. **Time-frequency JEPA versus raw-window JEPA**
   - compare latent spaces for downstream analog ranking.

4. **Autoresearch-style weight search**
   - bounded loop over weight vectors with walk-forward scorecard.

5. **Projector micro-optimization loop**
   - fixed benchmark to compare cone interpolation / widening variants.

---

## Recommendation

Karpathy’s autoresearch is best understood as a **research operating system pattern**, not just a repo. The Similarity should borrow:
- bounded write scopes,
- fixed evaluation budgets,
- explicit keep/discard discipline,
- durable experiment ledgers,
- human-authored agent playbooks.

If we apply that pattern to JEPA exploration, we get a credible path to faster, safer iteration:

- faster because agents can run more disciplined experiments,
- safer because every proposal must beat the benchmark,
- clearer because failures are logged instead of forgotten.

The practical takeaway is simple: use autoresearch to accelerate **how** we learn, and use JEPA to test **what** we should learn next.
