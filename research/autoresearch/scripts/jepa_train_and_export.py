"""JEPA train-and-export pipeline: end-to-end data -> encoder -> embeddings.

This module provides the missing link between the JEPA prototype components:
it orchestrates data loading, temporal splitting, encoder training, weight
saving, and embedding export into a single reproducible pipeline.

Lifecycle:
  1. ``train_and_export()`` loads datasets, splits temporally, trains the
     JEPA encoder, saves weights, and exports embeddings + metadata.
  2. ``load_embeddings()`` reloads cached embeddings and metadata from disk.
  3. ``embedding_retrieval_fn()`` wraps embeddings in a cosine-similarity
     retrieval function compatible with the ``RetrievalFn`` protocol.

Output artifacts (written to ``output_dir``):
  - ``encoder.pt``: PyTorch state dict of the trained WindowEncoder.
  - ``embeddings.npz``: numpy archive with keys ``embeddings``, ``offsets``,
    ``split_train``, ``split_val``, ``split_test``.
  - ``metadata.json``: training config, dataset names, split boundaries,
    loss history, and timestamps.

Immutability:
  - ``train_and_export`` writes to ``output_dir`` but does not mutate any
    input data or global state.
  - ``load_embeddings`` returns a fresh dict; callers own the arrays.
  - The retrieval function returned by ``embedding_retrieval_fn`` is
    stateless (captures embeddings by reference, does not mutate them).

Mathematical constraints:
  - Embeddings are L2-normalised before cosine similarity search so that
    dot product equals cosine similarity.
  - Retrieval excludes the query index from its own results.
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Optional

import numpy as np
import torch

from jepa_data_spec import (
    JEPADataset,
    build_jepa_dataset,
    build_jepa_dataset_from_array,
    temporal_split,
)
from jepa_retrieval_prototype import WindowEncoder, train_jepa


def train_and_export(
    dataset_names: list[str],
    output_dir: str | Path,
    *,
    window_size: int = 60,
    stride: int = 1,
    latent_dim: int = 64,
    epochs: int = 50,
    batch_size: int = 64,
    lr: float = 1e-3,
    ema_tau: float = 0.996,
    seed: int = 42,
    device: Optional[str] = None,
    verbose: bool = True,
) -> dict[str, Any]:
    """End-to-end JEPA training and embedding export.

    This function:
      1. Loads datasets and windows them via ``build_jepa_dataset``.
      2. Splits indices temporally (70/15/15 train/val/test).
      3. Trains the JEPA encoder on the training split only.
      4. Runs inference on all windows to produce embeddings.
      5. Saves encoder weights, embeddings, and metadata to ``output_dir``.

    Parameters:
        dataset_names: list of short dataset names (e.g. ["spy", "btc_usdt"]).
        output_dir: directory to write artifacts into (created if needed).
        window_size: number of bars per window.
        stride: sliding window step size.
        latent_dim: encoder output dimensionality.
        epochs: training epochs.
        batch_size: mini-batch size for training.
        lr: Adam learning rate.
        ema_tau: EMA momentum for the target encoder.
        seed: random seed for reproducibility.
        device: torch device string; auto-detected if None.
        verbose: print training progress.

    Returns:
        Dict with keys: 'output_dir', 'n_windows', 'latent_dim',
        'embedding_shape', 'final_loss', 'runtime_seconds'.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    started = time.perf_counter()

    # --- 1. Load and window datasets ---
    if verbose:
        print(f"Loading datasets: {dataset_names}")
    dataset: JEPADataset = build_jepa_dataset(
        dataset_names, window_size=window_size, stride=stride
    )
    n_windows = dataset.windows.shape[0]
    if verbose:
        print(f"  {n_windows} windows, shape {dataset.windows.shape}")

    # --- 2. Temporal split ---
    splits = temporal_split(n_windows)
    if verbose:
        print(
            f"  split: train={len(splits.train_idx)}, "
            f"val={len(splits.val_idx)}, test={len(splits.test_idx)}"
        )

    # --- 3. Train on the training split only ---
    # Extract training windows for the JEPA encoder
    train_windows = dataset.windows[splits.train_idx]
    if verbose:
        print(f"Training JEPA encoder ({epochs} epochs, latent_dim={latent_dim})...")

    encoder, loss_history = train_jepa(
        train_windows,
        latent_dim=latent_dim,
        epochs=epochs,
        batch_size=batch_size,
        lr=lr,
        ema_tau=ema_tau,
        seed=seed,
        device=device,
        verbose=verbose,
    )

    # --- 4. Export embeddings for ALL windows (train + val + test) ---
    if verbose:
        print("Exporting embeddings for all windows...")

    if device is None:
        device = "cuda" if torch.cuda.is_available() else "cpu"

    encoder.eval()
    encoder.to(device)
    all_tensor = torch.from_numpy(dataset.windows).float().to(device)

    # Batch inference to avoid OOM on large datasets
    embeddings_list: list[np.ndarray] = []
    with torch.no_grad():
        for start in range(0, n_windows, batch_size):
            batch = all_tensor[start : start + batch_size]
            emb = encoder(batch).cpu().numpy()
            embeddings_list.append(emb)

    embeddings = np.concatenate(embeddings_list, axis=0)  # (n_windows, latent_dim)

    # --- 5. Save artifacts ---
    # 5a. Encoder weights
    encoder_path = output_dir / "encoder.pt"
    torch.save(encoder.cpu().state_dict(), encoder_path)

    # 5b. Embeddings + split indices
    embeddings_path = output_dir / "embeddings.npz"
    np.savez(
        embeddings_path,
        embeddings=embeddings,
        offsets=dataset.window_offsets,
        split_train=splits.train_idx,
        split_val=splits.val_idx,
        split_test=splits.test_idx,
    )

    # 5c. Metadata JSON
    runtime_seconds = time.perf_counter() - started
    metadata = {
        "generated_at": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "dataset_names": dataset_names,
        "n_windows": n_windows,
        "window_size": window_size,
        "stride": stride,
        "latent_dim": latent_dim,
        "embedding_shape": list(embeddings.shape),
        "split_sizes": {
            "train": len(splits.train_idx),
            "val": len(splits.val_idx),
            "test": len(splits.test_idx),
        },
        "training_config": {
            "epochs": epochs,
            "batch_size": batch_size,
            "lr": lr,
            "ema_tau": ema_tau,
            "seed": seed,
        },
        "loss_history": loss_history,
        "final_loss": loss_history[-1] if loss_history else None,
        "runtime_seconds": runtime_seconds,
    }
    metadata_path = output_dir / "metadata.json"
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    if verbose:
        print(f"Artifacts saved to {output_dir}/")
        print(f"  encoder.pt       ({encoder_path.stat().st_size / 1024:.1f} KB)")
        print(f"  embeddings.npz   ({embeddings_path.stat().st_size / 1024:.1f} KB)")
        print(f"  metadata.json")
        print(f"  runtime: {runtime_seconds:.1f}s, final loss: {metadata['final_loss']:.6f}")

    return {
        "output_dir": str(output_dir),
        "n_windows": n_windows,
        "latent_dim": latent_dim,
        "embedding_shape": list(embeddings.shape),
        "final_loss": metadata["final_loss"],
        "runtime_seconds": runtime_seconds,
    }


def train_and_export_from_array(
    prices: np.ndarray,
    output_dir: str | Path,
    *,
    dataset_name: str = "synthetic",
    window_size: int = 60,
    stride: int = 1,
    latent_dim: int = 64,
    epochs: int = 50,
    batch_size: int = 64,
    lr: float = 1e-3,
    ema_tau: float = 0.996,
    seed: int = 42,
    device: Optional[str] = None,
    verbose: bool = False,
) -> dict[str, Any]:
    """Convenience wrapper: train and export from a raw 1-D price array.

    Same as ``train_and_export`` but accepts in-memory data directly.
    Useful for tests and synthetic experiments.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    started = time.perf_counter()

    dataset = build_jepa_dataset_from_array(
        prices, window_size=window_size, stride=stride, dataset_name=dataset_name
    )
    n_windows = dataset.windows.shape[0]
    splits = temporal_split(n_windows)
    train_windows = dataset.windows[splits.train_idx]

    encoder, loss_history = train_jepa(
        train_windows,
        latent_dim=latent_dim,
        epochs=epochs,
        batch_size=batch_size,
        lr=lr,
        ema_tau=ema_tau,
        seed=seed,
        device=device,
        verbose=verbose,
    )

    if device is None:
        device = "cuda" if torch.cuda.is_available() else "cpu"

    encoder.eval()
    encoder.to(device)
    all_tensor = torch.from_numpy(dataset.windows).float().to(device)

    embeddings_list: list[np.ndarray] = []
    with torch.no_grad():
        for start in range(0, n_windows, batch_size):
            batch = all_tensor[start : start + batch_size]
            emb = encoder(batch).cpu().numpy()
            embeddings_list.append(emb)

    embeddings = np.concatenate(embeddings_list, axis=0)

    encoder_path = output_dir / "encoder.pt"
    torch.save(encoder.cpu().state_dict(), encoder_path)

    embeddings_path = output_dir / "embeddings.npz"
    np.savez(
        embeddings_path,
        embeddings=embeddings,
        offsets=dataset.window_offsets,
        split_train=splits.train_idx,
        split_val=splits.val_idx,
        split_test=splits.test_idx,
    )

    runtime_seconds = time.perf_counter() - started
    metadata = {
        "generated_at": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "dataset_names": [dataset_name],
        "n_windows": n_windows,
        "window_size": window_size,
        "stride": stride,
        "latent_dim": latent_dim,
        "embedding_shape": list(embeddings.shape),
        "split_sizes": {
            "train": len(splits.train_idx),
            "val": len(splits.val_idx),
            "test": len(splits.test_idx),
        },
        "training_config": {
            "epochs": epochs,
            "batch_size": batch_size,
            "lr": lr,
            "ema_tau": ema_tau,
            "seed": seed,
        },
        "loss_history": loss_history,
        "final_loss": loss_history[-1] if loss_history else None,
        "runtime_seconds": runtime_seconds,
    }
    (output_dir / "metadata.json").write_text(
        json.dumps(metadata, indent=2), encoding="utf-8"
    )

    return {
        "output_dir": str(output_dir),
        "n_windows": n_windows,
        "latent_dim": latent_dim,
        "embedding_shape": list(embeddings.shape),
        "final_loss": metadata["final_loss"],
        "runtime_seconds": runtime_seconds,
    }


def load_embeddings(output_dir: str | Path) -> dict[str, Any]:
    """Load cached embeddings and metadata from a previous export.

    Parameters:
        output_dir: path to the directory created by ``train_and_export``.

    Returns:
        Dict with keys:
          - 'embeddings': float32 array of shape ``(n_windows, latent_dim)``.
          - 'offsets': int64 array of window offsets.
          - 'split_train', 'split_val', 'split_test': index arrays.
          - 'metadata': parsed JSON metadata dict.

    Raises:
        FileNotFoundError: if embeddings.npz or metadata.json is missing.
    """
    output_dir = Path(output_dir)

    embeddings_path = output_dir / "embeddings.npz"
    metadata_path = output_dir / "metadata.json"

    if not embeddings_path.exists():
        raise FileNotFoundError(f"Embeddings not found: {embeddings_path}")
    if not metadata_path.exists():
        raise FileNotFoundError(f"Metadata not found: {metadata_path}")

    data = np.load(embeddings_path)
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))

    return {
        "embeddings": data["embeddings"],
        "offsets": data["offsets"],
        "split_train": data["split_train"],
        "split_val": data["split_val"],
        "split_test": data["split_test"],
        "metadata": metadata,
    }


def embedding_retrieval_fn(
    embeddings: np.ndarray,
    k: int = 10,
    candidate_mask: Optional[np.ndarray] = None,
) -> Callable[[int], np.ndarray]:
    """Create a cosine-similarity retrieval function over pre-computed embeddings.

    The returned function conforms to the ``RetrievalFn`` protocol defined in
    ``retrieval_harness.py``.

    Implementation:
      1. L2-normalise all embeddings so dot product = cosine similarity.
      2. For a query index, compute dot products against all candidates.
      3. Return the top-k indices (excluding the query itself).

    Parameters:
        embeddings: array of shape ``(N, D)`` — one embedding per window.
        k: number of neighbors to return.
        candidate_mask: optional boolean array of shape ``(N,)``.  If
            provided, only indices where mask is True are candidates.
            Useful for restricting retrieval to the training set only
            (no look-ahead).

    Returns:
        A callable ``query_idx -> np.ndarray`` of top-k neighbor indices.
    """
    # L2-normalise embeddings for cosine similarity via dot product
    norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
    # Avoid division by zero for degenerate embeddings
    norms = np.maximum(norms, 1e-12)
    normed = embeddings / norms  # (N, D)

    # Pre-compute candidate indices
    if candidate_mask is not None:
        candidate_indices = np.where(candidate_mask)[0]
        candidate_embeddings = normed[candidate_indices]
    else:
        candidate_indices = np.arange(len(embeddings))
        candidate_embeddings = normed

    def _retrieve(query_idx: int) -> np.ndarray:
        """Return top-k neighbor indices for a query, excluding the query itself."""
        query = normed[query_idx]  # (D,)
        # Cosine similarity = dot product of L2-normalised vectors
        similarities = candidate_embeddings @ query  # (n_candidates,)

        # Mask out the query itself if it's in the candidate set
        # Find where query_idx appears in candidate_indices
        query_in_candidates = np.where(candidate_indices == query_idx)[0]
        if len(query_in_candidates) > 0:
            similarities[query_in_candidates[0]] = -np.inf

        # Top-k by descending similarity, excluding -inf entries (masked query)
        # Full argsort for correctness (argpartition doesn't sort within partition)
        sorted_local = np.argsort(similarities)[::-1]
        # Filter out any -inf entries (the masked-out query)
        valid = sorted_local[similarities[sorted_local] > -np.inf]
        actual_k = min(k, len(valid))
        if actual_k <= 0:
            return np.array([], dtype=np.int64)

        return candidate_indices[valid[:actual_k]]

    return _retrieve


def _parse_args() -> argparse.Namespace:
    """Parse CLI arguments for the train-and-export pipeline."""
    parser = argparse.ArgumentParser(
        description="Train a JEPA encoder and export embeddings.",
    )
    parser.add_argument(
        "--datasets",
        nargs="+",
        default=["spy", "btc_usdt"],
        help="Short dataset names (e.g. spy btc_usdt).",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="progress/autoresearch/embeddings/run001/",
        help="Output directory for artifacts.",
    )
    parser.add_argument("--window-size", type=int, default=60)
    parser.add_argument("--stride", type=int, default=1)
    parser.add_argument("--latent-dim", type=int, default=64)
    parser.add_argument("--epochs", type=int, default=50)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--ema-tau", type=float, default=0.996)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--device", type=str, default=None)
    return parser.parse_args()


def main() -> None:
    """CLI entry point: train JEPA encoder and export embeddings."""
    args = _parse_args()

    # Resolve output relative to repo root if not absolute
    output = Path(args.output)
    if not output.is_absolute():
        repo_root = Path(__file__).resolve().parents[3]
        output = repo_root / output

    result = train_and_export(
        dataset_names=args.datasets,
        output_dir=output,
        window_size=args.window_size,
        stride=args.stride,
        latent_dim=args.latent_dim,
        epochs=args.epochs,
        batch_size=args.batch_size,
        lr=args.lr,
        ema_tau=args.ema_tau,
        seed=args.seed,
        device=args.device,
        verbose=True,
    )

    print("\n--- Summary ---")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
