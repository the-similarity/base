"""Tests for the_similarity/methods/emd_matcher.py.

Covers EMD decomposition, IMF energy, per-pair matching, and the
convenience emd_score wrapper. EMD is a Tier 2 enrichment method;
the pipeline always pre-normalizes inputs before calling these functions.
"""

import numpy as np
import pytest

from the_similarity.methods.emd_matcher import (
    decompose_emd,
    emd_match,
    emd_score,
    imf_energy,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _composite_signal(n: int = 200, seed: int = 0) -> np.ndarray:
    """Two-component signal: high-frequency + slow trend — typical for finance."""
    rng = np.random.default_rng(seed)
    t = np.linspace(0, 4 * np.pi, n)
    return np.sin(t) + 0.5 * np.sin(5 * t) + 0.05 * rng.standard_normal(n)


def _random_noise(n: int = 200, seed: int = 99) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return rng.standard_normal(n)


# ---------------------------------------------------------------------------
# decompose_emd
# ---------------------------------------------------------------------------


class TestDecomposeEmd:
    """Tests for IMF decomposition."""

    def test_returns_list(self):
        """decompose_emd must return a list of arrays."""
        sig = _composite_signal(200)
        imfs = decompose_emd(sig)
        assert isinstance(imfs, list), f"Expected list, got {type(imfs)}"
        assert len(imfs) >= 1

    def test_max_imfs_respected(self):
        """Number of IMFs must not exceed max_imfs."""
        sig = _composite_signal(200)
        for max_imfs in (2, 4, 6):
            imfs = decompose_emd(sig, max_imfs=max_imfs)
            assert len(imfs) <= max_imfs, (
                f"Expected <= {max_imfs} IMFs, got {len(imfs)}"
            )

    def test_imfs_are_numpy_arrays(self):
        """Every IMF must be a numpy array."""
        sig = _composite_signal(200)
        imfs = decompose_emd(sig)
        for i, imf in enumerate(imfs):
            assert isinstance(imf, np.ndarray), f"IMF {i} is not ndarray"

    def test_constant_series_fallback(self):
        """A constant series should not raise and should return at least one IMF."""
        const = np.ones(100)
        imfs = decompose_emd(const)
        assert len(imfs) >= 1

    def test_typical_signal_produces_multiple_imfs(self):
        """A multi-component signal should decompose into >= 2 IMFs."""
        sig = _composite_signal(200)
        imfs = decompose_emd(sig, max_imfs=6)
        assert len(imfs) >= 2, (
            f"Expected >= 2 IMFs for composite signal, got {len(imfs)}"
        )


# ---------------------------------------------------------------------------
# imf_energy
# ---------------------------------------------------------------------------


class TestImfEnergy:
    """Tests for imf_energy()."""

    def test_energy_non_negative(self):
        """Energy (sum of squares) must be >= 0 for any input."""
        rng = np.random.default_rng(0)
        for _ in range(10):
            arr = rng.standard_normal(50)
            assert imf_energy(arr) >= 0.0

    def test_zero_signal_has_zero_energy(self):
        """All-zeros IMF must have energy 0."""
        assert imf_energy(np.zeros(100)) == 0.0

    def test_energy_equals_sum_of_squares(self):
        """imf_energy must equal np.sum(arr**2)."""
        rng = np.random.default_rng(42)
        arr = rng.standard_normal(80)
        expected = float(np.sum(arr**2))
        assert imf_energy(arr) == pytest.approx(expected, rel=1e-9)

    def test_unit_impulse_energy(self):
        """A single unit impulse has energy = 1.0."""
        arr = np.zeros(10)
        arr[5] = 1.0
        assert imf_energy(arr) == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# emd_match
# ---------------------------------------------------------------------------


class TestEmdMatch:
    """Tests for emd_match() which returns (score, distance) tuples."""

    def test_returns_tuple_of_two(self):
        """emd_match must return a 2-tuple (score, distance)."""
        sig = _composite_signal(120)
        result = emd_match(sig, sig.copy())
        assert isinstance(result, tuple) and len(result) == 2

    def test_identical_signals_high_score(self):
        """Same signal should produce score > 0.8."""
        sig = _composite_signal(200)
        score, dist = emd_match(sig, sig.copy())
        assert score > 0.8, f"Expected score > 0.8 for identical signals, got {score}"

    def test_score_in_unit_interval(self):
        """score part of emd_match result must be in [0, 1]."""
        a = _composite_signal(150, seed=0)
        b = _random_noise(150, seed=5)
        score, dist = emd_match(a, b)
        assert 0.0 <= score <= 1.0, f"Score {score} out of [0, 1]"

    def test_distance_non_negative(self):
        """distance part of emd_match result must be >= 0 or inf."""
        a = _composite_signal(150, seed=0)
        b = _random_noise(150, seed=5)
        _, dist = emd_match(a, b)
        assert dist >= 0.0

    def test_short_series_returns_zero_score(self):
        """Series shorter than 10 bars must return (0.0, inf)."""
        short = np.array([1.0, 2.0, 3.0])
        score, dist = emd_match(short, short)
        assert score == 0.0
        assert dist == float("inf")

    def test_constant_query_returns_zero_score(self):
        """Constant query (zero std) must return (0.0, inf)."""
        const = np.ones(100)
        score, dist = emd_match(const, _composite_signal(100))
        assert score == 0.0
        assert dist == float("inf")

    def test_constant_candidate_returns_zero_score(self):
        """Constant candidate (zero std) must return (0.0, inf)."""
        const = np.ones(100)
        score, dist = emd_match(_composite_signal(100), const)
        assert score == 0.0
        assert dist == float("inf")

    def test_max_imfs_parameter_forwarded(self):
        """max_imfs parameter must not raise and must return valid output."""
        sig = _composite_signal(200)
        for max_imfs in (2, 4, 6):
            score, dist = emd_match(sig, sig.copy(), max_imfs=max_imfs)
            assert 0.0 <= score <= 1.0


# ---------------------------------------------------------------------------
# emd_score
# ---------------------------------------------------------------------------


class TestEmdScore:
    """Tests for the emd_score convenience wrapper."""

    def test_identical_high_score(self):
        """Identical signals must score > 0.8."""
        sig = _composite_signal(200)
        score = emd_score(sig, sig.copy())
        assert score > 0.8, f"Expected > 0.8, got {score}"

    def test_returns_float(self):
        """emd_score must return a Python float."""
        sig = _composite_signal(150)
        score = emd_score(sig, sig.copy())
        assert isinstance(score, float)

    def test_score_range(self):
        """Score must always be in [0, 1] for arbitrary inputs."""
        rng = np.random.default_rng(3)
        for _ in range(8):
            a = rng.standard_normal(120)
            b = rng.standard_normal(120)
            s = emd_score(a, b)
            assert 0.0 <= s <= 1.0, f"Score {s} out of [0, 1]"

    def test_identical_outscores_short_series(self):
        """Identical long signal should score higher than two mismatched short
        signals that each return 0.0 due to the length guard."""
        sig = _composite_signal(200, seed=0)
        score_identical = emd_score(sig, sig.copy())
        # Series shorter than 10 bars returns 0.0
        short = np.array([1.0, 2.0, 3.0])
        score_short = emd_score(short, short)
        assert score_identical > score_short, (
            f"Identical ({score_identical}) should outscore short ({score_short})"
        )

    def test_short_series_returns_zero(self):
        """Series shorter than 10 bars must return 0.0."""
        short = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        assert emd_score(short, short) == 0.0
