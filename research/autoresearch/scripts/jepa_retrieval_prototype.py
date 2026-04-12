"""JEPA retrieval-only prototype for analog pattern matching.

This script implements a Joint Embedding Predictive Architecture (JEPA)
applied to time-series windows.  The goal is to learn latent embeddings
that capture the shape/dynamics of a window so that nearest-neighbour
retrieval in latent space can potentially improve (or complement) the
production 9-method tiered matcher.

**This is research code — intentionally outside production.**

Architecture overview
---------------------
1. **Encoder** — a small 1-D CNN that maps a raw window (length W) to a
   fixed-size latent vector (dimension ``latent_dim``).  We use two copies
   of the same encoder (online and target) following BYOL/JEPA convention;
   the target is an exponential-moving-average (EMA) of the online encoder.

2. **Predictor** — a lightweight MLP that takes the latent of a *masked*
   window and predicts the latent of the *full* window as produced by the
   target encoder.  The loss is purely in latent space (L2 on normalised
   vectors) — **we never reconstruct raw values**, which is the core JEPA
   principle.

3. **Training loop** — given a corpus of windows extracted from a price
   series, mask a random contiguous portion, encode the masked version with
   the online encoder, predict the target latent, and minimise cosine
   distance.  The target encoder is updated via EMA, preventing collapse.

4. **Retrieval** — after training, embed every candidate window with the
   target encoder.  Given a query, find the k nearest neighbours by cosine
   similarity.

5. **Comparison** — retrieve the same query via the production engine
   (``the_similarity.api.search``) and compare top-k overlap and rank
   correlation (Kendall tau).

Requirements (not added to pyproject.toml — research only)
----------------------------------------------------------
- ``torch >= 2.0``
- ``numpy``
- ``scipy`` (for rank correlation)
- ``the_similarity`` (installed in editable mode from the repo)

Usage
-----
    python research/autoresearch/scripts/jepa_retrieval_prototype.py \
        --dataset the-similarity-data/data/stocks/spy/1d.parquet \
        --window-size 60 --top-k 20 --epochs 50

The script prints comparison metrics and optionally writes a JSON report
under ``progress/autoresearch/reports/``.
"""

from __future__ import annotations

import argparse
import copy
import json
import math
import sys
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

# ── Repo root resolution ──────────────────────────────────────────────
# This script lives at  research/autoresearch/scripts/  (depth 3).
REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

# ── Optional heavy imports (fail fast with clear message) ─────────────
try:
    import torch
    import torch.nn as nn
    import torch.nn.functional as F  # noqa: N812 — PyTorch convention
except ImportError as exc:
    raise SystemExit(
        "PyTorch is required for the JEPA prototype.  "
        "Install it with:  pip install torch>=2.0"
    ) from exc

try:
    from scipy.stats import kendalltau
except ImportError as exc:
    raise SystemExit(
        "scipy is required for rank-correlation metrics.  "
        "Install it with:  pip install scipy"
    ) from exc


# =====================================================================
# 1. Encoder  —  1-D CNN mapping a window to a latent vector
# =====================================================================

class WindowEncoder(nn.Module):
    """Small 1-D convolutional encoder for time-series windows.

    Architecture:
        3 × (Conv1d → BatchNorm → GELU → MaxPool)  →  AdaptiveAvgPool  →  Linear

    The input is shape ``(batch, 1, window_size)`` and the output is
    ``(batch, latent_dim)``.  Projection is L2-normalised so that cosine
    similarity reduces to a simple dot product.

    Parameters
    ----------
    window_size : int
        Expected length of raw time-series windows.
    latent_dim : int
        Dimensionality of the output embedding.
    base_channels : int
        Number of channels after the first convolution; doubled at each
        subsequent layer.
    """

    def __init__(
        self,
        window_size: int = 60,
        latent_dim: int = 64,
        base_channels: int = 32,
    ) -> None:
        super().__init__()
        self.window_size = window_size
        self.latent_dim = latent_dim

        # ── Conv backbone ─────────────────────────────────────────────
        # Three conv blocks; kernel=5 captures local shape, pooling
        # progressively reduces temporal length.
        c1, c2, c3 = base_channels, base_channels * 2, base_channels * 4

        self.conv_blocks = nn.Sequential(
            # Block 1:  (1, W) → (c1, W/2)
            nn.Conv1d(1, c1, kernel_size=5, padding=2),
            nn.BatchNorm1d(c1),
            nn.GELU(),
            nn.MaxPool1d(kernel_size=2),

            # Block 2:  (c1, W/2) → (c2, W/4)
            nn.Conv1d(c1, c2, kernel_size=5, padding=2),
            nn.BatchNorm1d(c2),
            nn.GELU(),
            nn.MaxPool1d(kernel_size=2),

            # Block 3:  (c2, W/4) → (c3, W/8)
            nn.Conv1d(c2, c3, kernel_size=5, padding=2),
            nn.BatchNorm1d(c3),
            nn.GELU(),
            nn.MaxPool1d(kernel_size=2),
        )

        # Collapse temporal dimension to a single value per channel.
        self.pool = nn.AdaptiveAvgPool1d(1)

        # Linear projection to latent_dim.
        self.projection = nn.Linear(c3, latent_dim)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """Encode a batch of windows to L2-normalised latent vectors.

        Parameters
        ----------
        x : Tensor of shape ``(batch, 1, window_size)``

        Returns
        -------
        Tensor of shape ``(batch, latent_dim)``  — unit-norm embeddings.
        """
        h = self.conv_blocks(x)       # (B, c3, T')
        h = self.pool(h).squeeze(-1)  # (B, c3)
        z = self.projection(h)        # (B, latent_dim)
        # L2-normalise for cosine retrieval.
        z = F.normalize(z, dim=-1)
        return z


# =====================================================================
# 2. Predictor  —  MLP that maps masked-window latent → full latent
# =====================================================================

class LatentPredictor(nn.Module):
    """Lightweight MLP predicting the target latent from a masked-window latent.

    This is the core JEPA component: the loss is between the predictor
    output and the **target encoder** output (stop-gradient), ensuring the
    model learns to represent structure rather than memorise pixels.

    Parameters
    ----------
    latent_dim : int
        Dimensionality of both input and output latent vectors.
    hidden_dim : int
        Width of the hidden layer.
    """

    def __init__(self, latent_dim: int = 64, hidden_dim: int = 128) -> None:
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(latent_dim, hidden_dim),
            nn.GELU(),
            nn.Linear(hidden_dim, hidden_dim),
            nn.GELU(),
            nn.Linear(hidden_dim, latent_dim),
        )

    def forward(self, z_masked: torch.Tensor) -> torch.Tensor:
        """Predict target latent from masked-window latent.

        Returns L2-normalised output for cosine loss.
        """
        return F.normalize(self.net(z_masked), dim=-1)


# =====================================================================
# 3. Masking strategy
# =====================================================================

def mask_window(
    window: torch.Tensor,
    mask_ratio: float = 0.3,
) -> torch.Tensor:
    """Zero-out a random contiguous segment of a 1-D window.

    We use **contiguous** masking (not random-point dropout) because
    time-series structure is inherently sequential; predicting a missing
    chunk forces the encoder to capture global shape.

    Parameters
    ----------
    window : Tensor of shape ``(batch, 1, W)``
    mask_ratio : float
        Fraction of the window to zero out (0.0–1.0).

    Returns
    -------
    Tensor of same shape with a contiguous zero segment.
    """
    B, _, W = window.shape
    mask_len = max(1, int(W * mask_ratio))

    masked = window.clone()
    for i in range(B):
        # Random start position for the mask.
        start = torch.randint(0, W - mask_len + 1, (1,)).item()
        masked[i, 0, start: start + mask_len] = 0.0
    return masked


# =====================================================================
# 4. EMA update for the target encoder
# =====================================================================

@torch.no_grad()
def update_target_encoder(
    online: nn.Module,
    target: nn.Module,
    momentum: float = 0.996,
) -> None:
    """Exponential-moving-average update of the target encoder.

    Following BYOL / I-JEPA convention, the target encoder weights are a
    slow-moving average of the online encoder weights.  This prevents
    representation collapse without requiring negative pairs.

    Parameters
    ----------
    online : nn.Module
        Online (trainable) encoder.
    target : nn.Module
        Target (EMA) encoder — updated in-place.
    momentum : float
        EMA decay factor.  Closer to 1.0 → slower update.
    """
    for p_online, p_target in zip(online.parameters(), target.parameters()):
        p_target.data.mul_(momentum).add_(p_online.data, alpha=1.0 - momentum)


# =====================================================================
# 5. Window extraction from a numpy array
# =====================================================================

def extract_windows(
    series: np.ndarray,
    window_size: int,
    stride: int = 1,
    normalise: bool = True,
) -> np.ndarray:
    """Slide a fixed-size window over a 1-D series, returning all patches.

    Parameters
    ----------
    series : 1-D numpy array of float values.
    window_size : int
    stride : int
        Step between successive windows.
    normalise : bool
        If True, z-score each window independently (zero mean, unit
        variance).  This mirrors what the production matcher does.

    Returns
    -------
    Array of shape ``(n_windows, window_size)``.
    """
    n = len(series)
    if n < window_size:
        raise ValueError(
            f"Series length {n} < window_size {window_size}; cannot extract windows."
        )
    starts = range(0, n - window_size + 1, stride)
    windows = np.array([series[s: s + window_size] for s in starts], dtype=np.float32)

    if normalise:
        # Per-window z-score; guard against constant windows.
        mu = windows.mean(axis=1, keepdims=True)
        sigma = windows.std(axis=1, keepdims=True)
        sigma = np.where(sigma < 1e-8, 1.0, sigma)  # avoid division by zero
        windows = (windows - mu) / sigma

    return windows


# =====================================================================
# 6. Training loop
# =====================================================================

@dataclass
class TrainingConfig:
    """Hyper-parameters for the JEPA training loop."""

    window_size: int = 60
    latent_dim: int = 64
    base_channels: int = 32
    predictor_hidden: int = 128
    mask_ratio: float = 0.3
    ema_momentum: float = 0.996
    lr: float = 1e-3
    epochs: int = 50
    batch_size: int = 64
    seed: int = 42
    device: str = "cpu"


def train_jepa(
    windows: np.ndarray,
    config: TrainingConfig | None = None,
    verbose: bool = True,
) -> tuple[WindowEncoder, list[float]]:
    """Train a JEPA encoder on extracted windows.

    Parameters
    ----------
    windows : ndarray of shape ``(N, W)``
        Pre-extracted (optionally normalised) windows.
    config : TrainingConfig
    verbose : bool
        Print epoch losses.

    Returns
    -------
    (target_encoder, loss_history)
        The frozen target encoder is what we use for retrieval; the loss
        history is for diagnostics.
    """
    if config is None:
        config = TrainingConfig()

    torch.manual_seed(config.seed)
    np.random.seed(config.seed)

    device = torch.device(config.device)
    W = windows.shape[1]

    # Sanity check: window size in config should match the data.
    if W != config.window_size:
        raise ValueError(
            f"Window width {W} does not match config.window_size {config.window_size}"
        )

    # ── Build models ──────────────────────────────────────────────────
    online_encoder = WindowEncoder(W, config.latent_dim, config.base_channels).to(device)
    target_encoder = copy.deepcopy(online_encoder)
    # Target encoder does not receive gradients.
    for p in target_encoder.parameters():
        p.requires_grad = False

    predictor = LatentPredictor(config.latent_dim, config.predictor_hidden).to(device)

    # ── Optimiser (only online encoder + predictor are trainable) ─────
    params = list(online_encoder.parameters()) + list(predictor.parameters())
    optimiser = torch.optim.AdamW(params, lr=config.lr, weight_decay=1e-4)

    # ── DataLoader (simple tensor dataset) ────────────────────────────
    tensor_data = torch.from_numpy(windows).unsqueeze(1).to(device)  # (N, 1, W)
    dataset = torch.utils.data.TensorDataset(tensor_data)
    loader = torch.utils.data.DataLoader(
        dataset, batch_size=config.batch_size, shuffle=True, drop_last=False
    )

    # ── Training ──────────────────────────────────────────────────────
    loss_history: list[float] = []

    for epoch in range(config.epochs):
        epoch_loss = 0.0
        n_batches = 0

        for (batch,) in loader:
            # 1. Get target latent (no grad).
            with torch.no_grad():
                z_target = target_encoder(batch)  # (B, D)

            # 2. Mask the input and encode with online encoder.
            masked_batch = mask_window(batch, mask_ratio=config.mask_ratio)
            z_online = online_encoder(masked_batch)  # (B, D)

            # 3. Predict target latent from masked-window latent.
            z_pred = predictor(z_online)  # (B, D)

            # 4. Loss: negative cosine similarity (minimise distance).
            # Both z_pred and z_target are L2-normalised, so dot product
            # equals cosine similarity.  We minimise  1 - cos_sim.
            loss = (1.0 - (z_pred * z_target).sum(dim=-1)).mean()

            optimiser.zero_grad()
            loss.backward()
            optimiser.step()

            # 5. EMA update of target encoder.
            update_target_encoder(online_encoder, target_encoder, config.ema_momentum)

            epoch_loss += loss.item()
            n_batches += 1

        avg_loss = epoch_loss / max(n_batches, 1)
        loss_history.append(avg_loss)

        if verbose and (epoch % max(1, config.epochs // 10) == 0 or epoch == config.epochs - 1):
            print(f"  epoch {epoch:4d}/{config.epochs}  loss={avg_loss:.6f}")

    return target_encoder, loss_history


# =====================================================================
# 7. Retrieval in latent space
# =====================================================================

@torch.no_grad()
def embed_windows(
    encoder: WindowEncoder,
    windows: np.ndarray,
    batch_size: int = 256,
    device: str = "cpu",
) -> np.ndarray:
    """Embed all windows using the given encoder.

    Parameters
    ----------
    encoder : WindowEncoder
        Trained (frozen) encoder in eval mode.
    windows : ndarray of shape ``(N, W)``
    batch_size : int
    device : str

    Returns
    -------
    ndarray of shape ``(N, latent_dim)``  — L2-normalised embeddings.
    """
    encoder.eval()
    dev = torch.device(device)
    encoder = encoder.to(dev)

    all_embeddings: list[np.ndarray] = []
    N = len(windows)
    for start in range(0, N, batch_size):
        batch = torch.from_numpy(windows[start: start + batch_size]).unsqueeze(1).to(dev)
        z = encoder(batch)  # (B, D)
        all_embeddings.append(z.cpu().numpy())

    return np.concatenate(all_embeddings, axis=0)


def retrieve_topk(
    query_embedding: np.ndarray,
    corpus_embeddings: np.ndarray,
    k: int = 20,
    exclude_index: int | None = None,
) -> list[tuple[int, float]]:
    """Nearest-neighbour retrieval by cosine similarity.

    Both query and corpus embeddings are assumed to be L2-normalised,
    so cosine similarity = dot product.

    Parameters
    ----------
    query_embedding : 1-D array of shape ``(D,)``
    corpus_embeddings : 2-D array of shape ``(N, D)``
    k : int
        Number of neighbours to return.
    exclude_index : int | None
        Index to exclude from results (e.g. the query itself).

    Returns
    -------
    List of ``(index, similarity)`` tuples sorted by descending similarity.
    """
    # Cosine similarity = dot product (both are unit vectors).
    similarities = corpus_embeddings @ query_embedding  # (N,)

    # Exclude self-match if requested.
    if exclude_index is not None:
        similarities[exclude_index] = -np.inf

    # Partial argsort for top-k (faster than full sort for large N).
    # np.argpartition is O(N), then we sort only the top-k slice.
    if k >= len(similarities):
        top_indices = np.argsort(-similarities)[:k]
    else:
        partition_indices = np.argpartition(-similarities, k)[:k]
        # Sort the top-k by descending similarity.
        sorted_order = np.argsort(-similarities[partition_indices])
        top_indices = partition_indices[sorted_order]

    return [(int(idx), float(similarities[idx])) for idx in top_indices]


# =====================================================================
# 8. Comparison with production engine
# =====================================================================

@dataclass
class ComparisonResult:
    """Metrics comparing JEPA retrieval vs production engine retrieval."""

    query_index: int
    top_k: int
    jepa_indices: list[int]
    production_indices: list[int]
    overlap_count: int
    overlap_ratio: float
    kendall_tau: float | None
    kendall_p_value: float | None


def compare_with_production(
    series_values: np.ndarray,
    query_index: int,
    window_size: int,
    jepa_top_indices: list[int],
    top_k: int = 20,
) -> ComparisonResult:
    """Compare JEPA retrieval results against the production matcher.

    This calls ``the_similarity.api.search()`` with the same query window
    and returns overlap and rank-correlation metrics.

    Parameters
    ----------
    series_values : 1-D numpy array
        The full price/value series (raw, un-normalised).
    query_index : int
        Start index of the query window in the series.
    window_size : int
        Length of the query window.
    jepa_top_indices : list[int]
        Window start indices returned by JEPA retrieval.
    top_k : int
        Number of matches to retrieve from production.

    Returns
    -------
    ComparisonResult with overlap and rank-correlation metrics.
    """
    from the_similarity import load, search

    # Build TimeSeries objects.
    history_ts = load(series_values)
    query_slice = series_values[query_index: query_index + window_size]
    query_ts = load(query_slice)

    # Run production search.
    results = search(query_ts, history_ts, top_k=top_k)

    # Extract start indices of production matches.
    # MatchResult.offset gives the start position in the history.
    production_indices = [int(m.offset) for m in results.matches[:top_k]]

    # ── Overlap ───────────────────────────────────────────────────────
    jepa_set = set(jepa_top_indices[:top_k])
    prod_set = set(production_indices[:top_k])
    overlap = jepa_set & prod_set
    overlap_ratio = len(overlap) / top_k if top_k > 0 else 0.0

    # ── Rank correlation ──────────────────────────────────────────────
    # Build a shared index set and compare rankings.
    shared = sorted(jepa_set & prod_set)
    tau: float | None = None
    p_value: float | None = None
    if len(shared) >= 2:
        # Rank each shared index in both lists.
        jepa_ranks = [jepa_top_indices.index(idx) for idx in shared]
        prod_ranks = [production_indices.index(idx) for idx in shared]
        tau_result = kendalltau(jepa_ranks, prod_ranks)
        tau = float(tau_result.statistic) if not math.isnan(tau_result.statistic) else None
        p_value = float(tau_result.pvalue) if not math.isnan(tau_result.pvalue) else None

    return ComparisonResult(
        query_index=query_index,
        top_k=top_k,
        jepa_indices=jepa_top_indices[:top_k],
        production_indices=production_indices[:top_k],
        overlap_count=len(overlap),
        overlap_ratio=overlap_ratio,
        kendall_tau=tau,
        kendall_p_value=p_value,
    )


# =====================================================================
# 9. CLI entry point
# =====================================================================

DEFAULT_REPORT_DIR = REPO_ROOT / "progress" / "autoresearch" / "reports"


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Train a JEPA encoder and compare retrieval with the production engine."
    )
    p.add_argument(
        "--dataset",
        default="the-similarity-data/data/stocks/spy/1d.parquet",
        help="Repo-relative path to a parquet dataset.",
    )
    p.add_argument("--window-size", type=int, default=60)
    p.add_argument("--top-k", type=int, default=20)
    p.add_argument("--epochs", type=int, default=50)
    p.add_argument("--latent-dim", type=int, default=64)
    p.add_argument("--batch-size", type=int, default=64)
    p.add_argument("--lr", type=float, default=1e-3)
    p.add_argument("--mask-ratio", type=float, default=0.3)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--n-queries", type=int, default=5, help="Number of query windows to evaluate.")
    p.add_argument("--stride", type=int, default=1, help="Window extraction stride.")
    p.add_argument("--device", default="cpu")
    p.add_argument(
        "--write-report",
        action="store_true",
        help="Write a JSON report under progress/autoresearch/reports/.",
    )
    return p.parse_args()


def main() -> None:
    """Full pipeline: extract → train → embed → retrieve → compare."""
    args = _parse_args()

    # ── 1. Load data ──────────────────────────────────────────────────
    from the_similarity import load as ts_load

    dataset_path = REPO_ROOT / args.dataset
    if not dataset_path.exists():
        raise FileNotFoundError(f"Dataset not found: {dataset_path}")

    ts = ts_load(str(dataset_path))
    raw_values = np.array(ts.values, dtype=np.float64)
    print(f"Loaded {len(raw_values)} data points from {args.dataset}")

    # ── 2. Extract windows ────────────────────────────────────────────
    windows = extract_windows(raw_values, args.window_size, stride=args.stride)
    print(f"Extracted {len(windows)} windows (size={args.window_size}, stride={args.stride})")

    # ── 3. Train JEPA ─────────────────────────────────────────────────
    cfg = TrainingConfig(
        window_size=args.window_size,
        latent_dim=args.latent_dim,
        batch_size=args.batch_size,
        lr=args.lr,
        mask_ratio=args.mask_ratio,
        epochs=args.epochs,
        seed=args.seed,
        device=args.device,
    )
    print(f"\nTraining JEPA encoder ({args.epochs} epochs, latent_dim={args.latent_dim}) ...")
    t0 = time.perf_counter()
    encoder, loss_history = train_jepa(windows, cfg, verbose=True)
    train_time = time.perf_counter() - t0
    print(f"Training completed in {train_time:.1f}s  (final loss={loss_history[-1]:.6f})")

    # ── 4. Embed all windows ──────────────────────────────────────────
    print("\nEmbedding all windows ...")
    embeddings = embed_windows(encoder, windows, device=args.device)
    print(f"Embeddings shape: {embeddings.shape}")

    # ── 5. Pick query windows and compare ─────────────────────────────
    rng = np.random.RandomState(args.seed)
    n_windows = len(windows)
    # Pick queries from the middle of the series to allow full exclusion margins.
    margin = args.window_size * 2
    query_indices = rng.choice(
        range(margin, n_windows - margin), size=min(args.n_queries, n_windows - 2 * margin), replace=False
    )

    comparisons: list[ComparisonResult] = []
    print(f"\nComparing retrieval for {len(query_indices)} queries (top_k={args.top_k}) ...")

    for qi in query_indices:
        # JEPA retrieval.
        jepa_results = retrieve_topk(
            embeddings[qi], embeddings, k=args.top_k, exclude_index=qi
        )
        jepa_indices = [idx for idx, _sim in jepa_results]

        # Compare with production.
        try:
            comp = compare_with_production(
                raw_values, int(qi), args.window_size, jepa_indices, top_k=args.top_k
            )
            comparisons.append(comp)
            print(
                f"  query={qi:5d}  overlap={comp.overlap_count}/{comp.top_k}  "
                f"tau={comp.kendall_tau or 'N/A'}"
            )
        except Exception as exc:
            # Production search may fail on short series or edge cases;
            # log and continue.
            print(f"  query={qi:5d}  production comparison failed: {exc}")

    # ── 6. Aggregate metrics ──────────────────────────────────────────
    if comparisons:
        avg_overlap = np.mean([c.overlap_ratio for c in comparisons])
        valid_taus = [c.kendall_tau for c in comparisons if c.kendall_tau is not None]
        avg_tau = float(np.mean(valid_taus)) if valid_taus else None
    else:
        avg_overlap = 0.0
        avg_tau = None

    print("\n── Summary ──────────────────────────────────────────")
    print(f"  Queries evaluated:      {len(comparisons)}")
    print(f"  Avg top-k overlap:      {avg_overlap:.3f}")
    print(f"  Avg Kendall tau:        {avg_tau if avg_tau is not None else 'N/A'}")
    print(f"  Final training loss:    {loss_history[-1]:.6f}")
    print(f"  Training time:          {train_time:.1f}s")

    # ── 7. Optional JSON report ───────────────────────────────────────
    if args.write_report:
        report = {
            "generated_at": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            "lane_id": "jepa-retrieval-lane-v1",
            "experiment": "jepa_retrieval_prototype",
            "parameters": {
                "dataset": args.dataset,
                "window_size": args.window_size,
                "top_k": args.top_k,
                "epochs": args.epochs,
                "latent_dim": args.latent_dim,
                "batch_size": args.batch_size,
                "lr": args.lr,
                "mask_ratio": args.mask_ratio,
                "seed": args.seed,
                "stride": args.stride,
                "n_queries": args.n_queries,
            },
            "training": {
                "final_loss": loss_history[-1],
                "loss_history_sampled": loss_history[::max(1, len(loss_history) // 20)],
                "train_time_seconds": train_time,
            },
            "retrieval_comparison": {
                "n_queries": len(comparisons),
                "avg_overlap_ratio": avg_overlap,
                "avg_kendall_tau": avg_tau,
                "per_query": [asdict(c) for c in comparisons],
            },
        }
        report_path = DEFAULT_REPORT_DIR / "jepa-retrieval-prototype-report.json"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"\nReport written to {report_path.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
