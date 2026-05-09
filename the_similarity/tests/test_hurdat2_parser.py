"""Unit tests for the HURDAT2 fetcher / parser.

These tests exercise ``the-similarity-data/scripts/fetch_hurdat2.py`` on
the committed tiny fixture so CI never has to download from the NHC
endpoint. The fixture covers every parser branch the production data
will hit (header parsing, hemisphere conversion, missing-value
sentinels, status codes, short-track filtering).
"""

from __future__ import annotations

import importlib.util
import math
import sys
from datetime import datetime
from pathlib import Path

import pytest


_REPO_ROOT = Path(__file__).resolve().parents[2]
_FIXTURE_PATH = _REPO_ROOT / "the-similarity-data" / "fixtures" / "hurdat2-tiny.txt"
_FETCHER_PATH = (
    _REPO_ROOT / "the-similarity-data" / "scripts" / "fetch_hurdat2.py"
)


@pytest.fixture(scope="module")
def fetcher_module():
    """Import the fetcher script as a Python module.

    The script lives outside any package (it's a CLI runner under
    ``scripts/``), so we load it via importlib.spec rather than a
    bare ``import``. Module-scoped fixture: importing once amortizes
    the load cost across all tests.
    """
    spec = importlib.util.spec_from_file_location("fetch_hurdat2", _FETCHER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["fetch_hurdat2"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def fixture_text() -> str:
    """The committed tiny HURDAT2 fixture, read once per module."""
    return _FIXTURE_PATH.read_text(encoding="ascii")


class TestHemisphereParsing:
    """Latitude / longitude tokens carry hemispheres as a trailing letter."""

    def test_lat_north_is_positive(self, fetcher_module):
        assert fetcher_module._parse_lat("28.0N") == pytest.approx(28.0)

    def test_lat_south_is_negative(self, fetcher_module):
        # Atlantic basin is N-only but the parser must still honor the
        # sign so a future Pacific extension can reuse it without code
        # changes.
        assert fetcher_module._parse_lat("12.5S") == pytest.approx(-12.5)

    def test_lon_west_is_negative(self, fetcher_module):
        # Most Atlantic storms are western-hemisphere, so this is the
        # important branch for our experiment.
        assert fetcher_module._parse_lon("94.6W") == pytest.approx(-94.6)

    def test_lon_east_is_positive(self, fetcher_module):
        # Late-season recurvers occasionally cross 0E into the eastern
        # hemisphere; the parser must not corrupt their sign.
        assert fetcher_module._parse_lon("12.0E") == pytest.approx(12.0)

    def test_unknown_hemisphere_raises(self, fetcher_module):
        with pytest.raises(ValueError):
            fetcher_module._parse_lat("28.0X")


class TestMissingValueHandling:
    """HURDAT2 uses -99 / -999 as missing-value sentinels."""

    def test_neg99_becomes_nan(self, fetcher_module):
        assert math.isnan(fetcher_module._parse_missing_int("-99"))

    def test_neg999_becomes_nan(self, fetcher_module):
        assert math.isnan(fetcher_module._parse_missing_int("-999"))

    def test_positive_value_passes_through(self, fetcher_module):
        # Wind / pressure tokens in the live data are physically
        # non-negative; they must round-trip exactly.
        assert fetcher_module._parse_missing_int("1005") == pytest.approx(1005.0)

    def test_empty_string_becomes_nan(self, fetcher_module):
        assert math.isnan(fetcher_module._parse_missing_int(""))


class TestHeaderParsing:
    def test_header_yields_storm_id_name_count(self, fetcher_module):
        sid, name, n = fetcher_module._parse_header(
            "AL122005,            KATRINA,    14,"
        )
        assert sid == "AL122005"
        assert name == "KATRINA"
        assert n == 14

    def test_malformed_header_raises(self, fetcher_module):
        with pytest.raises(ValueError):
            fetcher_module._parse_header("AL122005, KATRINA")


class TestFullFixtureParse:
    """Top-level parse_hurdat2_text on the committed fixture."""

    def test_parses_expected_storm_count(self, fetcher_module, fixture_text):
        # Default min_fixes=8. Fixture has 10 storms; the 1900 UNNAMED
        # 3-fix entry should be dropped, leaving 9.
        fixes = fetcher_module.parse_hurdat2_text(fixture_text, min_fixes=8)
        storm_ids = {f.storm_id for f in fixes}
        assert "AL122005" in storm_ids  # KATRINA — passes filter
        assert "AL031900" not in storm_ids  # 3 fixes — fails filter
        # Exactly 9 storms (10 in fixture - 1 short-track).
        assert len(storm_ids) == 9

    def test_min_fixes_filter_can_be_relaxed(self, fetcher_module, fixture_text):
        # Lowering the threshold to 3 keeps the short-track entry.
        fixes = fetcher_module.parse_hurdat2_text(fixture_text, min_fixes=3)
        storm_ids = {f.storm_id for f in fixes}
        assert "AL031900" in storm_ids

    def test_year_extracted_from_storm_id(self, fetcher_module, fixture_text):
        fixes = fetcher_module.parse_hurdat2_text(fixture_text, min_fixes=8)
        years = {f.year for f in fixes}
        # Fixture intentionally spans 1851, 1950, and 2005 to exercise
        # the year-from-id extraction across centuries.
        assert {1851, 1950, 2005}.issubset(years)

    def test_status_codes_preserved_uppercase(self, fetcher_module, fixture_text):
        fixes = fetcher_module.parse_hurdat2_text(fixture_text, min_fixes=8)
        statuses = {f.status for f in fixes}
        # The fixture exercises TD, TS, HU, EX. All uppercase.
        assert {"TD", "TS", "HU", "EX"}.issubset(statuses)

    def test_missing_max_wind_becomes_nan(self, fetcher_module, fixture_text):
        # AL041950 BAKER's first fix uses -99 for max_wind. Verify it
        # parses to NaN rather than -99 (which would bias every
        # downstream metric).
        fixes = fetcher_module.parse_hurdat2_text(fixture_text, min_fixes=8)
        baker_first = next(
            f for f in fixes if f.storm_id == "AL041950" and f.fix_idx == 0
        )
        assert math.isnan(baker_first.max_wind_kt)

    def test_datetime_parsed_correctly(self, fetcher_module, fixture_text):
        fixes = fetcher_module.parse_hurdat2_text(fixture_text, min_fixes=8)
        # Pick KATRINA's landfall fix (fix_idx=9, 22:30 UTC on 25 Aug 2005).
        katrina_landfall = next(
            f
            for f in fixes
            if f.storm_id == "AL122005" and f.fix_idx == 9
        )
        assert katrina_landfall.datetime_utc == datetime(2005, 8, 25, 22, 30)
        assert katrina_landfall.lat == pytest.approx(26.0)
        assert katrina_landfall.lon == pytest.approx(-80.1)
        assert katrina_landfall.max_wind_kt == pytest.approx(70.0)


class TestParquetWrite:
    """Round-trip test: parse fixture, write parquet, re-read."""

    def test_writes_parquet_with_expected_columns(
        self, fetcher_module, fixture_text, tmp_path
    ):
        pyarrow = pytest.importorskip("pyarrow")
        import pyarrow.parquet as pq  # noqa: F401  # imported for round-trip read

        fixes = fetcher_module.parse_hurdat2_text(fixture_text, min_fixes=8)
        out_path = tmp_path / "atlantic.parquet"
        fetcher_module._write_parquet(fixes, out_path)
        assert out_path.exists()

        table = pq.read_table(out_path)
        # Schema must match the documented column set; downstream
        # loaders rely on these names exactly.
        expected_cols = {
            "storm_id",
            "name",
            "year",
            "fix_idx",
            "datetime_utc",
            "lat",
            "lon",
            "max_wind_kt",
            "min_pressure_mb",
            "status",
        }
        assert set(table.column_names) == expected_cols
        assert table.num_rows == len(fixes)
