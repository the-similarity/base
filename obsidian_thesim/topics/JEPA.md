# JEPA (Joint-Embedding Predictive Architecture)

**Idea in one breath:** learn **forward dynamics** — how a market state evolves into the next — by predicting future latent representations, not by reconstructing noisy price data. Build a world model, not a shape matcher.

## Why we care

JEPA's core principle: predict in latent space, not data space. This means:
- Learn **how state A becomes state B**, not just "does A look like B"
- Capture regime transitions, volatility shifts, structural breaks
- Generate **synthetic plausible futures** from a current state
- Eventually replace Koopman eigenvalue extrapolation with learned dynamics

## What we tried and killed

**JEPA retrieval (April 2026):** trained a 1D CNN encoder with masked prediction for cosine nearest-neighbor retrieval. Results:
- SPY: learned shape features (discrimination gap 0.177) but zero regime separation (0.023). DTW already does this better.
- BTC: total representation collapse on 326 windows.
- **Verdict: dead end.** Retrieval is not what JEPA is for. All retrieval code was deleted.

## Actual direction: world models

The research question is now: **can JEPA learn forward dynamics of financial time series?**

Research hierarchy:
1. **Q1:** Can it predict latent(t+Δ) from latent(t)? (beat naive persistence)
2. **Q2:** Does it learn regime-aware dynamics? (regime separation > 0.10)
3. **Q3:** Can it generate plausible synthetic futures? (distributional similarity)
4. **Q4:** Does it beat Koopman for the forecast cone? (CRPS + calibration)

Key architecture difference from retrieval: **temporal pairs (t, t+Δ)** not masked reconstruction. The predictor learns evolution, not pattern completion.

See: `research/autoresearch/playbooks/JEPA_WORLD_MODEL_LANE.md`

## Connections

- The fractal terrain engine (`the-similarity-fractal/`) is a parallel world-model effort — different domain, shared abstractions
- Koopman operator (`the_similarity/core/projector.py`) is the current forward-dynamics approach — JEPA world model is the potential successor

## Read next

- [[06-jepa-joint-embedding-predictive-architecture]]
- [[Karpathy autoresearch]]
- [[Koopman operator]]
- [[Research hub]]
