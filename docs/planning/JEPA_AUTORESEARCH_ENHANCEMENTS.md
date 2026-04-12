# JEPA + autoresearch enhancement roadmap for The Similarity

## Purpose

This document turns the current JEPA and autoresearch research into an implementation-oriented roadmap for The Similarity. It is intentionally conservative: the goal is to identify enhancements that are both technically meaningful and testable against the current engine.

---

## Design principle

Do not replace the existing interpretable pipeline until a learned latent method repeatedly improves:
- analog retrieval quality,
- walk-forward calibration,
- CRPS,
- and robustness across regimes.

Use JEPA as an incremental extension first. Use autoresearch-style loops to validate each change.

---

## Priority 1 — low-risk, high-information enhancements

## 1. Add a JEPA research harness outside the production matcher

### What to build
- dataset builder for normalized sliding windows,
- time-based train/validation/test splits,
- embedding export job,
- nearest-neighbor evaluation harness,
- walk-forward comparison report against the current engine.

### Why first
This creates the measurement surface before any production integration.

### Success criteria
- reproducible benchmark runs,
- embeddings can be computed for fixed window sets,
- baseline versus JEPA retrieval comparisons become easy.

---

## 2. Introduce a frozen `jepa_similarity` score as an experimental Tier 2 field

### What to build
- extend `ScoreBreakdown` with a JEPA similarity slot,
- cache per-window embeddings in the feature store or equivalent offline artifact,
- compute cosine similarity for top Tier 2 candidates only,
- gate it behind `active_methods`.

### Why first in production
- minimal pipeline disruption,
- easy ablation,
- interpretable enough to compare with existing scores.

### Success criteria
- no regression in runtime for non-JEPA runs,
- measurable lift in reranking quality or downstream forecast quality.

---

## 3. Add a JEPA novelty / predictability residual

### What to build
- predictor error summary for the query window,
- optional confidence penalty or decay multiplier,
- logging for analysis during backtests.

### Why it matters
This gives JEPA a second role beyond similarity: identifying when the current regime is outside the model’s familiar manifold.

### Success criteria
- reduced overconfidence in regime-shift periods,
- improved coverage / calibration even when median forecasts do not improve much.

---

## Priority 2 — medium-risk, potentially high-upside enhancements

## 4. Multi-resolution JEPA objective

### What to build
Train latent prediction at multiple horizons or scales.

### Why it fits the project
The Similarity already encodes a multi-scale worldview through wavelets, fractals, and cone horizons.

### Hypothesis
A multi-resolution objective will outperform a single fixed-horizon latent predictor for analog retrieval and confidence estimation.

---

## 5. Time-frequency JEPA

### What to build
- time-domain encoder,
- frequency / wavelet / scalogram encoder,
- predictive alignment objective between them.

### Why it fits
This is the learned counterpart to our current combination of path-based and spectrum-based methods.

### Hypothesis
A dual-view latent space will better preserve structural similarity than a raw-window-only encoder.

---

## 6. Regime-codebook JEPA

### What to build
- soft codebook or prototype bottleneck,
- regime token summaries,
- optional conditioning of retrieval and projection by latent regime token.

### Why it fits
This could bridge latent representation learning with the project’s explicit regime language.

### Hypothesis
Discrete latent prototypes improve match grouping and forecast conditioning.

---

## Priority 3 — high-risk, long-horizon enhancements

## 7. Probabilistic / variational JEPA for cone uncertainty

### What to build
- latent uncertainty model,
- sampled future latent trajectories,
- cone-width contribution from latent transition uncertainty.

### Why it is interesting
Recent JEPA research is moving toward probabilistic world models. That aligns with our need for calibrated uncertainty rather than point estimates.

### Main risk
This adds major complexity and should only happen after a simpler JEPA similarity lens proves value.

---

## 8. JEPA-guided candidate generation

### What to build
Use latent retrieval earlier in the pipeline, potentially as a prefilter or blended candidate proposer.

### Why this is deferred
Changing candidate generation changes the character of the engine. That is a bigger risk than adding a Tier 2 enrichment score.

---

## 9. Hybrid analog + latent projector

### What to build
Blend:
- empirical analog futures,
- Koopman forward evolution,
- JEPA latent future uncertainty.

### Why this is compelling
It could create a genuinely richer probabilistic projector than any single component alone.

### Why this is deferred
This should wait until each component has independent evidence.

---

## Autoresearch-style infrastructure enhancements

## 10. Add agent-readable research playbooks

### What to build
Markdown playbooks that define:
- writable files,
- fixed benchmark ids,
- acceptance metrics,
- keep/discard rules,
- logging format.

### Why it matters
This imports the strongest idea from Karpathy’s `program.md` into a repo shaped like ours.

---

## 11. Create benchmark manifests for autonomous experiments

### What to build
Named benchmark suites such as:
- equities-daily-core,
- crypto-daily-core,
- stress-regimes,
- low-volatility regimes,
- intraday-mini.

### Why it matters
Agents should not improvise evaluation sets every run.

---

## 12. Add an experiment ledger

### What to build
A structured ledger recording:
- run id,
- branch / commit,
- benchmark suite,
- metrics before/after,
- keep/discard decision,
- notes.

### Why it matters
This is essential for cumulative research memory and for preventing repeated dead ends.

---

## 13. Add reversible keep/discard automation

### What to build
A helper workflow that:
- applies a bounded change,
- runs the benchmark,
- logs the result,
- keeps or reverts automatically.

### Why it matters
This is the cleanest path toward safe autonomous research on this codebase.

---

## Suggested order of execution

1. Build the JEPA research harness.
2. Add benchmark manifests and experiment ledger.
3. Pilot frozen JEPA similarity as a Tier 2 score.
4. Pilot JEPA predictor residual as a confidence penalty.
5. Run autoresearch-style ablations across benchmarks.
6. Explore multi-resolution JEPA.
7. Explore time-frequency JEPA.
8. Explore regime codebooks.
9. Only then consider probabilistic JEPA or earlier-pipeline retrieval changes.

---

## Decision gates

A JEPA-related enhancement should only move forward if it clears these gates:

### Gate A — offline retrieval
Improves top-k analog ranking or similar retrieval metrics.

### Gate B — walk-forward forecast quality
Improves CRPS and/or calibration on at least one benchmark suite without unacceptable regressions elsewhere.

### Gate C — runtime / complexity
Does not introduce unreasonable cost relative to the benefit.

### Gate D — interpretability
Can still be explained in the context of the existing score stack.

---

## Recommended immediate next tasks

1. write a benchmark spec for JEPA retrieval experiments,
2. define the experiment ledger schema,
3. prepare normalized window datasets and temporal splits,
4. prototype a minimal frozen JEPA encoder outside production,
5. compare latent nearest neighbors with the current Tier 2 matches on the same windows.

---

## Bottom line

The best near-term enhancement is **not** a full world-model rewrite. It is a disciplined experimental lane:

- JEPA for latent-regime similarity and novelty estimation,
- autoresearch for safe, benchmark-driven iteration,
- promotion into the engine only after repeated backtest wins.

That path preserves the current system’s interpretability while opening a credible route toward learned structural similarity.
