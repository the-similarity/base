"""Tests for the narrative trajectory compiler.

Covers:
1. Crash -> downward price movement
2. Rally -> upward price movement
3. Total bars == sum of event durations
4. Determinism (same seed -> same output)
5. Registry integration via compile_and_register
6. Unknown event_type raises ValueError
7. Empty events list raises ValueError
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np
import pytest

from the_similarity.narrative.compiler import (
    SUPPORTED_EVENT_TYPES,
    TrajectoryArtifact,
    compile_and_register,
    compile_trajectory,
)
from the_similarity.platform.artifacts import RunKind
from the_similarity.platform.registry import RunRegistry


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _crash_sequence(duration: int = 20, intensity: float = 0.9) -> dict:
    """Single-event crash sequence."""
    return {
        "events": [
            {"event_type": "crash", "intensity": intensity, "duration_bars": duration}
        ]
    }


def _rally_sequence(duration: int = 20, intensity: float = 0.9) -> dict:
    """Single-event rally sequence."""
    return {
        "events": [
            {"event_type": "rally", "intensity": intensity, "duration_bars": duration}
        ]
    }


def _mixed_sequence() -> dict:
    """Multi-event sequence: crash then rally then consolidation."""
    return {
        "events": [
            {"event_type": "crash", "intensity": 0.8, "duration_bars": 15},
            {"event_type": "rally", "intensity": 0.6, "duration_bars": 10},
            {"event_type": "consolidation", "intensity": 0.3, "duration_bars": 25},
        ]
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestCrashDownward:
    """Crash event type produces a downward price trajectory."""

    def test_crash_ends_below_start(self):
        """A high-intensity crash over many bars ends below the base price."""
        prices = compile_trajectory(
            _crash_sequence(duration=30, intensity=1.0), base_price=100.0
        )
        # With 30 bars of max-intensity crash, the end price should be
        # substantially below 100.  We use a generous threshold because
        # stochastic noise can dampen the move.
        assert prices[-1] < 100.0, (
            f"Crash should end below base_price=100, got {prices[-1]:.4f}"
        )

    def test_crash_trend_is_negative(self):
        """The linear regression slope over a crash segment is negative."""
        prices = compile_trajectory(
            _crash_sequence(duration=50, intensity=0.9), base_price=100.0
        )
        # Simple slope: (last - first) / n_bars
        slope = (prices[-1] - prices[0]) / len(prices)
        assert slope < 0, f"Expected negative slope for crash, got {slope:.6f}"


class TestRallyUpward:
    """Rally event type produces an upward price trajectory."""

    def test_rally_ends_above_start(self):
        """A high-intensity rally over many bars ends above the base price."""
        prices = compile_trajectory(
            _rally_sequence(duration=30, intensity=1.0), base_price=100.0
        )
        assert prices[-1] > 100.0, (
            f"Rally should end above base_price=100, got {prices[-1]:.4f}"
        )

    def test_rally_trend_is_positive(self):
        """The linear regression slope over a rally segment is positive."""
        prices = compile_trajectory(
            _rally_sequence(duration=50, intensity=0.9), base_price=100.0
        )
        slope = (prices[-1] - prices[0]) / len(prices)
        assert slope > 0, f"Expected positive slope for rally, got {slope:.6f}"


class TestTotalBars:
    """Total output length == sum of all event durations."""

    def test_single_event_length(self):
        prices = compile_trajectory(_crash_sequence(duration=17))
        assert len(prices) == 17

    def test_multi_event_length(self):
        seq = _mixed_sequence()
        expected = sum(e["duration_bars"] for e in seq["events"])
        prices = compile_trajectory(seq)
        assert len(prices) == expected, f"Expected {expected} bars, got {len(prices)}"


class TestDeterminism:
    """Same inputs + same seed -> identical output array."""

    def test_same_seed_same_output(self):
        seq = _mixed_sequence()
        a = compile_trajectory(seq, seed=123)
        b = compile_trajectory(seq, seed=123)
        np.testing.assert_array_equal(a, b)

    def test_different_seed_different_output(self):
        seq = _mixed_sequence()
        a = compile_trajectory(seq, seed=1)
        b = compile_trajectory(seq, seed=2)
        # Extremely unlikely to be equal with different seeds.
        assert not np.array_equal(a, b)


class TestRegistration:
    """compile_and_register stores a RunRecord in the registry."""

    def test_registers_nl_ts_run(self):
        seq = _mixed_sequence()
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test_registry.db"
            with RunRegistry(db_path) as registry:
                run_id = compile_and_register(seq, registry, base_price=100.0, seed=42)

                # Verify the run is in the registry.
                record = registry.get_run(run_id)
                assert record is not None
                assert record.kind == RunKind.NL_TS
                assert record.seed == 42
                assert record.pillar == "nl_ts"

                # Summary should contain prices and metadata.
                assert "prices" in record.summary
                assert "n_bars" in record.summary
                expected_bars = sum(e["duration_bars"] for e in seq["events"])
                assert record.summary["n_bars"] == expected_bars
                assert len(record.summary["prices"]) == expected_bars

    def test_registered_prices_match_direct_compile(self):
        """Prices stored in registry match a direct compile_trajectory call."""
        seq = _crash_sequence(duration=10)
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test_registry.db"
            with RunRegistry(db_path) as registry:
                run_id = compile_and_register(seq, registry, base_price=50.0, seed=99)
                record = registry.get_run(run_id)
                # Re-compile with same params.
                direct = compile_trajectory(seq, base_price=50.0, seed=99)
                np.testing.assert_allclose(
                    record.summary["prices"], direct.tolist(), rtol=1e-12
                )


class TestEdgeCases:
    """Validation and edge-case handling."""

    def test_unknown_event_type_raises(self):
        seq = {
            "events": [
                {"event_type": "earthquake", "intensity": 0.5, "duration_bars": 5}
            ]
        }
        with pytest.raises(ValueError, match="Unknown event_type"):
            compile_trajectory(seq)

    def test_empty_events_raises(self):
        with pytest.raises(ValueError, match="non-empty"):
            compile_trajectory({"events": []})

    def test_missing_events_key_raises(self):
        with pytest.raises(ValueError, match="non-empty"):
            compile_trajectory({})

    def test_all_supported_event_types_compile(self):
        """Every supported event type compiles without error."""
        for etype in SUPPORTED_EVENT_TYPES:
            seq = {
                "events": [{"event_type": etype, "intensity": 0.5, "duration_bars": 5}]
            }
            prices = compile_trajectory(seq, seed=0)
            assert len(prices) == 5, f"{etype} produced wrong length"
            assert np.all(np.isfinite(prices)), f"{etype} produced non-finite values"

    def test_zero_intensity_produces_near_flat(self):
        """Intensity=0 should produce near-flat prices (only minimal noise)."""
        seq = {
            "events": [{"event_type": "crash", "intensity": 0.0, "duration_bars": 50}]
        }
        prices = compile_trajectory(seq, base_price=100.0)
        # With zero intensity, drift=0 and vol≈0 (clamped to 1e-12),
        # so prices should barely move from 100.
        assert abs(prices[-1] - 100.0) < 1.0, (
            f"Zero-intensity should be near-flat, got end={prices[-1]:.4f}"
        )


class TestTrajectoryArtifact:
    """TrajectoryArtifact dataclass basic checks."""

    def test_construction(self):
        seq = _crash_sequence()
        prices = compile_trajectory(seq)
        artifact = TrajectoryArtifact(
            prices=prices,
            sequence=seq,
            base_price=100.0,
            seed=42,
        )
        assert artifact.prices is prices
        assert artifact.base_price == 100.0
        assert artifact.seed == 42
        assert artifact.sequence is seq
