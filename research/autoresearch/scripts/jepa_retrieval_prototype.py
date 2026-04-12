"""JEPA retrieval prototype: encoder, predictor, and self-supervised training.

Implements a Joint-Embedding Predictive Architecture (JEPA) for time-series
windows.  The encoder maps raw windows to latent representations; the predictor
maps context-encoder outputs to target-encoder outputs; and the target encoder
is an exponential moving average (EMA) of the context encoder.

Architecture summary:
  - **WindowEncoder**: 1-D CNN that maps ``(B, C, W)`` to ``(B, D)`` where
    D = ``latent_dim``.  Three conv blocks with BatchNorm + ReLU, followed
    by adaptive average pooling and a linear head.
  - **LatentPredictor**: two-layer MLP that maps ``(B, D)`` to ``(B, D)``.
  - **EMA target encoder**: a copy of WindowEncoder whose parameters are
    updated as ``theta_target = tau * theta_target + (1 - tau) * theta_context``
    after each optimiser step.

Training objective:
  The predictor receives the context encoder's output for one view of a window
  and must predict the target encoder's output for a (potentially masked or
  augmented) view.  The loss is mean-squared error in latent space:
      L = MSE(predictor(context_enc(x)), target_enc(x'))

Immutability notes:
  - ``train_jepa`` returns a *new* trained encoder; it does not mutate any
    passed-in model.
  - EMA updates happen in-place on the target encoder copy only.

Mathematical constraints:
  - EMA momentum ``tau`` must be in [0, 1); values near 1 (e.g. 0.996) give
    slow-moving targets which stabilise training.
  - The predictor is intentionally lower capacity than the encoder to prevent
    representation collapse (the predictor cannot simply memorise identity).
"""

from __future__ import annotations

import copy
from typing import Optional

import numpy as np
import torch
import torch.nn as nn


class WindowEncoder(nn.Module):
    """1-D CNN encoder: maps (batch, channels, window_size) -> (batch, latent_dim).

    Three convolutional blocks progressively expand channels from ``in_channels``
    to 64 -> 128 -> 256, each followed by BatchNorm and ReLU.  Adaptive average
    pooling reduces the temporal dimension to 1 before a final linear projection
    to ``latent_dim``.

    Parameters:
        in_channels: number of input channels (1 for univariate).
        latent_dim: dimensionality of the output embedding.
    """

    def __init__(self, in_channels: int = 1, latent_dim: int = 64) -> None:
        super().__init__()
        # Three conv blocks with increasing channel width
        # Kernel size 5 gives a receptive field of ~15 bars after 3 layers
        self.conv_blocks = nn.Sequential(
            nn.Conv1d(in_channels, 64, kernel_size=5, padding=2),
            nn.BatchNorm1d(64),
            nn.ReLU(inplace=True),
            nn.Conv1d(64, 128, kernel_size=5, padding=2),
            nn.BatchNorm1d(128),
            nn.ReLU(inplace=True),
            nn.Conv1d(128, 256, kernel_size=5, padding=2),
            nn.BatchNorm1d(256),
            nn.ReLU(inplace=True),
        )
        # Collapse temporal dimension to a single value per channel
        self.pool = nn.AdaptiveAvgPool1d(1)
        # Project from 256 channels to latent_dim
        self.head = nn.Linear(256, latent_dim)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """Forward pass.

        Args:
            x: tensor of shape ``(B, C, W)``.

        Returns:
            Tensor of shape ``(B, latent_dim)``.
        """
        h = self.conv_blocks(x)  # (B, 256, W)
        h = self.pool(h).squeeze(-1)  # (B, 256)
        return self.head(h)  # (B, latent_dim)


class LatentPredictor(nn.Module):
    """Two-layer MLP predictor: maps (B, D) -> (B, D).

    Intentionally lower capacity than the encoder to prevent collapse.
    Hidden dimension is 2x the latent dimension.
    """

    def __init__(self, latent_dim: int = 64) -> None:
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(latent_dim, latent_dim * 2),
            nn.ReLU(inplace=True),
            nn.Linear(latent_dim * 2, latent_dim),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.net(x)


@torch.no_grad()
def _update_ema(
    online: nn.Module,
    target: nn.Module,
    tau: float,
) -> None:
    """Exponential moving average update of target parameters.

    theta_target = tau * theta_target + (1 - tau) * theta_online

    This runs under torch.no_grad() to avoid tracking gradients for the
    target network — it is not trained by backprop.
    """
    for p_online, p_target in zip(online.parameters(), target.parameters()):
        p_target.data.mul_(tau).add_(p_online.data, alpha=1.0 - tau)


def train_jepa(
    windows: np.ndarray,
    *,
    latent_dim: int = 64,
    epochs: int = 50,
    batch_size: int = 64,
    lr: float = 1e-3,
    ema_tau: float = 0.996,
    seed: int = 42,
    device: Optional[str] = None,
    verbose: bool = True,
) -> tuple[WindowEncoder, list[float]]:
    """Train a JEPA encoder on windowed time-series data.

    Parameters:
        windows: array of shape ``(N, C, W)`` — the full training set.
        latent_dim: embedding dimension.
        epochs: number of training epochs.
        batch_size: mini-batch size.
        lr: Adam learning rate.
        ema_tau: EMA momentum for the target encoder.
        seed: random seed for reproducibility.
        device: 'cpu', 'cuda', or 'mps'.  Auto-detected if None.
        verbose: print epoch losses.

    Returns:
        Tuple of (trained_encoder, loss_history).  The returned encoder is
        the *context* encoder with learned weights.
    """
    if device is None:
        device = "cuda" if torch.cuda.is_available() else "cpu"

    torch.manual_seed(seed)
    np.random.seed(seed)

    in_channels = windows.shape[1]
    context_encoder = WindowEncoder(in_channels=in_channels, latent_dim=latent_dim).to(device)
    target_encoder = copy.deepcopy(context_encoder).to(device)
    predictor = LatentPredictor(latent_dim=latent_dim).to(device)

    # Target encoder is not trained by gradient descent
    for p in target_encoder.parameters():
        p.requires_grad = False

    optimizer = torch.optim.Adam(
        list(context_encoder.parameters()) + list(predictor.parameters()),
        lr=lr,
    )
    loss_fn = nn.MSELoss()

    n_samples = windows.shape[0]
    tensor_data = torch.from_numpy(windows).float().to(device)

    loss_history: list[float] = []

    for epoch in range(epochs):
        # Shuffle indices each epoch for stochastic training
        perm = torch.randperm(n_samples, device=device)
        epoch_loss = 0.0
        n_batches = 0

        for start in range(0, n_samples, batch_size):
            idx = perm[start : start + batch_size]
            batch = tensor_data[idx]

            # Context and target views — for now both are the same window
            # (future: apply masking or augmentation for different views)
            context_out = context_encoder(batch)
            with torch.no_grad():
                target_out = target_encoder(batch)

            pred = predictor(context_out)
            loss = loss_fn(pred, target_out)

            optimizer.zero_grad()
            loss.backward()
            optimizer.step()

            # Update EMA target after each optimiser step
            _update_ema(context_encoder, target_encoder, ema_tau)

            epoch_loss += loss.item()
            n_batches += 1

        avg_loss = epoch_loss / max(n_batches, 1)
        loss_history.append(avg_loss)
        if verbose:
            print(f"  epoch {epoch + 1:3d}/{epochs}  loss={avg_loss:.6f}")

    # Return the context encoder (the one trained by gradient descent)
    context_encoder.eval()
    return context_encoder, loss_history
