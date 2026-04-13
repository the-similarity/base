# JEPA retrieval prototype

Research prototype exploring whether **Joint Embedding Predictive Architecture** (JEPA) latent representations can improve analog retrieval quality compared to the production [[Nine-method pipeline]].

## What is JEPA?

JEPA (Assran et al., 2023 — I-JEPA; LeCun, 2022 — position paper) learns representations by predicting the **latent embedding** of masked input regions, rather than reconstructing raw pixel/sample values. This forces the encoder to capture semantic structure instead of low-level detail.

Applied to time series: given a window of price data, mask a contiguous chunk, encode the masked window, and train a predictor to match the **target encoder's** latent of the full window. The target encoder is an EMA (exponential moving average) copy of the online encoder, preventing representation collapse.

## Architecture

```
Raw window (1×W)
    │
    ├── [mask contiguous 30%] ──→ Online Encoder (1D CNN) ──→ z_masked
    │                                                              │
    │                                                        Predictor (MLP)
    │                                                              │
    │                                                           z_pred
    │                                                              │
    └── Target Encoder (EMA copy) ──→ z_target ←── L2 loss ──────┘
```

- **Encoder**: 3-layer 1D CNN (Conv → BN → GELU → MaxPool) → AdaptiveAvgPool → Linear → L2-normalise
- **Predictor**: 3-layer MLP (Linear → GELU → Linear → GELU → Linear → L2-normalise)
- **Loss**: `1 - cosine_similarity(z_pred, z_target)` (purely in latent space)
- **EMA momentum**: 0.996 (target encoder tracks online slowly)

## How to run

### Requirements (not in pyproject.toml — research only)

```bash
pip install torch>=2.0    # CPU build: pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install scipy
```

### Training + retrieval comparison

```bash
python research/autoresearch/scripts/jepa_retrieval_prototype.py \
    --dataset the-similarity-data/data/stocks/spy/1d.parquet \
    --window-size 60 --top-k 20 --epochs 50 --write-report
```

### Tests

```bash
python -m pytest research/autoresearch/scripts/test_jepa_prototype.py -v
```

## What it measures

| Metric | Meaning |
|--------|---------|
| **Top-k overlap ratio** | Fraction of JEPA's top-k matches that also appear in the production engine's top-k |
| **Kendall tau** | Rank correlation between JEPA and production rankings on shared matches |
| **Training loss** | Cosine distance between predicted and target latents (lower = better representation) |

## Relation to the autoresearch lane

This prototype is **Task 3** of the [[Research hub|JEPA autoresearch lane]] (`jepa-retrieval-lane-v1`). The lane playbook is at `research/autoresearch/playbooks/JEPA_RETRIEVAL_LANE.md`.

**Write scope**: `research/autoresearch/`, `progress/autoresearch/`, `the-similarity-playground/`, `the_similarity/examples/`. Production code in `the_similarity/core/` is not touched.

## Key files

| Path | Purpose |
|------|---------|
| `research/autoresearch/scripts/jepa_retrieval_prototype.py` | Main prototype (encoder, predictor, training, retrieval, comparison) |
| `research/autoresearch/scripts/test_jepa_prototype.py` | 17 unit tests on synthetic data |
| `research/autoresearch/playbooks/JEPA_RETRIEVAL_LANE.md` | Lane playbook (frozen evaluator, budget, keep/discard rules) |
| `progress/autoresearch/reports/` | JSON reports from runs |

## Design decisions

1. **1D CNN over transformer** — simpler, faster to train on short windows (60 bars); transformer variant is a future candidate experiment.
2. **Contiguous masking** — mirrors how real missing data or future prediction works in time series; random dropout would not force global shape learning.
3. **Cosine retrieval** — L2-normalised embeddings make nearest-neighbour search a simple dot product; scales to large corpora with FAISS if needed.
4. **No raw reconstruction** — the JEPA principle: predicting latents avoids learning noise and focuses on invariant structure.
