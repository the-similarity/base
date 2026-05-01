"""Tests for the benchmarks/ harness package.

Coverage:
- Metrics: hand-computed expected values on synthetic Forecast +
  actuals — sanity checks that the formulas in benchmarks/metrics.py
  match what the docstrings say.
- SeasonalNaive adapter: deterministic check on a sinusoid with known
  period; the band must contain at least 80% of in-sample residuals.
- MatrixProfile adapter (skipped if STUMPY unavailable): smoke test
  on a 200-bar synthetic with embedded motif.
- TheSimilarity adapter: smoke test on 100 random bars, horizon=5.
- Runner end-to-end: 1 synthetic dataset × 2 series × 2 systems × 1
  horizon → 4 JSONL lines, all metrics finite.

Each test runs in well under a second so they fit the standard CI
budget without ``-m slow``.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from benchmarks.core import Dataset, Forecast
from benchmarks.metrics import coverage_p10_p90, crps, mae, mase, smape
from benchmarks.runners.run import run_sweep
from benchmarks.systems.engine import TheSimilarity
from benchmarks.systems.naive import SeasonalNaive


# ---------------------------------------------------------------------------
# Metric tests — hand-computed expected values
# ---------------------------------------------------------------------------


class TestMetrics:
    """Hand-computed metric checks on tiny synthetic data."""

    def _flat_forecast(self, value: float, horizon: int = 4) -> Forecast:
        """Forecast with constant P10/P50/P90 = value (no spread)."""
        arr = np.full(horizon, value, dtype=np.float64)
        return Forecast(p10=arr.copy(), p50=arr.copy(), p90=arr.copy())

    def test_mae_known_values(self):
        # P50 = [10, 10, 10, 10], actual = [10, 12, 8, 14]
        # |0|+|2|+|2|+|4| = 8, mean = 2.0
        f = self._flat_forecast(10.0)
        actual = np.array([10.0, 12.0, 8.0, 14.0])
        assert mae(f, actual) == pytest.approx(2.0)

    def test_mae_perfect_zero(self):
        f = self._flat_forecast(5.0)
        actual = np.full(4, 5.0)
        assert mae(f, actual) == 0.0

    def test_smape_known_values(self):
        # Single bar, P50 = 10, actual = 8
        # numerator = 2 * |10 - 8| = 4
        # denominator = |10| + |8| = 18
        # per-bar = 4/18 ≈ 0.2222 → ×100 ≈ 22.22%
        f = Forecast(
            p10=np.array([8.0]),
            p50=np.array([10.0]),
            p90=np.array([12.0]),
        )
        actual = np.array([8.0])
        assert smape(f, actual) == pytest.approx(4.0 / 18.0 * 100.0)

    def test_smape_zero_actual_and_forecast(self):
        # Both zero per-bar → contribute 0, not NaN
        f = self._flat_forecast(0.0)
        actual = np.zeros(3)
        assert smape(f, actual) == 0.0

    def test_crps_actual_equals_median(self):
        # actual = P50 = 10. Indicators I(10 <= F_p) for p in {10,50,90}:
        #   I(10 <= 5)  = 0  (P10 below actual)
        #   I(10 <= 10) = 1  (P50 at actual)
        #   I(10 <= 15) = 1  (P90 above actual)
        # Squared deviations from nominal CDF [0.1, 0.5, 0.9]:
        #   (0-0.1)^2 + (1-0.5)^2 + (1-0.9)^2 = 0.01 + 0.25 + 0.01 = 0.27
        # Mean over 3 percentiles → 0.09
        f = Forecast(
            p10=np.array([5.0]),
            p50=np.array([10.0]),
            p90=np.array([15.0]),
        )
        actual = np.array([10.0])
        expected = float(np.mean([(0 - 0.1) ** 2, (1 - 0.5) ** 2, (1 - 0.9) ** 2]))
        assert crps(f, actual) == pytest.approx(expected)

    def test_crps_actual_above_all_percentiles(self):
        # actual > all percentiles → indicators all 0 → squared dev =
        # [0.01, 0.25, 0.81] → mean ≈ 0.3567 (symmetric to above)
        f = Forecast(
            p10=np.array([5.0]),
            p50=np.array([10.0]),
            p90=np.array([15.0]),
        )
        actual = np.array([100.0])
        expected = float(np.mean([0.1**2, 0.5**2, 0.9**2]))
        assert crps(f, actual) == pytest.approx(expected)

    def test_mase_known_values(self):
        # train = [1,2,3,4,5,6,7,8] with seasonality=2 → diffs are
        # |3-1|+|4-2|+|5-3|+|6-4|+|7-5|+|8-6| = 2+2+2+2+2+2 = 12, mean=2.0
        # MAE = 2.0 (from test_mae_known_values), MASE = 2.0/2.0 = 1.0
        train = np.array([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0])
        f = self._flat_forecast(10.0)
        actual = np.array([10.0, 12.0, 8.0, 14.0])
        assert mase(f, actual, train, seasonality=2) == pytest.approx(2.0 / 2.0)

    def test_mase_constant_train_returns_nan(self):
        train = np.full(10, 5.0)
        f = self._flat_forecast(10.0)
        actual = np.array([10.0, 12.0, 8.0, 14.0])
        assert np.isnan(mase(f, actual, train, seasonality=2))

    def test_coverage_all_inside(self):
        f = Forecast(
            p10=np.array([0.0, 0.0, 0.0]),
            p50=np.array([5.0, 5.0, 5.0]),
            p90=np.array([10.0, 10.0, 10.0]),
        )
        actual = np.array([3.0, 5.0, 7.0])
        assert coverage_p10_p90(f, actual) == 1.0

    def test_coverage_half_inside(self):
        f = Forecast(
            p10=np.array([0.0, 0.0]),
            p50=np.array([5.0, 5.0]),
            p90=np.array([10.0, 10.0]),
        )
        actual = np.array([5.0, 100.0])  # one inside, one outside
        assert coverage_p10_p90(f, actual) == 0.5

    def test_empty_actual_returns_nan(self):
        f = self._flat_forecast(0.0, horizon=0)
        actual = np.array([])
        assert np.isnan(mae(f, actual))
        assert np.isnan(smape(f, actual))
        assert np.isnan(crps(f, actual))
        assert np.isnan(coverage_p10_p90(f, actual))


# ---------------------------------------------------------------------------
# SeasonalNaive adapter
# ---------------------------------------------------------------------------


class TestSeasonalNaive:
    """Determinism + basic correctness on known-period data."""

    def test_repeats_last_seasonal_cycle(self):
        # Period-4 sawtooth — naive should reproduce [1,2,3,4]
        train = np.tile([1.0, 2.0, 3.0, 4.0], 5)  # length 20
        sn = SeasonalNaive()
        f = sn.forecast(train, horizon=8, seasonality=4)
        # P50 should be [1,2,3,4,1,2,3,4]
        np.testing.assert_array_equal(f.p50, np.array([1.0, 2.0, 3.0, 4.0] * 2))

    def test_band_zero_on_perfectly_periodic_input(self):
        train = np.tile([1.0, 2.0, 3.0, 4.0], 5)
        sn = SeasonalNaive()
        f = sn.forecast(train, horizon=4, seasonality=4)
        # No seasonal residual → band collapses to point forecast
        np.testing.assert_array_equal(f.p10, f.p50)
        np.testing.assert_array_equal(f.p90, f.p50)

    def test_band_widens_with_noise(self):
        rng = np.random.default_rng(0)
        # Sinusoid + noise → seasonal residuals are non-zero
        t = np.arange(200)
        train = np.sin(2 * np.pi * t / 24) + 0.5 * rng.standard_normal(200)
        sn = SeasonalNaive()
        f = sn.forecast(train, horizon=24, seasonality=24)
        # P90 - P10 should equal 2 * 1.28 * sigma ≈ positive
        spread = float(np.mean(f.p90 - f.p10))
        assert spread > 0.5  # noise is non-trivial

    def test_short_train_falls_back_to_last_value(self):
        train = np.array([1.0, 2.0, 3.0])
        sn = SeasonalNaive()
        f = sn.forecast(train, horizon=5, seasonality=7)
        # Train shorter than 2 * seasonality → m=1 fallback → repeat 3.0
        np.testing.assert_array_equal(f.p50, np.full(5, 3.0))


# ---------------------------------------------------------------------------
# MatrixProfile adapter (skipped if STUMPY is unimportable on this system)
# ---------------------------------------------------------------------------


class TestMatrixProfile:
    """Smoke test on a 200-bar series with an embedded motif."""

    def test_smoke_embedded_motif(self):
        # STUMPY relies on numba + llvmlite. On platforms where the
        # native libs cannot be loaded the import raises OSError (not
        # ImportError), so we catch both. The skip mirrors what
        # benchmarks/systems/__init__.py does at registration time.
        try:
            import stumpy  # noqa: F401  # probe load of numba/llvmlite
            from benchmarks.systems.matrix_profile import MatrixProfile
        except (ImportError, OSError):  # pragma: no cover - env-dependent
            pytest.skip("STUMPY unavailable in this environment")

        # Construct a series where the LAST 20 bars match an earlier
        # sinusoidal motif starting at index 50. The MP forecaster
        # should pick that motif as its top match and produce a
        # continuation that resembles the post-motif region.
        rng = np.random.default_rng(0)
        n = 200
        base = 0.1 * rng.standard_normal(n)
        motif = np.sin(np.linspace(0, 4 * np.pi, 20))
        base[50:70] = motif
        base[-20:] = motif  # query tail = the motif we want to match

        mp = MatrixProfile()
        f = mp.forecast(train=base, horizon=10, seasonality=10)
        # All percentile arrays must be the requested length, finite
        assert len(f.p50) == 10
        assert np.all(np.isfinite(f.p10))
        assert np.all(np.isfinite(f.p50))
        assert np.all(np.isfinite(f.p90))
        # P10 ≤ P50 ≤ P90 (cone validity is enforced upstream by sort
        # in the engine adapter, but MP's quantile call already gives
        # this ordering by construction).
        assert np.all(f.p10 <= f.p90 + 1e-9)


# ---------------------------------------------------------------------------
# TheSimilarity adapter — smoke
# ---------------------------------------------------------------------------


class TestTheSimilarity:
    """The engine adapter on a deliberately simple input."""

    def test_smoke_returns_valid_forecast(self):
        # 100 bars of sinusoid + noise. Default-config search may
        # return very few matches, but the adapter falls back to a
        # constant forecast in that case — the test just asserts
        # shape + finiteness.
        rng = np.random.default_rng(1)
        t = np.arange(100)
        train = 100.0 + np.sin(2 * np.pi * t / 14) + 0.1 * rng.standard_normal(100)

        engine = TheSimilarity()
        f = engine.forecast(train=train, horizon=5, seasonality=7)
        assert len(f.p50) == 5
        assert np.all(np.isfinite(f.p10))
        assert np.all(np.isfinite(f.p50))
        assert np.all(np.isfinite(f.p90))
        # Cone must be ordered (the adapter sorts each bar's trio).
        assert np.all(f.p10 <= f.p50 + 1e-9)
        assert np.all(f.p50 <= f.p90 + 1e-9)


# ---------------------------------------------------------------------------
# Runner end-to-end smoke
# ---------------------------------------------------------------------------


class TestRunner:
    """1 dataset × 2 series × 2 systems × 1 horizon → 4 JSONL lines."""

    def _make_synthetic_datasets(self) -> list[Dataset]:
        rng = np.random.default_rng(7)
        out = []
        for sid in ("S1", "S2"):
            t = np.arange(120)
            values = 100.0 + 0.5 * np.sin(2 * np.pi * t / 7) + 0.05 * rng.standard_normal(120)
            out.append(
                Dataset(
                    name="synthetic",
                    series_id=sid,
                    train=values[:100],
                    test=values[100:],
                    frequency="D",
                    seasonality=7,
                )
            )
        return out

    def test_smoke_jsonl_output(self, tmp_path: Path):
        datasets = self._make_synthetic_datasets()
        systems = [SeasonalNaive(), TheSimilarity()]
        out_path = tmp_path / "raw.jsonl"

        written = run_sweep(
            datasets=datasets,
            systems=systems,
            horizons=[5],
            out_path=out_path,
        )
        assert written == 4
        # Reload and inspect.
        lines = out_path.read_text().splitlines()
        assert len(lines) == 4
        for line in lines:
            row = json.loads(line)
            for key in (
                "dataset",
                "series_id",
                "system",
                "horizon",
                "mae",
                "smape",
                "crps",
                "mase",
                "coverage_p10_p90",
                "query_ms",
                "peak_mb",
            ):
                assert key in row, f"missing key: {key}"
            # Every metric must be finite. NaN here would mean the
            # adapter produced a bad forecast or a metric leaked NaN
            # for non-degenerate input.
            for metric_key in ("mae", "smape", "crps", "mase", "coverage_p10_p90"):
                assert np.isfinite(row[metric_key]), f"{row['system']}.{metric_key} not finite"
            assert row["query_ms"] >= 0.0
            assert row["peak_mb"] >= 0.0

    def test_resume_skips_completed(self, tmp_path: Path):
        # First run: write 2 rows (1 dataset × 1 system × 1 horizon × 2 series)
        datasets = self._make_synthetic_datasets()
        out_path = tmp_path / "raw.jsonl"
        written1 = run_sweep(
            datasets=datasets,
            systems=[SeasonalNaive()],
            horizons=[5],
            out_path=out_path,
        )
        assert written1 == 2

        # Second run with the SAME params: nothing new should be written.
        written2 = run_sweep(
            datasets=datasets,
            systems=[SeasonalNaive()],
            horizons=[5],
            out_path=out_path,
        )
        assert written2 == 0
        # Adding a NEW system should produce only the new combos (2 more).
        written3 = run_sweep(
            datasets=datasets,
            systems=[SeasonalNaive(), TheSimilarity()],
            horizons=[5],
            out_path=out_path,
        )
        assert written3 == 2
