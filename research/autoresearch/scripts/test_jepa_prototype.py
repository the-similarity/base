"""Tests for the JEPA retrieval prototype.

These tests verify the core components with synthetic data — they do NOT
require real datasets or the full production engine.  They are designed
to run quickly (< 10 s) on CPU.

Run with:
    python -m pytest research/autoresearch/scripts/test_jepa_prototype.py -v
"""

from __future__ import annotations

import numpy as np
import pytest
import torch

from jepa_retrieval_prototype import (
    TrainingConfig,
    WindowEncoder,
    LatentPredictor,
    embed_windows,
    extract_windows,
    mask_window,
    retrieve_topk,
    train_jepa,
    update_target_encoder,
)


# ── Fixtures ──────────────────────────────────────────────────────────

WINDOW_SIZE = 30
LATENT_DIM = 16
N_WINDOWS = 50


@pytest.fixture
def synthetic_series() -> np.ndarray:
    """Generate a synthetic sine-based time series."""
    rng = np.random.RandomState(42)
    t = np.linspace(0, 10 * np.pi, 300)
    return np.sin(t) + 0.1 * rng.randn(len(t))


@pytest.fixture
def synthetic_windows(synthetic_series: np.ndarray) -> np.ndarray:
    """Extract normalised windows from the synthetic series."""
    return extract_windows(synthetic_series, WINDOW_SIZE, stride=5)


# ── Encoder tests ─────────────────────────────────────────────────────

class TestWindowEncoder:
    """Verify encoder forward pass and output properties."""

    def test_output_shape(self) -> None:
        """Encoder produces (batch, latent_dim) output."""
        encoder = WindowEncoder(window_size=WINDOW_SIZE, latent_dim=LATENT_DIM)
        x = torch.randn(4, 1, WINDOW_SIZE)
        z = encoder(x)
        assert z.shape == (4, LATENT_DIM)

    def test_output_unit_norm(self) -> None:
        """Output embeddings are L2-normalised (unit vectors)."""
        encoder = WindowEncoder(window_size=WINDOW_SIZE, latent_dim=LATENT_DIM)
        x = torch.randn(8, 1, WINDOW_SIZE)
        z = encoder(x)
        norms = torch.norm(z, dim=-1)
        np.testing.assert_allclose(norms.detach().numpy(), 1.0, atol=1e-5)

    def test_deterministic(self) -> None:
        """Same input → same output in eval mode."""
        encoder = WindowEncoder(window_size=WINDOW_SIZE, latent_dim=LATENT_DIM)
        encoder.eval()
        x = torch.randn(2, 1, WINDOW_SIZE)
        z1 = encoder(x)
        z2 = encoder(x)
        np.testing.assert_array_equal(z1.detach().numpy(), z2.detach().numpy())


# ── Predictor tests ───────────────────────────────────────────────────

class TestLatentPredictor:
    """Verify predictor MLP shape and normalisation."""

    def test_output_shape(self) -> None:
        predictor = LatentPredictor(latent_dim=LATENT_DIM, hidden_dim=32)
        z_in = torch.randn(4, LATENT_DIM)
        z_out = predictor(z_in)
        assert z_out.shape == (4, LATENT_DIM)

    def test_output_unit_norm(self) -> None:
        predictor = LatentPredictor(latent_dim=LATENT_DIM, hidden_dim=32)
        z_in = torch.randn(8, LATENT_DIM)
        z_out = predictor(z_in)
        norms = torch.norm(z_out, dim=-1)
        np.testing.assert_allclose(norms.detach().numpy(), 1.0, atol=1e-5)


# ── Masking tests ─────────────────────────────────────────────────────

class TestMasking:
    """Verify contiguous masking zeroes the expected fraction."""

    def test_mask_creates_zeros(self) -> None:
        x = torch.ones(2, 1, WINDOW_SIZE)
        masked = mask_window(x, mask_ratio=0.3)
        # At least some zeros should exist.
        assert (masked == 0).any()
        # Not everything should be zero.
        assert (masked != 0).any()

    def test_mask_ratio_approximate(self) -> None:
        """Masked fraction should roughly match the requested ratio."""
        x = torch.ones(100, 1, WINDOW_SIZE)
        masked = mask_window(x, mask_ratio=0.5)
        zero_frac = (masked == 0).float().mean().item()
        # Allow generous tolerance — each sample has a random mask.
        assert 0.3 < zero_frac < 0.7


# ── Window extraction tests ──────────────────────────────────────────

class TestExtractWindows:
    """Verify window extraction shape and normalisation."""

    def test_shape(self, synthetic_series: np.ndarray) -> None:
        windows = extract_windows(synthetic_series, WINDOW_SIZE, stride=1)
        expected_n = len(synthetic_series) - WINDOW_SIZE + 1
        assert windows.shape == (expected_n, WINDOW_SIZE)

    def test_stride(self, synthetic_series: np.ndarray) -> None:
        windows = extract_windows(synthetic_series, WINDOW_SIZE, stride=10)
        expected_n = len(range(0, len(synthetic_series) - WINDOW_SIZE + 1, 10))
        assert windows.shape[0] == expected_n

    def test_normalisation(self, synthetic_series: np.ndarray) -> None:
        """Each window should be approximately zero-mean, unit-variance."""
        windows = extract_windows(synthetic_series, WINDOW_SIZE, stride=5, normalise=True)
        means = windows.mean(axis=1)
        stds = windows.std(axis=1)
        np.testing.assert_allclose(means, 0.0, atol=1e-5)
        np.testing.assert_allclose(stds, 1.0, atol=0.1)


# ── EMA update test ──────────────────────────────────────────────────

class TestEMAUpdate:
    """Verify target encoder tracks online encoder via EMA."""

    def test_ema_moves_target(self) -> None:
        online = WindowEncoder(window_size=WINDOW_SIZE, latent_dim=LATENT_DIM)
        target = WindowEncoder(window_size=WINDOW_SIZE, latent_dim=LATENT_DIM)

        # Make them different.
        with torch.no_grad():
            for p in online.parameters():
                p.add_(torch.randn_like(p) * 0.1)

        # Snapshot before.
        before = {n: p.clone() for n, p in target.named_parameters()}

        update_target_encoder(online, target, momentum=0.9)

        # At least one parameter should have changed.
        any_changed = False
        for n, p in target.named_parameters():
            if not torch.equal(p, before[n]):
                any_changed = True
                break
        assert any_changed, "EMA update did not change any target parameters"


# ── Training smoke test ──────────────────────────────────────────────

class TestTraining:
    """Smoke-test the training loop on synthetic data."""

    def test_train_returns_encoder_and_losses(self, synthetic_windows: np.ndarray) -> None:
        """Training completes and loss decreases over epochs."""
        cfg = TrainingConfig(
            window_size=WINDOW_SIZE,
            latent_dim=LATENT_DIM,
            base_channels=8,       # tiny model for speed
            predictor_hidden=16,
            epochs=5,
            batch_size=16,
            seed=42,
        )
        encoder, losses = train_jepa(synthetic_windows, cfg, verbose=False)

        assert isinstance(encoder, WindowEncoder)
        assert len(losses) == 5
        # Loss should be finite.
        assert all(np.isfinite(l) for l in losses)


# ── Embedding tests ──────────────────────────────────────────────────

class TestEmbedding:
    """Verify embedding of a window corpus."""

    def test_embed_shape(self, synthetic_windows: np.ndarray) -> None:
        encoder = WindowEncoder(window_size=WINDOW_SIZE, latent_dim=LATENT_DIM)
        encoder.eval()
        embeddings = embed_windows(encoder, synthetic_windows)
        assert embeddings.shape == (len(synthetic_windows), LATENT_DIM)

    def test_embed_unit_norm(self, synthetic_windows: np.ndarray) -> None:
        encoder = WindowEncoder(window_size=WINDOW_SIZE, latent_dim=LATENT_DIM)
        encoder.eval()
        embeddings = embed_windows(encoder, synthetic_windows)
        norms = np.linalg.norm(embeddings, axis=1)
        np.testing.assert_allclose(norms, 1.0, atol=1e-5)


# ── Retrieval tests ──────────────────────────────────────────────────

class TestRetrieval:
    """Verify nearest-neighbour retrieval returns expected results."""

    def test_returns_k_results(self) -> None:
        """retrieve_topk returns exactly k results."""
        rng = np.random.RandomState(42)
        corpus = rng.randn(100, LATENT_DIM).astype(np.float32)
        # L2-normalise.
        corpus = corpus / np.linalg.norm(corpus, axis=1, keepdims=True)
        query = corpus[0]

        results = retrieve_topk(query, corpus, k=10, exclude_index=0)
        assert len(results) == 10
        # Self should be excluded.
        assert all(idx != 0 for idx, _ in results)

    def test_results_sorted_descending(self) -> None:
        """Results should be sorted by descending similarity."""
        rng = np.random.RandomState(123)
        corpus = rng.randn(50, LATENT_DIM).astype(np.float32)
        corpus = corpus / np.linalg.norm(corpus, axis=1, keepdims=True)
        query = corpus[5]

        results = retrieve_topk(query, corpus, k=10, exclude_index=5)
        sims = [s for _, s in results]
        assert sims == sorted(sims, reverse=True)

    def test_self_is_best_without_exclusion(self) -> None:
        """Without exclusion, the query itself should be the top match."""
        rng = np.random.RandomState(7)
        corpus = rng.randn(30, LATENT_DIM).astype(np.float32)
        corpus = corpus / np.linalg.norm(corpus, axis=1, keepdims=True)
        query = corpus[10]

        results = retrieve_topk(query, corpus, k=5, exclude_index=None)
        # Top result should be index 10 (self) with similarity ~1.0.
        assert results[0][0] == 10
        np.testing.assert_allclose(results[0][1], 1.0, atol=1e-5)
