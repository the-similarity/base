"""Smoke tests for the 3D trajectory backtest -> registry adapter.

Verifies that ``register_trajectory_backtest_run`` writes a
well-formed run row + per-predictor scorecard + dataset spec into
a fresh in-memory registry, and that the CLI / registry queries
return what was written.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from the_similarity.platform.adapters.trajectories import (
    register_trajectory_backtest_run,
)
from the_similarity.platform.contracts import ScorecardKind
from the_similarity.platform.registry import RunRegistry


@pytest.fixture
def registry(tmp_path: Path) -> RunRegistry:
    """Fresh per-test registry under a tmp dir."""
    db = tmp_path / "registry.db"
    reg = RunRegistry(db)
    yield reg
    reg.close()


def _sample_metrics():
    """Realistic-looking predictor metrics from the MVP backtest."""
    return {
        "model": {"spatial_mae": 2.72, "hit_rate": 0.40, "crps": 0.16, "n_trials": 750},
        "persistence": {"spatial_mae": 6.57, "hit_rate": 0.00, "crps": 0.23, "n_trials": 750},
        "linear": {"spatial_mae": 4.21, "hit_rate": 0.37, "crps": 0.17, "n_trials": 750},
        "random_analogue": {"spatial_mae": 2.87, "hit_rate": 0.17, "crps": 0.21, "n_trials": 750},
    }


class TestRegisterTrajectoryBacktest:
    def test_registers_run_with_correct_kind_and_summary(self, registry):
        run_id = register_trajectory_backtest_run(
            predictor_metrics=_sample_metrics(),
            n_agents=50,
            n_ticks=500,
            n_windows=2200,
            window_len=50,
            forward_bars=20,
            primary_predictor="model",
            seed=42,
            registry=registry,
        )
        assert isinstance(run_id, str) and len(run_id) == 32

        record = registry.get_run(run_id)
        assert record is not None
        # Reuse worlds pillar — see adapter docstring for why.
        assert record.kind.value == "worlds"
        # The adapter goes through the legacy RunArtifact path, which
        # doesn't carry a pillar field; the registry stores pillar as
        # NULL and consumers re-derive it via _DEFAULT_PILLAR_FOR_KIND
        # when they need it. We therefore assert via the summary
        # mirror (which DOES carry the explicit pillar tag).
        assert record.summary["pillar"] == "worlds"
        assert record.summary["experiment"] == "trajectory_3d_backtest"
        assert record.summary["primary_predictor"] == "model"
        assert record.summary["spatial_mae"] == 2.72
        assert record.summary["hit_rate"] == 0.40
        assert record.summary["n_predictors"] == 4

    def test_scorecard_collapses_per_predictor_into_details(self, registry):
        run_id = register_trajectory_backtest_run(
            predictor_metrics=_sample_metrics(),
            n_agents=10, n_ticks=100, n_windows=80,
            window_len=20, forward_bars=10,
            seed=7, registry=registry,
        )
        # The adapter merges all predictor scorecards into ONE row
        # because the registry's scorecards table has primary key
        # (run_id, kind). Verify the merge preserved every predictor.
        sc_list = registry.get_scorecards(run_id)
        assert len(sc_list) == 1
        sc = sc_list[0]
        assert sc.kind == ScorecardKind.BACKTEST
        per_pred = sc.details["per_predictor"]
        assert set(per_pred.keys()) == {
            "model", "persistence", "linear", "random_analogue"
        }
        # Headline numbers come from the primary predictor (model).
        assert sc.details["primary_predictor"] == "model"
        assert sc.details["spatial_mae"] == 2.72

    def test_dataset_spec_registered_when_id_supplied(self, registry):
        run_id = register_trajectory_backtest_run(
            predictor_metrics=_sample_metrics(),
            n_agents=50, n_ticks=500, n_windows=2200,
            window_len=50, forward_bars=20,
            dataset_id="traj-corpus-test-v1",
            dataset_name="Trajectory MVP corpus (test)",
            registry=registry,
        )
        ds = registry.get_dataset("traj-corpus-test-v1")
        assert ds is not None
        assert ds.name == "Trajectory MVP corpus (test)"
        assert ds.n_rows == 50 * 500
        assert ds.n_columns == 3
        assert ds.metadata["experiment"] == "trajectory_3d_backtest"
        assert ds.metadata["axes"] == ["x", "y", "z"]

    def test_dataset_id_without_name_raises(self, registry):
        with pytest.raises(ValueError, match="dataset_name is required"):
            register_trajectory_backtest_run(
                predictor_metrics=_sample_metrics(),
                n_agents=10, n_ticks=100, n_windows=80,
                window_len=20, forward_bars=10,
                dataset_id="x", dataset_name=None,
                registry=registry,
            )

    def test_explicit_run_id_is_honored(self, registry):
        explicit = "abcdef0123456789abcdef0123456789"
        rid = register_trajectory_backtest_run(
            predictor_metrics=_sample_metrics(),
            n_agents=1, n_ticks=10, n_windows=1,
            window_len=5, forward_bars=2,
            run_id=explicit, registry=registry,
        )
        assert rid == explicit
