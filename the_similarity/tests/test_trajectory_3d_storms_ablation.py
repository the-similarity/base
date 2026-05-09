"""Z-scale ablation for the HURDAT2 storm-tracks self-similarity experiment.

Sister test to ``test_trajectory_3d_storms.py``. Runs the same backtest
at four z-scales:

    Z_SCALE = 0.0   -- collapses to 2D; tau is identically zero on
                       planar curves. Tests the "did 3D help?" question.
    Z_SCALE = 1.0   -- mild intensity weighting (1 kt -> 1 km).
    Z_SCALE = 5.0   -- default; 100 kt -> 500 km, balanced metric weight.
    Z_SCALE = 25.0  -- heavy intensity weighting; z dominates the metric.

Identifies the best z-scale empirically. If 0.0 wins, that's the headline
finding — torsion adds no signal for storm tracks and the next experiments
need richer descriptors. The concept note ``obsidian_thesim/concepts/
storm_tracks.md`` carries the analysis.

Marked ``@pytest.mark.slow`` because we run the full backtest 4x.
Total runtime should stay under two minutes; if it exceeds 5 minutes
we downsample the test set further (currently 100 storms).
"""

from __future__ import annotations

import pytest

# Reuse the shared helpers from the headline test. Importing test
# helpers from another test file is unusual but keeps the ablation
# DRY without inventing a sibling-shared module.
from the_similarity.tests.test_trajectory_3d_storms import (
    _PARQUET_PATH,
    _run_predictor_table,
)


@pytest.mark.slow
@pytest.mark.skipif(
    not _PARQUET_PATH.exists(),
    reason=(
        "HURDAT2 parquet missing; run "
        "`python the-similarity-data/scripts/fetch_hurdat2.py` first"
    ),
)
def test_storm_tracks_z_scale_ablation():
    """Backtest the self-similarity primitive at four z-scales.

    Prints a single 4-row x 4-predictor table so the answer to "did
    the 3D embedding help?" is visible at a glance. Identifies the
    best z-scale by smallest model spatial MAE.

    Test passes if the harness produces non-zero trials at every
    z-scale; the experiment outcome is the printed table, not a
    pytest assertion.
    """
    K = 4
    J = 4
    z_scales = [0.0, 1.0, 5.0, 25.0]

    rows: list[tuple[float, dict[str, tuple[float, float, float, int]]]] = []
    for z in z_scales:
        bt_p, bt_l, bt_r, bt_m, n_windows = _run_predictor_table(
            z_scale=z, K=K, J=J
        )
        rows.append(
            (
                z,
                {
                    "persistence": (
                        bt_p.spatial_mae_km,
                        bt_p.hit_rate,
                        bt_p.crps,
                        bt_p.n_trials,
                    ),
                    "linear": (
                        bt_l.spatial_mae_km,
                        bt_l.hit_rate,
                        bt_l.crps,
                        bt_l.n_trials,
                    ),
                    "random_analogue": (
                        bt_r.spatial_mae_km,
                        bt_r.hit_rate,
                        bt_r.crps,
                        bt_r.n_trials,
                    ),
                    "model": (
                        bt_m.spatial_mae_km,
                        bt_m.hit_rate,
                        bt_m.crps,
                        bt_m.n_trials,
                    ),
                },
            )
        )

    # Wide table: rows = z-scale, columns = (predictor, MAE).
    print()
    print("=== HURDAT2 Z-Scale Ablation (MAE_km / hit_rate / CRPS) ===")
    print(f"  Window K={K}, horizon J={J}; per-row trials shown after table\n")
    cell_h = "{:<18}".format("")
    cell_h += " | ".join("z={:>5.1f}".format(z) for z in z_scales)
    print("  " + cell_h)
    print("  " + "-" * len(cell_h))
    for predictor in ["persistence", "linear", "random_analogue", "model"]:
        # MAE row.
        row = "{:<18}".format(f"{predictor} MAE")
        cells = []
        for z, table in rows:
            mae = table[predictor][0]
            cells.append("{:>7.1f}".format(mae))
        row += " | ".join(cells)
        print("  " + row)
    print()
    for predictor in ["persistence", "linear", "random_analogue", "model"]:
        row = "{:<18}".format(f"{predictor} hit")
        cells = []
        for z, table in rows:
            hit = table[predictor][1]
            cells.append("{:>7.3f}".format(hit))
        row += " | ".join(cells)
        print("  " + row)
    print()
    for predictor in ["persistence", "linear", "random_analogue", "model"]:
        row = "{:<18}".format(f"{predictor} CRPS")
        cells = []
        for z, table in rows:
            crps_v = table[predictor][2]
            cells.append("{:>7.4f}".format(crps_v))
        row += " | ".join(cells)
        print("  " + row)
    print()
    print(
        f"  Trials per cell: {rows[0][1]['model'][3]} "
        f"(deterministic; identical across z-scales by construction)\n"
    )

    # Identify best z-scale for the model.
    best_z, best_mae = min(
        ((z, table["model"][0]) for z, table in rows), key=lambda kv: kv[1]
    )
    print(f"  Best z-scale for model: {best_z:.1f}  (MAE_km = {best_mae:.2f})")
    # Compare model best against persistence at that z-scale.
    persistence_at_best = next(
        table["persistence"][0] for z, table in rows if z == best_z
    )
    print(
        f"  At z={best_z:.1f}: model MAE={best_mae:.2f}, "
        f"persistence MAE={persistence_at_best:.2f}"
    )

    # Harness assertion: every row produced trials. Outcome of the
    # ablation is the printed table.
    for z, table in rows:
        for predictor, (_mae, _hit, _crps, n_trials) in table.items():
            assert n_trials > 0, f"Zero trials for {predictor} at z={z}"
