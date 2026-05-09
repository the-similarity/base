"""Tests for the HURDAT2 -> 3D Storm dataset loader.

The fixture parquet is built on-the-fly from the committed
``hurdat2-tiny.txt`` so the test is self-contained: no network, no
manually-cached parquet to keep in sync with the fixture.
"""

from __future__ import annotations

import importlib.util
import math
import sys
from pathlib import Path

import numpy as np
import pytest

from the_similarity.datasets.storm_tracks import (
    Storm,
    _equirectangular_project,
    load_storms,
)


_REPO_ROOT = Path(__file__).resolve().parents[2]
_FIXTURE_PATH = _REPO_ROOT / "the-similarity-data" / "fixtures" / "hurdat2-tiny.txt"
_FETCHER_PATH = _REPO_ROOT / "the-similarity-data" / "scripts" / "fetch_hurdat2.py"


def _load_fetcher():
    """Import the fetcher script as a module (mirrors the parser test)."""
    spec = importlib.util.spec_from_file_location("fetch_hurdat2", _FETCHER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["fetch_hurdat2"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def storm_tracks_parquet(tmp_path_factory) -> Path:
    """Build a parquet from the fixture once per test module."""
    pytest.importorskip("pyarrow")
    fetcher = _load_fetcher()
    text = _FIXTURE_PATH.read_text(encoding="ascii")
    fixes = fetcher.parse_hurdat2_text(text, min_fixes=8)
    out = tmp_path_factory.mktemp("storm_tracks") / "atlantic.parquet"
    fetcher._write_parquet(fixes, out)
    return out


# ---------------------------------------------------------------------------
# Projection unit tests
# ---------------------------------------------------------------------------


class TestEquirectangularProjection:
    def test_centroid_maps_to_origin(self):
        # The projection is centered on the centroid by construction;
        # the centroid itself must therefore land at (0, 0).
        lats = np.array([28.0, 28.5, 29.0, 28.5])
        lons = np.array([-94.6, -95.0, -95.4, -95.0])
        x, y = _equirectangular_project(lats, lons)
        # Centroid index isn't a real fix but the *mean* of (x, y)
        # is zero by construction.
        assert float(np.mean(x)) == pytest.approx(0.0, abs=1e-9)
        assert float(np.mean(y)) == pytest.approx(0.0, abs=1e-9)

    def test_known_offset_matches_great_circle_approx(self):
        # 1 degree of latitude ~= 111.32 km. Construct two points
        # exactly 1 deg apart in latitude (same lon) and verify the
        # y-axis offset matches.
        lats = np.array([20.0, 21.0])
        lons = np.array([-50.0, -50.0])
        x, y = _equirectangular_project(lats, lons)
        # y for the second point relative to centroid (20.5):
        # (21.0 - 20.5) * 111.32 = 55.66 km. y for the first should
        # be the negation.
        assert y[1] == pytest.approx(55.66, abs=0.01)
        assert y[0] == pytest.approx(-55.66, abs=0.01)
        # x is exactly zero because lons are identical.
        assert float(np.max(np.abs(x))) == pytest.approx(0.0, abs=1e-9)

    def test_longitude_distance_uses_cosine_correction(self):
        # 1 deg longitude at 60 deg latitude is half of 1 deg at the
        # equator (cos 60 = 0.5). Verify the cos(centroid_lat) factor
        # is being applied.
        lats = np.array([60.0, 60.0])
        lons = np.array([-50.0, -49.0])
        x, _y = _equirectangular_project(lats, lons)
        # x[1] - x[0] = 1 deg * 111.32 * cos(60 deg) = 55.66 km.
        assert float(x[1] - x[0]) == pytest.approx(
            111.32 * math.cos(math.radians(60.0)), abs=0.01
        )


# ---------------------------------------------------------------------------
# load_storms behavior
# ---------------------------------------------------------------------------


class TestLoadStorms:
    def test_returns_storms_with_3d_points(self, storm_tracks_parquet):
        storms = load_storms(storm_tracks_parquet, min_fixes=8)
        assert len(storms) > 0
        for s in storms:
            assert isinstance(s, Storm)
            assert s.points.ndim == 2
            assert s.points.shape[1] == 3
            # No NaNs in the projected points; the loader must
            # interpolate any missing winds before constructing
            # the array.
            assert not np.any(np.isnan(s.points))

    def test_min_fixes_filter_excludes_short_tracks(self, storm_tracks_parquet):
        # The 1900 UNNAMED storm has only 3 fixes — already filtered
        # out at fetcher time when min_fixes=8. Loading with
        # min_fixes=8 should also exclude it. We verify it stays
        # excluded even when we set a stricter threshold here.
        loose = load_storms(storm_tracks_parquet, min_fixes=8)
        strict = load_storms(storm_tracks_parquet, min_fixes=11)
        # KATRINA has 14 fixes — survives strict.
        loose_ids = {s.storm_id for s in loose}
        strict_ids = {s.storm_id for s in strict}
        assert "AL122005" in loose_ids and "AL122005" in strict_ids
        # LEE has 8 fixes (just above default min) — survives loose
        # but not strict.
        assert "AL132005" in loose_ids
        assert "AL132005" not in strict_ids

    def test_z_scale_zero_collapses_to_2d(self, storm_tracks_parquet):
        # The 2D-equivalent baseline: with z_scale=0 the third axis
        # is uniformly zero, which makes torsion identically zero
        # (the "did 3D help?" ablation case).
        storms = load_storms(storm_tracks_parquet, z_scale=0.0)
        for s in storms:
            assert float(np.max(np.abs(s.points[:, 2]))) == 0.0

    def test_z_scale_passes_through_max_wind(self, storm_tracks_parquet):
        # With z_scale=5.0 (default) the z-axis values should be
        # exactly max_wind_kt * 5.0 after interpolation.
        storms = load_storms(storm_tracks_parquet, z_scale=5.0)
        for s in storms:
            wind = s.fix_metadata["max_wind_kt"]
            np.testing.assert_allclose(s.points[:, 2], wind * 5.0)

    def test_storm_metadata_preserved(self, storm_tracks_parquet):
        storms = load_storms(storm_tracks_parquet, min_fixes=8)
        # Find KATRINA — the headline storm in the fixture.
        katrina = next(s for s in storms if s.storm_id == "AL122005")
        assert katrina.name == "KATRINA"
        assert katrina.year == 2005
        # Metadata arrays are aligned with points.
        assert katrina.fix_metadata["max_wind_kt"].shape[0] == katrina.points.shape[0]

    def test_storms_returned_in_chronological_order(self, storm_tracks_parquet):
        storms = load_storms(storm_tracks_parquet, min_fixes=8)
        years = [s.year for s in storms]
        # Sorted ascending — so chronological train/test splits are
        # deterministic across runs.
        assert years == sorted(years)

    def test_negative_z_scale_raises(self, storm_tracks_parquet):
        with pytest.raises(ValueError, match="z_scale must be >= 0"):
            load_storms(storm_tracks_parquet, z_scale=-1.0)
