# JEPA (Joint-Embedding Predictive Architecture)

**Idea in one breath:** learn the **state** behind the sequence by predicting a **future / hidden latent representation**, not by reconstructing every noisy tick. In plain English: move from **shape matching** toward **regime matching**.

## Why we care

For The Similarity, JEPA is interesting because markets are noisy. A good JEPA-style encoder could ignore some path-level clutter and focus on things like:
- trend regime,
- volatility state,
- multi-scale structure,
- how predictable the next segment is.

## Best first use here

The safest first use is **not** to replace the engine.

Use JEPA first as:
1. a **Tier 2 latent similarity score**,
2. a **novelty / predictability residual**,
3. a research-only feature until backtests show real lift.

## Research directions that matter most

- **I-JEPA (2023):** latent prediction without reconstruction in images.
- **V-JEPA (2024):** extends the same idea to temporal visual dynamics.
- **Time-series JEPA work (2024-2026):** increasingly emphasizes multi-resolution prediction, time-frequency alignment, regime-like codebooks, and probabilistic uncertainty.

## Why it fits our roadmap

JEPA lines up with several things we already believe:
- analogs should reflect **structure**, not only path shape,
- multi-scale information matters,
- confidence should drop when the regime is unfamiliar,
- uncertainty should widen honestly.

## Read next

- [[06-jepa-joint-embedding-predictive-architecture]]
- [[Karpathy autoresearch]]
- [[Koopman operator]]
- [[Wavelet leaders]]
- [[Analog forecasting]]

## Related

- [[Research hub]]
- [[Methods index]]
- [[Engine map]]
