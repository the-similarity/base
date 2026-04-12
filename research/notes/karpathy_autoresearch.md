# Karpathy auto-research

## Bottom line

Andrej Karpathy does appear to have a public **auto-research** project: `karpathy/autoresearch` on GitHub. The clearest public description is the repository README, which frames the workflow as an autonomous experiment loop around a small but real LLM training setup.

This is **not** a formal paper or benchmark. It is best understood as a public repo plus a set of supporting posts and adjacent tooling habits.

## What the public sources say

### 1) `karpathy/autoresearch` repository

The README describes:

- a **single editable training file** (`train.py`)
- a **locked evaluation / prep file** (`prepare.py`)
- a **human-authored instruction file** (`program.md`)
- a **fixed five-minute training budget**
- a **single scalar metric**: `val_bpb` (validation bits per byte)
- an overnight loop where the agent modifies code, trains, evaluates, keeps or discards, and repeats

The repo README says the project story is from **March 2026** and links to two Karpathy X posts for additional context.

Source:
- GitHub repo: https://github.com/karpathy/autoresearch

### 2) Karpathy’s broader “meta research” pattern

His personal site also explicitly says he has long been interested in “meta research” and points to tools like `arxiv-sanity`, `research lei`, `scholaroctopus`, and `biomed-sanity`.

That matters because `autoresearch` is not a one-off stunt. It fits a long-running pattern: build a small tool that improves research throughput, then iterate on the workflow itself.

Source:
- Karpathy site: https://karpathy.ai/

### 3) `nanochat` as the underlying scaffold

The `autoresearch` README says the training code is a simplified single-GPU implementation of `nanochat`.

`nanochat` itself is presented as a minimal, dependency-light GPT training stack. That minimalism is important: it keeps the experiment surface small enough for an agent to explore safely.

Sources:
- NanoChat site: https://nanochat.karpathy.ai/
- NanoChat repo: https://github.com/karpathy/nanochat

## What I would infer, carefully

Reasonable inference:

- Karpathy’s public “auto-research” idea is a **closed-loop experimentation system**.
- The key design is not “AI writes everything,” but **AI mutates one bounded surface while a locked evaluator decides winners**.
- The human’s job shifts to writing the **program/instructions** and improving the research org itself.

Do **not** over-claim:

- There is no evidence here of a single canonical paper called “auto-research.”
- The public artifact is a repo and associated posts, not a formal methodology spec.
- Claims about star counts, adoption, or later derivatives should be treated separately unless directly sourced.

## Reusable workflow ideas for The Similarity

### A. One editable surface, one locked evaluator

Use a strict split similar to Karpathy’s repo:

- `program.md` equivalent: the research brief, constraints, and success criteria
- editable surface: one method file, one config, or one hypothesis branch
- locked evaluator: frozen walk-forward backtest and calibration/CRPS checks

This would fit The Similarity especially well because the project already has clear evaluation surfaces: hit rate, MAE, calibration, and CRPS.

### B. Budgeted experiment loops

Run short, repeatable experiments with a fixed wall-clock budget.

For The Similarity, that could mean:

- a 5–15 minute smoke loop for proposal quality
- a longer overnight sweep for parameter candidates
- a hard stop if metrics do not improve after N tries

### C. Append-only experiment ledger

Karpathy’s workflow emphasizes a log of what was tried.

For our repo, that should become:

- an experiment TSV/JSONL
- a short Obsidian note per hypothesis
- the exact metric deltas and failure modes

### D. Hypothesis-first agent prompts

Instead of asking an agent to “improve the model,” ask it to:

- propose one hypothesis
- state the expected metric impact
- edit only the allowed files
- summarize whether the locked eval accepted the change

### E. Keep and revert like a scientist

Use Git as the memory of the loop:

- keep a commit only when the locked metric improves
- revert quickly when it does not
- treat branches as disposable experiment containers

## Practical enhancements we could add to The Similarity

### Near-term

1. Add a `research/program.md` that describes the current hypothesis, constraints, and metric target.
2. Add a frozen `research/eval/` harness for one canonical slice of data.
3. Create a tiny agent loop that mutates one config or one method file and writes results to a ledger.
4. Auto-generate an Obsidian note from each completed experiment.

### Medium-term

1. Run parallel ablations over window length, scale factors, and ranking weights.
2. Use the loop to test JEPA-style latent-lens ideas before any large implementation.
3. Add failure-mode classification: leakage, overfit, instability, slow inference, poor calibration.

### Longer-term

1. Build a persistent research agent that proposes enhancements, runs evals, and drafts docs automatically.
2. Use separate agents for proposal, execution, evaluation, and synthesis.
3. Tie the whole loop to the project’s existing walk-forward backtester so the system learns from real forecast quality, not just proxy loss.

## Why this matters for us

The Similarity already has a strong scientific shape: methods, scores, backtests, and a multi-stage matcher. Karpathy’s auto-research pattern suggests we should make the research process itself as disciplined as the model pipeline:

- one hypothesis
- one editable surface
- one locked evaluator
- one append-only result log

That is the simplest way to get an agent to help without letting it optimize the wrong thing.

## Source list

- `karpathy/autoresearch` README: https://github.com/karpathy/autoresearch
- Karpathy site / meta-research background: https://karpathy.ai/
- `nanochat` site: https://nanochat.karpathy.ai/
- `nanochat` repo: https://github.com/karpathy/nanochat
