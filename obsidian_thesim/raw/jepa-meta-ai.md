# Raw: JEPA source notes

## Primary sources checked

- Yann LeCun, **A Path Towards Autonomous Machine Intelligence** (OpenReview, June 27, 2022)
  - https://openreview.net/forum?id=BZ5a_8n9hcS
- **I-JEPA** paper + official Meta repo (2023)
  - https://arxiv.org/abs/2301.08243
  - https://github.com/facebookresearch/ijepa
- **V-JEPA** paper + official Meta repo (2024)
  - https://arxiv.org/abs/2404.08471
  - https://github.com/facebookresearch/jepa
- **Time-Series JEPA for Predictive Remote Control under Capacity-Limited Networks** (2024)
  - https://arxiv.org/abs/2406.04853
- **TF-JEPA: Predictive Alignment of Time-Frequency Representations Without Contrastive Pairs** (OpenReview submission, 2025/2026)
  - https://openreview.net/forum?id=8bLa8PILyO
- **MTS-JEPA** (2026)
  - https://arxiv.org/abs/2602.04643
- **VJEPA** / **Var-JEPA** (2026)
  - https://arxiv.org/abs/2601.14354
  - https://arxiv.org/abs/2603.20111

## Working conclusions

- JEPA is best understood as **latent predictive representation learning**, not generic generation.
- The strongest mature evidence is still in vision/video; time-series evidence is newer and should be treated as promising, not settled.
- The most relevant directions for The Similarity are:
  - latent regime matching,
  - predictor residual as novelty / confidence,
  - multi-resolution training,
  - time-frequency dual-view encoders,
  - probabilistic uncertainty for cone widening.

## Important caution

There is currently no strong public evidence that JEPA is already a proven superior approach for **financial analog forecasting** specifically. Any recommendation for this repo is therefore an **engineering inference** from adjacent primary literature plus architecture fit.
