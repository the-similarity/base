"""Smoke tests for the storm-tracks backtest -> registry adapter.

Mirrors ``test_trajectory_3d_adapter.py``: verifies that
``register_storm_backtest_run`` writes a well-formed run row +
collapsed per-predictor scorecard + dataset spec into a fresh
in-memory registry.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from the_similarity.platform.adapters.storms import register_storm_backtest_run
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
    """Realistic-looking predictor metrics from the storm backtest at z=0.0.

    Numbers chosen to match the empirical headline at z_scale=0.0:
    model wins at ~297.5 km vs persistence ~320.8 km. See the concept
    note for the full ablation grid.
    """
    return {
        "model": {
            "spatial_mae_km": 297.50,
            "hit_rate": 0.413,
            "crps": 0.1871,
            "n_trials": 641,
        },
        "persistence": {
            "spatial_mae_km": 320.78,
            "hit_rate": 0.017,
            "crps": 0.2950,
            "n_trials": 641,
        },
        "linear": {
            "spatial_mae_km": 177.27,
            "hit_rate": 0.016,
            "crps": 0.3308,
            "n_trials": 641,
        },
        "random_analogue": {
            "spatial_mae_km": 314.21,
            "hit_rate": 0.435,
            "crps": 0.1830,
            "n_trials": 641,
        },
    }


class TestRegisterStormBacktest:
    def test_registers_run_with_events_kind(self, registry):
        run_id = register_storm_backtest_run(
            predictor_metrics=_sample_metrics(),
            n_storms_train=1629,
            n_storms_test=222,
            n_windows=35591,
            window_len=4,
            forward_bars=4,
            z_scale=0.0,
            primary_predictor="model",
            seed=42,
            registry=registry,
        )
        assert isinstance(run_id, str) and len(run_id) == 32

        record = registry.get_run(run_id)
        assert record is not None
        # World-events pillar — storms are real-world phenomena.
        assert record.kind.value == "events"
        assert record.summary["pillar"] == "events"
        assert record.summary["experiment"] == "storm_tracks_backtest"
        assert record.summary["data_source"] == "noaa_hurdat2_atlantic"
        assert record.summary["primary_predictor"] == "model"
        assert record.summary["spatial_mae_km"] == 297.50
        assert record.summary["z_scale"] == 0.0
        assert record.summary["n_predictors"] == 4

    def test_scorecard_collapses_per_predictor_into_details(self, registry):
        run_id = register_storm_backtest_run(
            predictor_metrics=_sample_metrics(),
            n_storms_train=1629,
            n_storms_test=222,
            n_windows=35591,
            window_len=4,
            forward_bars=4,
            z_scale=5.0,
            seed=7,
            registry=registry,
        )
        sc_list = registry.get_scorecards(run_id)
        assert len(sc_list) == 1
        sc = sc_list[0]
        assert sc.kind == ScorecardKind.BACKTEST
        per_pred = sc.details["per_predictor"]
        assert set(per_pred.keys()) == {
            "model",
            "persistence",
            "linear",
            "random_analogue",
        }
        # Headline numbers come from the primary predictor (model).
        assert sc.details["primary_predictor"] == "model"
        assert sc.details["spatial_mae_km"] == 297.50

    def test_z_scale_recorded_in_config_for_ablation_traceability(self, registry):
        # Two runs at different z-scales must produce distinct config
        # rows so the ablation grid can be reconstructed from the
        # registry alone.
        rid_0 = register_storm_backtest_run(
            predictor_metrics=_sample_metrics(),
            n_storms_train=1629,
            n_storms_test=222,
            n_windows=35591,
            window_len=4,
            forward_bars=4,
            z_scale=0.0,
            registry=registry,
        )
        rid_5 = register_storm_backtest_run(
            predictor_metrics=_sample_metrics(),
            n_storms_train=1629,
            n_storms_test=222,
            n_windows=35591,
            window_len=4,
            forward_bars=4,
            z_scale=5.0,
            registry=registry,
        )
        rec_0 = registry.get_run(rid_0)
        rec_5 = registry.get_run(rid_5)
        assert rec_0.config["z_scale"] == 0.0
        assert rec_5.config["z_scale"] == 5.0
        # Run IDs are distinct so neither overwrites the other.
        assert rid_0 != rid_5

    def test_dataset_spec_registered_when_id_supplied(self, registry):
        register_storm_backtest_run(
            predictor_metrics=_sample_metrics(),
            n_storms_train=1629,
            n_storms_test=222,
            n_windows=35591,
            window_len=4,
            forward_bars=4,
            z_scale=5.0,
            dataset_id="hurdat2-atlantic-v1",
            dataset_name="HURDAT2 Atlantic 1851-2023",
            registry=registry,
        )
        ds = registry.get_dataset("hurdat2-atlantic-v1")
        assert ds is not None
        assert ds.name == "HURDAT2 Atlantic 1851-2023"
        assert ds.metadata["basin"] == "atlantic"
        assert ds.metadata["pillar"] == "events"
        assert ds.metadata["axes"] == ["x_km", "y_km", "z_scaled_wind"]
        # Source URL points back at NHC for self-describing
        # cross-references.
        assert "nhc.noaa.gov" in ds.source

    def test_dataset_id_without_name_raises(self, registry):
        with pytest.raises(ValueError, match="dataset_name is required"):
            register_storm_backtest_run(
                predictor_metrics=_sample_metrics(),
                n_storms_train=10,
                n_storms_test=5,
                n_windows=80,
                window_len=4,
                forward_bars=4,
                z_scale=5.0,
                dataset_id="x",
                dataset_name=None,
                registry=registry,
            )

    def test_explicit_run_id_is_honored(self, registry):
        explicit = "abcdef0123456789abcdef0123456789"
        rid = register_storm_backtest_run(
            predictor_metrics=_sample_metrics(),
            n_storms_train=1,
            n_storms_test=1,
            n_windows=1,
            window_len=4,
            forward_bars=4,
            z_scale=5.0,
            run_id=explicit,
            registry=registry,
        )
        assert rid == explicit
