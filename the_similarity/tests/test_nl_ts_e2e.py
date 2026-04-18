"""End-to-end tests for the NL-to-time-series pipeline.

Tests the full parse -> compile -> register -> verify flow using the
inline demo components. Each test uses a temporary SQLite registry so
there are no side effects.

Coverage
--------
- test_parse_down_narrative: keyword parser detects "crash" -> direction=down
- test_parse_up_narrative: keyword parser detects "rally" -> direction=up
- test_compile_trajectory_shape: compiler produces correct shape and bounds
- test_e2e_register_and_retrieve: full pipeline round-trip through registry
"""

from __future__ import annotations

import os
import sys
import tempfile

import pytest

# ---------------------------------------------------------------------------
# Path setup — ensure the examples/ directory is importable.
# ---------------------------------------------------------------------------
_THIS = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.abspath(os.path.join(_THIS, os.pardir, os.pardir))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

try:
    import numpy as np

    from the_similarity.platform.artifacts import RunKind
    from the_similarity.platform.registry import RunRegistry

    # Import demo components directly — they are the system under test.
    # We add the examples/ dir to path so the module can be imported.
    _EXAMPLES_DIR = os.path.join(_REPO_ROOT, "examples")
    if _EXAMPLES_DIR not in sys.path:
        sys.path.insert(0, _EXAMPLES_DIR)

    from nl_to_timeseries_demo import (
        NarrativeSchema,
        compile_trajectory,
        parse_narrative,
        register_nl_ts_run,
    )

    _IMPORTS_OK = True
except ImportError:
    _IMPORTS_OK = False

# Skip entire module if imports fail (e.g. missing numpy or platform modules)
pytestmark = pytest.mark.skipif(
    not _IMPORTS_OK,
    reason="NL-to-time-series demo dependencies not available",
)


# =========================================================================
# Test: keyword parser — downward narrative
# =========================================================================


class TestParseNarrative:
    """Verify the keyword parser extracts direction, magnitude, volatility."""

    def test_parse_down_narrative(self) -> None:
        """A narrative with 'crash' and 'volatile' should parse as down/sharp/high."""
        text = (
            "A sharp crash over 20 trading days with extremely volatile "
            "price action as markets plunge on pandemic fears."
        )
        schema = parse_narrative(text)

        assert schema.direction == "down", f"Expected down, got {schema.direction}"
        assert schema.magnitude == "sharp", f"Expected sharp, got {schema.magnitude}"
        assert schema.volatility == "high", f"Expected high, got {schema.volatility}"
        assert schema.duration_days == 20, f"Expected 20, got {schema.duration_days}"
        # At least one keyword should be extracted
        assert len(schema.catalyst_keywords) > 0

    def test_parse_up_narrative(self) -> None:
        """A narrative with 'rally' and 'calm' should parse as up/moderate/low."""
        text = (
            "A moderate recovery rally over 3 months as confidence returns "
            "and volatility calms to pre-crisis levels."
        )
        schema = parse_narrative(text)

        assert schema.direction == "up", f"Expected up, got {schema.direction}"
        assert schema.magnitude == "moderate", f"Expected moderate, got {schema.magnitude}"
        assert schema.volatility == "low", f"Expected low, got {schema.volatility}"
        # 3 months -> 63 trading days
        assert schema.duration_days == 63, f"Expected 63, got {schema.duration_days}"

    def test_parse_sideways_narrative(self) -> None:
        """A narrative with 'range-bound' and 'quiet' should parse as sideways/mild/low."""
        text = (
            "A mild, range-bound market over 4 weeks with quiet, "
            "steady price action."
        )
        schema = parse_narrative(text)

        assert schema.direction == "sideways", f"Expected sideways, got {schema.direction}"
        assert schema.magnitude == "mild", f"Expected mild, got {schema.magnitude}"
        assert schema.volatility == "low", f"Expected low, got {schema.volatility}"
        # 4 weeks -> 20 trading days
        assert schema.duration_days == 20, f"Expected 20, got {schema.duration_days}"

    def test_raw_text_preserved(self) -> None:
        """The original text should be preserved in the schema."""
        text = "Markets crash sharply."
        schema = parse_narrative(text)
        assert schema.raw_text == text


# =========================================================================
# Test: trajectory compiler
# =========================================================================


class TestCompileTrajectory:
    """Verify the trajectory compiler produces correct shapes and bounds."""

    def test_shape_matches_duration(self) -> None:
        """Output length should match duration_days in the schema."""
        schema = NarrativeSchema(
            direction="down",
            magnitude="sharp",
            duration_days=30,
            volatility="high",
        )
        traj = compile_trajectory(schema, seed=42)

        assert traj.shape == (30,), f"Expected (30,), got {traj.shape}"

    def test_prices_positive(self) -> None:
        """All prices should be positive (floored at 1.0)."""
        schema = NarrativeSchema(
            direction="down",
            magnitude="sharp",
            duration_days=100,
            volatility="high",
        )
        traj = compile_trajectory(schema, seed=42)

        assert np.all(traj >= 1.0), "Prices must be >= 1.0"

    def test_deterministic_with_seed(self) -> None:
        """Same seed should produce identical trajectories."""
        schema = NarrativeSchema(
            direction="up",
            magnitude="moderate",
            duration_days=50,
            volatility="normal",
        )
        traj1 = compile_trajectory(schema, seed=123)
        traj2 = compile_trajectory(schema, seed=123)

        np.testing.assert_array_equal(traj1, traj2)

    def test_different_seeds_differ(self) -> None:
        """Different seeds should produce different trajectories."""
        schema = NarrativeSchema(
            direction="up",
            magnitude="moderate",
            duration_days=50,
            volatility="normal",
        )
        traj1 = compile_trajectory(schema, seed=1)
        traj2 = compile_trajectory(schema, seed=2)

        assert not np.array_equal(traj1, traj2), "Different seeds should differ"


# =========================================================================
# Test: full E2E register + retrieve
# =========================================================================


class TestE2ERegisterAndRetrieve:
    """Full pipeline: parse -> compile -> register -> retrieve from registry."""

    def test_round_trip(self) -> None:
        """Parse a narrative, compile, register, and verify retrieval."""
        text = (
            "A sharp sell-off over 25 trading days with volatile price action "
            "as rate hike fears grip the market."
        )

        # Parse
        schema = parse_narrative(text)
        assert schema.direction == "down"

        # Compile
        trajectory = compile_trajectory(schema, seed=99)
        assert len(trajectory) == 25

        # Register in temp registry
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test_registry.db")
            run_id = register_nl_ts_run(schema, trajectory, db_path, seed=99)

            # Retrieve and verify — use list_runs() to get RunRecord
            # objects (which have the pillar field), not the legacy list()
            # which returns RunArtifact objects without pillar.
            registry = RunRegistry(db_path)
            runs = registry.list_runs(kind=RunKind.NL_TS)
            registry.close()

            assert len(runs) == 1, f"Expected 1 run, got {len(runs)}"
            assert runs[0].run_id == run_id
            assert runs[0].pillar == "nl_ts"

            # Verify summary contains expected fields
            summary = runs[0].summary
            assert "start_price" in summary
            assert "end_price" in summary
            assert "total_return_pct" in summary
            assert summary["direction"] == "down"
