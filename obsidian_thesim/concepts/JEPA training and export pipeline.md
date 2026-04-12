# JEPA training and export pipeline

End-to-end pipeline that loads time-series data, trains a JEPA encoder, and exports frozen embeddings for downstream retrieval experiments.

## Location

- **Pipeline script:** `research/autoresearch/scripts/jepa_train_and_export.py`
- **Encoder + prototype:** `research/autoresearch/scripts/jepa_retrieval_prototype.py`
- **Data spec:** `research/autoresearch/scripts/jepa_data_spec.py`
- **Retrieval harness:** `research/autoresearch/scripts/retrieval_harness.py`
- **Tests:** `research/autoresearch/scripts/test_jepa_train_export.py`

## What it does

1. **Loads datasets** via `build_jepa_dataset()` — parquet files windowed into `(N, 1, W)` arrays with z-normalisation per window.
2. **Splits temporally** into train (70%) / val (15%) / test (15%) — no look-ahead.
3. **Trains the JEPA encoder** using self-supervised MSE loss in latent space with an EMA target encoder.
4. **Exports embeddings** for all windows (train + val + test) to disk.

## Output artifacts

Saved to `output_dir/`:

| File | Contents |
|------|----------|
| `encoder.pt` | PyTorch state dict of the trained `WindowEncoder` |
| `embeddings.npz` | numpy archive: `embeddings`, `offsets`, `split_train`, `split_val`, `split_test` |
| `metadata.json` | Training config, dataset names, split sizes, loss history, timestamp |

## How to run

### CLI

```bash
python research/autoresearch/scripts/jepa_train_and_export.py \
  --datasets spy btc_usdt \
  --output progress/autoresearch/embeddings/run001/ \
  --epochs 50 \
  --latent-dim 64 \
  --window-size 60
```

### Python API

```python
from jepa_train_and_export import train_and_export, load_embeddings, embedding_retrieval_fn

# Train and save
result = train_and_export(["spy", "btc_usdt"], "progress/autoresearch/embeddings/run001/")

# Load cached
data = load_embeddings("progress/autoresearch/embeddings/run001/")

# Build retrieval function
retrieve = embedding_retrieval_fn(data["embeddings"], k=10)
neighbors = retrieve(query_idx=42)
```

### From raw array (tests / synthetic data)

```python
from jepa_train_and_export import train_and_export_from_array

result = train_and_export_from_array(prices_array, "/tmp/test_run", epochs=5)
```

## Architecture

- **WindowEncoder**: 1D CNN (3 conv blocks, 64→128→256 channels, kernel 5) → adaptive avg pool → linear head to `latent_dim`.
- **LatentPredictor**: 2-layer MLP (`D → 2D → D`), intentionally lower capacity than the encoder to prevent collapse.
- **EMA target encoder**: `theta_target = tau * theta_target + (1-tau) * theta_context` with tau=0.996.
- **Retrieval**: L2-normalised embeddings, cosine similarity via dot product, top-k with optional candidate mask.

## Related notes

- [[Nine-method pipeline]] — the production matcher this research lane may eventually enrich
- [[Research hub]] — broader research context
- [[Repo research and docs]] — links to all research scripts

## Lane context

This pipeline is part of the [[JEPA retrieval lane|jepa-retrieval-lane-v1]] (benchmark: `jepa-retrieval-core-v1.yaml`). The embeddings are consumed by the retrieval harness for offline evaluation before any production integration.
