# Joint-Embedding Predictive Architecture (JEPA) for The Similarity

## Executive summary

JEPA is a family of self-supervised models that learns by predicting **latent representations** of hidden or future content rather than reconstructing raw observations. That matters for financial time series because raw prices contain large amounts of nuisance variation, microstructure noise, and pathwise randomness. A JEPA-style model can, in principle, learn a compact representation of **regime, dynamics, and predictability** instead of memorizing every bar.

For The Similarity, the most promising use is **not** “replace the whole engine with one deep model.” The better near-term interpretation is:

1. train a JEPA encoder on historical windows,
2. use its embeddings as an additional **latent-regime lens** inside the existing matcher,
3. treat predictor residuals as a **novelty / predictability signal**, and
4. keep the current interpretable nine-method stack as the decision surface while the latent model earns trust through backtests.

This is a good fit for the project because the current system already separates **candidate generation**, **enrichment**, and **forecasting**. JEPA can slot into Tier 2 first, then later influence retrieval and projection if validation supports it.

---

## What JEPA is

A canonical JEPA setup has four moving parts:

1. **Context encoder**: encodes the observed part of a sample.
2. **Target encoder**: encodes the hidden / future / masked part into the same latent space.
3. **Predictor**: maps context latents toward target latents.
4. **Consistency objective**: minimizes distance between predicted and target latents, often with architectural or EMA-based collapse prevention.

Unlike reconstruction-heavy models, JEPA does not need to predict every noisy detail in observation space. The intended bias is to learn **high-level, predictable structure**.

In LeCun’s 2022 position paper, hierarchical joint-embedding world models are explicitly framed as a path toward prediction, reasoning, and planning across multiple levels of abstraction.

---

## Why this is interesting for markets

### 1. Latent matching is closer to “regime matching” than “shape matching”

DTW, Pearson, SAX, and Matrix Profile are excellent at measuring path similarity. JEPA adds a different possibility: two windows may have different local path geometry but still occupy similar latent states because they share comparable trend-strength, volatility compression/expansion, mean-reversion pressure, or multi-scale structure.

### 2. Prediction error can become a first-class signal

If a predictor is trained to estimate future latent states, then high prediction error is useful information. In our setting that can mean:

- the current regime is rare,
- the market is transitionary or unstable,
- analog retrieval should be down-weighted,
- forecast bands should widen faster.

### 3. Multi-scale JEPA research is converging toward exactly the problems we care about

Recent time-series JEPA work increasingly focuses on:

- **multi-resolution objectives**,
- **time-frequency alignment**,
- **discrete regime bottlenecks / codebooks**,
- **probabilistic latent forecasting and uncertainty**.

Those map naturally onto The Similarity’s roadmap: fractal structure, tiered retrieval, confidence calibration, and forward cones.

---

## Primary research timeline

### 2022 — LeCun, “A Path Towards Autonomous Machine Intelligence”
- URL: https://openreview.net/forum?id=BZ5a_8n9hcS
- Why it matters: sets the conceptual frame for JEPA as a **hierarchical world-model** approach rather than a one-off architecture.
- Relevance to us: supports the interpretation that useful prediction should happen in **abstract state space**, not necessarily in raw observation space.

### 2023 — I-JEPA
- Paper: https://arxiv.org/abs/2301.08243
- Code / official repo: https://github.com/facebookresearch/ijepa
- Key point: representation prediction can learn semantic structure **without reconstruction or contrastive negatives**.
- Transferable lesson: a predictive latent objective can be useful even when the hidden content is high-entropy.

### 2024 — V-JEPA
- Paper: https://arxiv.org/abs/2404.08471
- Code / official repo: https://github.com/facebookresearch/jepa
- Key point: feature prediction from video alone produces strong downstream representations, still without pixel reconstruction.
- Transferable lesson: JEPA is not limited to static vision; it scales toward **temporal dynamics** and can behave like a primitive world model.

### 2024 — Time-Series JEPA for predictive remote control
- Paper: https://arxiv.org/abs/2406.04853
- Key point: applies TS-JEPA to bandwidth-limited control by transmitting semantically useful latent state instead of raw sequential data.
- Transferable lesson: even outside finance, TS-JEPA is already being used where **latent sufficiency** matters more than raw reconstruction.

### 2025/2026 — TF-JEPA
- OpenReview: https://openreview.net/forum?id=8bLa8PILyO
- Key point: aligns time-domain and frequency-domain views for multivariate time series without contrastive pairs.
- Transferable lesson: directly relevant to our multi-scale / wavelet worldview. A dual-view objective is a better fit than a single raw-window encoder if we want latent states to reflect both path and spectrum.

### 2026 — MTS-JEPA
- Paper: https://arxiv.org/abs/2602.04643
- Key point: combines a multi-resolution predictive objective with a soft codebook bottleneck for anomaly early warning.
- Transferable lesson: the codebook idea looks especially useful for The Similarity because it suggests a clean bridge between continuous embeddings and **discrete regime tags**.

### 2026 — VJEPA / Var-JEPA
- VJEPA: https://arxiv.org/abs/2601.14354
- Var-JEPA: https://arxiv.org/abs/2603.20111
- Key point: recent work is pushing JEPA toward **probabilistic latent prediction** and explicit uncertainty.
- Transferable lesson: this is the clearest research bridge between JEPA embeddings and our need for **forecast cone calibration**.

---

## What the research does **not** prove yet

It is important to be precise.

1. There is **not yet strong public evidence** that JEPA is a proven superior method for financial analog forecasting.
2. The strongest JEPA evidence still comes from **vision/video** and from newer, emerging time-series papers.
3. For this project, the case is therefore an **engineering inference** from adjacent evidence, not a settled domain theorem.

That makes the right posture: integrate gradually, backtest aggressively, and keep the interpretable stack as the baseline.

---

## Most promising integration patterns for The Similarity

## 1. JEPA as a Tier 2 enrichment lens

This is the safest first move.

### Mechanism
- Train an encoder on normalized historical windows.
- Compute one embedding for the query and one for each surviving candidate.
- Score cosine similarity (or learned Mahalanobis distance) in latent space.
- Add the result to `ScoreBreakdown` as something like `jepa_similarity`.

### Why this first
- minimal disruption to the current search pipeline,
- easy ablation against existing methods,
- simple to turn off with `active_methods`,
- compatible with feature-store caching.

### What success would look like
- better top-k match quality on held-out retrieval tasks,
- better calibration after adding the score to the ensemble,
- reduced false confidence in noisy or regime-shift periods.

## 2. Predictor residual as a confidence / novelty term

### Mechanism
- Use the predictor’s error for the current query window as `jepa_unfamiliarity`.
- Down-weight confident projections when the current latent state is poorly predicted.

### Why it is valuable
This would turn JEPA into both:
- a similarity lens, and
- a regime-break detector.

That is more useful than a plain embedding lookup because it tells us **when the analog itself should not be trusted**.

## 3. Multi-resolution JEPA objective

### Mechanism
Train on multiple horizons simultaneously, for example:
- short horizon: local continuation,
- medium horizon: swing structure,
- long horizon: regime drift.

### Why it fits
The Similarity already thinks in multi-scale terms via wavelets, fractals, and forecasting horizons. A multi-resolution objective is likely better than a single fixed prediction span.

## 4. Time-frequency dual-view JEPA

### Mechanism
- one encoder ingests normalized returns / prices,
- another ingests spectral features (wavelets, scalograms, FFT patches, or IMF summaries),
- align their latent targets predictively.

### Why it fits
This is the closest learned analogue to our current hand-built combination of shape + spectrum + structure.

## 5. Regime codebook / vector-quantized latent states

### Mechanism
Borrow the MTS-JEPA-style intuition: constrain latent dynamics through a soft codebook or regime prototypes.

### Why it fits
This could produce:
- discrete regime tokens,
- cleaner clustering of retrieved matches,
- easier human interpretation,
- better conditioning for the forecast cone.

## 6. Probabilistic JEPA for forecast cone uncertainty

### Mechanism
Use a probabilistic latent model to sample future latent states, decode or retrieve analog continuations, and translate dispersion into cone width.

### Why it fits
Our current cones are empirical distributions over retrieved futures. A probabilistic JEPA could eventually become an additional uncertainty source:
- analog dispersion,
- regime uncertainty,
- latent transition uncertainty.

---

## A staged roadmap

## Stage 0 — research harness only
- offline dataset prep,
- clear train/val/test temporal splits,
- retrieval benchmark and walk-forward benchmark,
- no production inference.

## Stage 1 — frozen encoder, retrieval-only
- train JEPA encoder,
- compute embeddings for windows,
- evaluate nearest-neighbor quality and downstream match ranking.

## Stage 2 — add predictor residual
- estimate novelty / predictability,
- use residual to modulate confidence decay or candidate weights.

## Stage 3 — multi-resolution + time-frequency variants
- test whether multi-scale objectives beat single-horizon objectives,
- compare raw-window JEPA versus time-frequency JEPA.

## Stage 4 — probabilistic JEPA
- explore latent uncertainty for cone widening,
- only after standard walk-forward shows incremental value.

---

## Practical dataset and training notes

If we pursue JEPA, the data representation matters more than the architecture buzzword.

Recommended first-pass choices:
- train on **normalized return windows**, not raw prices,
- include optional side channels: realized volatility, volume, maybe market breadth if available,
- use temporal splits by date to avoid leakage,
- start with a **retrieval benchmark** before chasing point forecasting metrics.

Potential positive-pair / target designs:
- future continuation of the same window,
- masked future segment,
- alternate scale of the same window,
- time-domain versus frequency-domain view.

---

## Evaluation criteria

JEPA should not be judged by representation aesthetics. It should earn its keep through metrics.

### Retrieval metrics
- top-k analog precision on labeled historical motifs,
- downstream rerank lift relative to current Tier 2 baseline,
- diversity of retrieved analogs.

### Forecast metrics
- CRPS,
- coverage / calibration of forecast bands,
- directional accuracy,
- performance by market regime.

### Safety metrics
- degradation during regime shifts,
- stability across assets and timeframes,
- sensitivity to retraining window choice.

---

## Risks

### 1. Latent collapse or trivial embeddings
Newer papers still treat collapse prevention as a central engineering issue.

### 2. Beautiful embeddings with no trading value
Representation learning can improve benchmarks without helping forward calibration.

### 3. Excess complexity too early
A full JEPA stack is harder to debug than explicit methods like DTW, Koopman, and wavelets.

### 4. Hidden leakage
Window sampling, overlapping splits, and future-conditioned targets can easily contaminate evaluation.

---

## Recommendation

The best current interpretation is:

- **Yes, JEPA is worth researching for The Similarity.**
- **No, it should not replace the current engine yet.**
- The right first implementation is a **cached Tier 2 latent-regime lens plus novelty score**.
- The right longer-term bet is **multi-resolution, time-frequency, probabilistic JEPA**, but only if the first-stage retrieval and walk-forward evidence is positive.

In short: JEPA looks like a credible path from “pattern similarity” toward “state similarity,” which is exactly the conceptual upgrade The Similarity wants. The burden of proof, however, still belongs to backtesting.
