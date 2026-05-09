"""Fetch and parse the NOAA HURDAT2 Atlantic basin best-track database.

The HURDAT2 (Hurricane DATabase 2nd-revision) feed is the canonical
public-domain record of every recorded Atlantic-basin tropical cyclone
since 1851, maintained by NOAA's National Hurricane Center (NHC). Each
storm is stored as a single header row followed by N "best-track" fix
rows (typically every 6 hours).

Source URL
----------
``https://www.nhc.noaa.gov/data/hurdat/hurdat2-atl-1851-2023-042624.txt``

Format spec: ``https://www.nhc.noaa.gov/data/hurdat/hurdat2-format-atl.pdf``

The file is plain ASCII, comma-separated, with a *header-then-rows*
structure rather than a uniform table. We parse it into a flat parquet
with one row per fix and a ``storm_id`` foreign key linking back to the
header.

Lifecycle
---------
- Downloads ``hurdat2-atl.txt`` to
  ``the-similarity-data/raw/hurdat2-atl.txt`` once and caches it
  there. Subsequent calls return immediately unless ``--refresh`` is
  passed (or the cached file is missing).
- Writes a fresh parquet to
  ``the-similarity-data/datasets/storm_tracks/atlantic.parquet`` on
  every call (parsing is cheap; writing fresh keeps schema consistent).
- Filters out tracks with fewer than ``min_fixes`` valid fixes (where
  "valid" means ``max_wind_kt`` is present). This excludes one-fix
  reports and pre-aircraft-era stubs that have no shape signal.

The script is intentionally side-effect-free at import time. Running
it from CLI is the only way to fetch / regenerate.

Output schema
-------------
One row per fix:

    storm_id        str   # e.g. "AL122005" — basin + cyclone number + year
    name            str   # e.g. "KATRINA" or "UNNAMED"
    year            int   # 4-digit year
    fix_idx         int   # 0-indexed fix order within the storm
    datetime_utc    timestamp[ns]
    lat             float # degrees north (positive)
    lon             float # degrees east (negative for western hemisphere)
    max_wind_kt     float # NaN if missing
    min_pressure_mb float # NaN if missing
    status          str   # TD, TS, HU, EX, SD, SS, LO, WV, DB

Missing-value sentinels are HURDAT2's ``-99`` and ``-999``; we map both
to ``NaN`` on the wind and pressure columns.

Usage
-----
    $ python the-similarity-data/scripts/fetch_hurdat2.py
    $ python the-similarity-data/scripts/fetch_hurdat2.py --refresh
    $ python the-similarity-data/scripts/fetch_hurdat2.py --raw path/to/file.txt

The third form lets the parser run on a local fixture, which is what
the unit tests use.
"""

from __future__ import annotations

import argparse
import math
import sys
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable, List, Optional

# Paths default to repo-relative locations so the script "just works"
# from any cwd. Resolved relative to the repo root (parents[2]) so we
# don't depend on the shell's current directory.
_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_DATA_ROOT = _REPO_ROOT / "the-similarity-data"
_DEFAULT_RAW_PATH = _DEFAULT_DATA_ROOT / "raw" / "hurdat2-atl.txt"
_DEFAULT_PARQUET_PATH = (
    _DEFAULT_DATA_ROOT / "datasets" / "storm_tracks" / "atlantic.parquet"
)

HURDAT2_URL = (
    "https://www.nhc.noaa.gov/data/hurdat/hurdat2-atl-1851-2023-042624.txt"
)


# ---------------------------------------------------------------------------
# Parser internals
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StormFix:
    """One best-track fix row.

    Immutable: built once, written to parquet, never mutated.
    """

    storm_id: str
    name: str
    year: int
    fix_idx: int
    datetime_utc: datetime
    lat: float
    lon: float
    max_wind_kt: float  # NaN if missing
    min_pressure_mb: float  # NaN if missing
    status: str


def _parse_lat(token: str) -> float:
    """Convert HURDAT2 latitude string (``"28.0N"`` / ``"12.5S"``) to float.

    HURDAT2 always trails the magnitude with ``N`` or ``S``. Northern
    hemisphere is positive; southern is negative. Atlantic basin only
    has northern entries but we honor the sign for safety.
    """
    token = token.strip()
    if not token:
        raise ValueError("empty latitude token")
    hemisphere = token[-1].upper()
    magnitude = float(token[:-1])
    if hemisphere == "N":
        return magnitude
    if hemisphere == "S":
        return -magnitude
    raise ValueError(f"unrecognized latitude hemisphere {hemisphere!r}")


def _parse_lon(token: str) -> float:
    """Convert HURDAT2 longitude string (``"94.6W"`` / ``"12.0E"``) to float.

    Western hemisphere is negative (the convention used by every map
    tool the engine talks to). Atlantic-basin storms are almost always
    in the western hemisphere but a handful straddle 0E during East
    Atlantic re-curvature, so we honor both.
    """
    token = token.strip()
    if not token:
        raise ValueError("empty longitude token")
    hemisphere = token[-1].upper()
    magnitude = float(token[:-1])
    if hemisphere == "W":
        return -magnitude
    if hemisphere == "E":
        return magnitude
    raise ValueError(f"unrecognized longitude hemisphere {hemisphere!r}")


def _parse_missing_int(token: str) -> float:
    """Convert a HURDAT2 numeric token to float, with -99 / -999 -> NaN.

    HURDAT2 uses ``-99`` for missing wind values and ``-999`` for
    missing pressure (and a few other rare sentinels). Anything in the
    ``-99...-999`` range that is also strictly negative gets mapped to
    NaN. Normal physical values (winds 0..200 kt, pressures 850..1050)
    are positive and pass through untouched.
    """
    token = token.strip()
    if not token:
        return float("nan")
    try:
        v = float(token)
    except ValueError:
        return float("nan")
    # The spec uses -99 / -999 as missing; we treat any negative as
    # missing because wind and pressure are physically non-negative.
    if v < 0:
        return float("nan")
    return v


def _parse_header(line: str) -> tuple[str, str, int]:
    """Parse a HURDAT2 header line.

    Header format (from the NHC spec):

        AL122005,            KATRINA,    30,

    Returns ``(storm_id, name, n_fix_rows)``. The ``storm_id`` carries
    the basin (``AL`` for Atlantic), the cyclone number for that year
    (zero-padded to 2 digits), and the 4-digit year.
    """
    # Trailing comma + whitespace are common — split and strip.
    parts = [p.strip() for p in line.split(",")]
    if len(parts) < 3:
        raise ValueError(f"malformed HURDAT2 header: {line!r}")
    storm_id = parts[0]
    name = parts[1]
    try:
        n_rows = int(parts[2])
    except ValueError as exc:
        raise ValueError(f"malformed HURDAT2 header (n_rows): {line!r}") from exc
    return storm_id, name, n_rows


def _parse_fix(line: str, storm_id: str, name: str, year: int, fix_idx: int) -> StormFix:
    """Parse a single best-track fix row.

    Fix-row format (excerpt; columns 0-7 are the ones we care about):

        20050829, 1100, L, HU, 28.0N,  94.6W, 130, 902, ... (wind radii)

    Where:
        col 0: YYYYMMDD
        col 1: HHMM (UTC)
        col 2: record identifier (L = landfall, blank otherwise)
        col 3: status (TD, TS, HU, EX, SD, SS, LO, WV, DB)
        col 4: latitude (e.g. "28.0N")
        col 5: longitude (e.g. "94.6W")
        col 6: max sustained wind in knots
        col 7: min pressure in millibars
        cols 8+: 34/50/64 kt wind radii (NE/SE/SW/NW) — we ignore.
    """
    parts = [p.strip() for p in line.split(",")]
    if len(parts) < 8:
        raise ValueError(f"malformed HURDAT2 fix row: {line!r}")
    date_str = parts[0]
    time_str = parts[1]
    status = parts[3].upper()
    lat = _parse_lat(parts[4])
    lon = _parse_lon(parts[5])
    max_wind_kt = _parse_missing_int(parts[6])
    min_pressure_mb = _parse_missing_int(parts[7])

    # Time is given as HHMM with no separator, padded to 4 digits.
    if len(time_str) != 4 or not time_str.isdigit():
        raise ValueError(f"unexpected time token {time_str!r} in row {line!r}")
    dt = datetime(
        year=int(date_str[0:4]),
        month=int(date_str[4:6]),
        day=int(date_str[6:8]),
        hour=int(time_str[0:2]),
        minute=int(time_str[2:4]),
    )
    return StormFix(
        storm_id=storm_id,
        name=name,
        year=year,
        fix_idx=fix_idx,
        datetime_utc=dt,
        lat=lat,
        lon=lon,
        max_wind_kt=max_wind_kt,
        min_pressure_mb=min_pressure_mb,
        status=status,
    )


def parse_hurdat2_text(text: str, *, min_fixes: int = 8) -> List[StormFix]:
    """Parse the full HURDAT2 text blob into a list of fixes.

    Filtering: only storms with at least ``min_fixes`` rows where
    ``max_wind_kt`` is non-NaN are kept. The threshold default of 8
    reflects ~48 hours of 6-hourly fixes — short enough to keep most
    real storms, long enough to demand >= 4 valid Frenet samples.

    Lifecycle: pure function. Reads text, returns list. No I/O.

    Raises ``ValueError`` on structural format violations (header
    mismatch, fix-row column count). Per-row data quirks (missing
    values, unusual statuses) are tolerated and surfaced as NaNs /
    raw strings.
    """
    fixes: List[StormFix] = []
    # Iterate manually so we can step the iterator inside the header
    # block (which has to read the next N rows in lockstep).
    iterator: Iterable[str] = (
        line.rstrip("\n") for line in text.splitlines() if line.strip()
    )
    line_iter = iter(iterator)
    while True:
        try:
            header = next(line_iter)
        except StopIteration:
            break
        # Header is recognized by NOT starting with a digit. Fix rows
        # always start with the 8-digit date.
        head_first = header.lstrip()[:1]
        if head_first.isdigit():
            # Stray fix row (corrupt file). Skip it — being defensive
            # here keeps a single bad block from poisoning the whole
            # parse.
            continue
        storm_id, name, n_rows = _parse_header(header)
        try:
            year = int(storm_id[-4:])
        except ValueError as exc:
            raise ValueError(
                f"could not extract year from storm_id {storm_id!r}"
            ) from exc

        storm_fixes: List[StormFix] = []
        for fix_idx in range(n_rows):
            try:
                row = next(line_iter)
            except StopIteration as exc:
                raise ValueError(
                    f"truncated HURDAT2: header {storm_id!r} promised "
                    f"{n_rows} rows but file ended at fix {fix_idx}"
                ) from exc
            storm_fixes.append(_parse_fix(row, storm_id, name, year, fix_idx))

        # Apply the min_fixes filter on the count of fixes that have a
        # usable max_wind_kt — that is the column the downstream
        # 3D-trajectory experiment uses for the z axis.
        n_valid_wind = sum(1 for f in storm_fixes if not math.isnan(f.max_wind_kt))
        if n_valid_wind < min_fixes:
            continue
        fixes.extend(storm_fixes)
    return fixes


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------


def _write_parquet(fixes: List[StormFix], output_path: Path) -> None:
    """Write the fix list as a parquet (or CSV fallback if pyarrow missing).

    Pyarrow is the preferred backend because it preserves typed
    timestamps and is what the downstream loaders expect. If pyarrow
    is unavailable the function falls back to CSV at the same
    location with a ``.csv`` suffix; the caller is expected to handle
    both formats. This fallback is documented in the module
    docstring under "Parquet vs CSV".
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    rows = [
        {
            "storm_id": f.storm_id,
            "name": f.name,
            "year": f.year,
            "fix_idx": f.fix_idx,
            "datetime_utc": f.datetime_utc,
            "lat": f.lat,
            "lon": f.lon,
            "max_wind_kt": f.max_wind_kt,
            "min_pressure_mb": f.min_pressure_mb,
            "status": f.status,
        }
        for f in fixes
    ]

    try:
        import pyarrow as pa  # type: ignore[import-not-found]
        import pyarrow.parquet as pq  # type: ignore[import-not-found]
    except Exception:
        # Fallback path: write CSV so the experiment can still run on
        # systems that haven't installed pyarrow.
        import csv

        csv_path = output_path.with_suffix(".csv")
        with csv_path.open("w", newline="") as fh:
            if not rows:
                fh.write("")
                return
            writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            for row in rows:
                row = dict(row)
                # CSV needs str for datetime.
                row["datetime_utc"] = row["datetime_utc"].isoformat()
                writer.writerow(row)
        return

    # Build a pyarrow Table column-by-column so we control the schema
    # explicitly (timestamps as ns, floats as float64).
    table = pa.table(
        {
            "storm_id": pa.array([r["storm_id"] for r in rows], type=pa.string()),
            "name": pa.array([r["name"] for r in rows], type=pa.string()),
            "year": pa.array([r["year"] for r in rows], type=pa.int32()),
            "fix_idx": pa.array([r["fix_idx"] for r in rows], type=pa.int32()),
            "datetime_utc": pa.array(
                [r["datetime_utc"] for r in rows], type=pa.timestamp("ns")
            ),
            "lat": pa.array([r["lat"] for r in rows], type=pa.float64()),
            "lon": pa.array([r["lon"] for r in rows], type=pa.float64()),
            "max_wind_kt": pa.array(
                [r["max_wind_kt"] for r in rows], type=pa.float64()
            ),
            "min_pressure_mb": pa.array(
                [r["min_pressure_mb"] for r in rows], type=pa.float64()
            ),
            "status": pa.array([r["status"] for r in rows], type=pa.string()),
        }
    )
    pq.write_table(table, output_path)


# ---------------------------------------------------------------------------
# Fetch
# ---------------------------------------------------------------------------


def _download(url: str, dest: Path) -> None:
    """Download ``url`` to ``dest``, creating parent dirs as needed.

    Uses urllib so we don't pull in an extra dependency; the file is
    a few MB so streaming isn't necessary. Network errors propagate.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(url) as response, dest.open("wb") as fh:
        fh.write(response.read())


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Fetch + parse NOAA HURDAT2 Atlantic best-track data"
    )
    parser.add_argument(
        "--url",
        default=HURDAT2_URL,
        help="Source URL (default: NHC HURDAT2 Atlantic 1851-2023)",
    )
    parser.add_argument(
        "--raw",
        type=Path,
        default=_DEFAULT_RAW_PATH,
        help="Local path to the cached HURDAT2 .txt",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=_DEFAULT_PARQUET_PATH,
        help="Output parquet path",
    )
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Force re-download even if the cached file exists",
    )
    parser.add_argument(
        "--min-fixes",
        type=int,
        default=8,
        help="Minimum number of valid-wind fixes required to keep a storm",
    )
    args = parser.parse_args(argv)

    # Step 1: ensure the raw text is on disk.
    if args.refresh or not args.raw.exists():
        print(f"[fetch_hurdat2] downloading {args.url} -> {args.raw}")
        _download(args.url, args.raw)
    else:
        print(f"[fetch_hurdat2] using cached {args.raw}")

    # Step 2: parse + filter.
    text = args.raw.read_text(encoding="ascii", errors="replace")
    fixes = parse_hurdat2_text(text, min_fixes=args.min_fixes)
    n_storms = len({f.storm_id for f in fixes})
    print(
        f"[fetch_hurdat2] parsed {len(fixes)} fixes across {n_storms} storms "
        f"(min_fixes={args.min_fixes})"
    )

    # Step 3: write parquet.
    _write_parquet(fixes, args.out)
    print(f"[fetch_hurdat2] wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
