"""Storm trajectory loading and 3D embedding for self-similarity experiments.

Lifecycle: storms loaded from parsed HURDAT2 parquet at module call time;
no caching beyond the parquet file. Each Storm holds its own (N, 3) array
with no shared mutable state.

Coordinate system: equirectangular projection at per-storm centroid latitude
(local enough for storm-scale paths). x_km, y_km in kilometers; z is scaled
max wind (default Z_SCALE=5.0, so 100 kt -> 500 km, comparable to typical
horizontal extent).

Why per-storm centroid: keeps projection distortion small without paying
for a global UTM grid. The downstream Frenet descriptors are
rotation/translation-invariant, so the centroid choice doesn't affect
similarity comparisons across storms.

Why max_wind (not pressure) for the z axis
------------------------------------------
HURDAT2 reports both max sustained wind (kt) and minimum central
pressure (mb). Wind is the canonical storm-strength metric AND has
denser missing-value patterns (older storms often lack pressure but
do report wind). For the third dimension to be useful for shape
matching it must exist on most fixes; max_wind is the better column.

Why a per-storm centroid (not a global projection)
--------------------------------------------------
A single storm spans <30 deg latitude, so equirectangular projection
distortion at the storm's centroid is < 0.5%. Using a per-storm
centroid lets two storms with different latitudes be compared on
their own native scale without first projecting through a shared
global grid (which would entangle similarity with absolute position).
The Frenet (kappa, tau) descriptors are translation- and
rotation-invariant, so the absolute centroid choice does not affect
shape-similarity rankings between storms.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, List, Mapping

import numpy as np
from numpy.typing import NDArray


# Earth-radius constant: 1 deg latitude ~= 111.32 km. Equirectangular
# projection scales 1 deg longitude by cos(lat). Both are documented
# inline at every call site rather than imported from a constants
# module so the math is legible during code review.
_KM_PER_DEG = 111.32


# ---------------------------------------------------------------------------
# Storm dataclass
# ---------------------------------------------------------------------------


@dataclass
class Storm:
    """One storm trajectory in 3D form.

    Fields
    ------
    storm_id:
        HURDAT2 BASIN+CYCLONE+YEAR identifier (e.g. "AL122005").
    name:
        Human-readable storm name (e.g. "KATRINA"). Many older
        storms are "UNNAMED".
    year:
        4-digit calendar year of the first fix.
    points:
        ``(N, 3)`` float64 array of (x_km, y_km, z_scaled) samples
        in the equirectangular projection. Lifecycle: built once at
        load time, treated as immutable downstream.
    fix_metadata:
        Lightweight dict carrying per-row provenance: 'datetime_utc'
        timestamps, 'lat'/'lon' raw degrees, 'max_wind_kt',
        'min_pressure_mb', 'status'. Stored as 1D arrays aligned
        with ``points`` so the caller can join them after the fact
        without going back to parquet.
    """

    storm_id: str
    name: str
    year: int
    points: NDArray[np.float64]
    fix_metadata: Mapping[str, Any]


# ---------------------------------------------------------------------------
# Equirectangular projection
# ---------------------------------------------------------------------------


def _equirectangular_project(
    lats: NDArray[np.float64], lons: NDArray[np.float64]
) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    """Project lat/lon pairs to (x_km, y_km) using equirectangular at the centroid.

    Algorithm:
        centroid_lat = mean(lats)
        x_km = (lon - centroid_lon) * 111.32 * cos(centroid_lat * pi/180)
        y_km = (lat - centroid_lat) * 111.32

    The projection is local-tangent: it minimizes distortion within
    a few hundred km of the centroid (which storm-scale paths fit
    inside) while keeping the math trivial. We do NOT use a global
    UTM zone because storms cross zones routinely.

    Returns ``(x_km, y_km)`` arrays of the same shape as the inputs.

    Parameters
    ----------
    lats, lons:
        Same-length float64 arrays of latitude / longitude in degrees.
        Latitude positive north; longitude positive east (standard
        signed convention — west is negative).
    """
    if lats.shape != lons.shape:
        raise ValueError(f"lat / lon shape mismatch: {lats.shape} vs {lons.shape}")
    if lats.size == 0:
        return np.empty(0, dtype=np.float64), np.empty(0, dtype=np.float64)

    centroid_lat = float(np.mean(lats))
    centroid_lon = float(np.mean(lons))
    # cos(centroid_lat) is computed once and broadcast; this is the
    # only call site so we do not bother memoizing.
    cos_lat = math.cos(math.radians(centroid_lat))
    x_km = (lons - centroid_lon) * _KM_PER_DEG * cos_lat
    y_km = (lats - centroid_lat) * _KM_PER_DEG
    return x_km.astype(np.float64), y_km.astype(np.float64)


# ---------------------------------------------------------------------------
# Public loader
# ---------------------------------------------------------------------------


def _read_parquet_or_csv(path: Path) -> Mapping[str, NDArray[np.float64]]:
    """Read either a parquet (preferred) or csv fallback into column arrays.

    Returning a dict-of-arrays rather than a DataFrame keeps the
    rest of this module independent of pandas (which is heavy and
    not always installed in CI minimal envs).
    """
    if path.suffix == ".csv":
        # Lazy import to keep csv-only environments importable.
        import csv

        cols: dict[str, list] = {
            "storm_id": [],
            "name": [],
            "year": [],
            "fix_idx": [],
            "datetime_utc": [],
            "lat": [],
            "lon": [],
            "max_wind_kt": [],
            "min_pressure_mb": [],
            "status": [],
        }
        with path.open("r") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                cols["storm_id"].append(row["storm_id"])
                cols["name"].append(row["name"])
                cols["year"].append(int(row["year"]))
                cols["fix_idx"].append(int(row["fix_idx"]))
                cols["datetime_utc"].append(row["datetime_utc"])
                cols["lat"].append(float(row["lat"]))
                cols["lon"].append(float(row["lon"]))
                cols["max_wind_kt"].append(float(row["max_wind_kt"] or "nan"))
                cols["min_pressure_mb"].append(float(row["min_pressure_mb"] or "nan"))
                cols["status"].append(row["status"])
        return {
            "storm_id": np.asarray(cols["storm_id"], dtype=object),
            "name": np.asarray(cols["name"], dtype=object),
            "year": np.asarray(cols["year"], dtype=np.int32),
            "fix_idx": np.asarray(cols["fix_idx"], dtype=np.int32),
            "datetime_utc": np.asarray(cols["datetime_utc"], dtype=object),
            "lat": np.asarray(cols["lat"], dtype=np.float64),
            "lon": np.asarray(cols["lon"], dtype=np.float64),
            "max_wind_kt": np.asarray(cols["max_wind_kt"], dtype=np.float64),
            "min_pressure_mb": np.asarray(cols["min_pressure_mb"], dtype=np.float64),
            "status": np.asarray(cols["status"], dtype=object),
        }

    # Parquet path. We prefer pyarrow which is the canonical writer
    # for our pipeline.
    import pyarrow.parquet as pq  # type: ignore[import-not-found]

    table = pq.read_table(path)
    out: dict[str, NDArray[Any]] = {}
    for col in table.column_names:
        # to_numpy(zero_copy_only=False) handles both numeric and
        # object-typed columns cleanly.
        out[col] = table[col].to_numpy(zero_copy_only=False)
    return out


def load_storms(
    parquet_path: Path | str,
    *,
    min_fixes: int = 8,
    z_scale: float = 5.0,
) -> List[Storm]:
    """Load storms from a HURDAT2-derived parquet into 3D Storm objects.

    Parameters
    ----------
    parquet_path:
        Path to the parquet file produced by
        ``the-similarity-data/scripts/fetch_hurdat2.py``. CSV files
        with the same schema are also accepted (the fetcher's
        fallback when pyarrow is missing).
    min_fixes:
        Reject storms with fewer than this many fixes that have
        valid (non-NaN) ``max_wind_kt``. The 3D embedding fills
        missing winds with linear interpolation, so we still need a
        floor on how much real signal each track carries. Default
        ``8`` matches the fetcher's default.
    z_scale:
        Scalar multiplier on max_wind_kt for the z-axis. Default
        5.0 puts a 100 kt storm at z=500 km, comparable to typical
        horizontal track extents (~1000-3000 km). ``z_scale=0.0``
        collapses to 2D (no torsion signal); used as the
        "did 3D help?" ablation baseline. Negative values are not
        supported.

    Returns
    -------
    List[Storm]
        One :class:`Storm` per surviving track, ordered by year and
        then storm_id (so chronological splits are deterministic).
    """
    if z_scale < 0:
        raise ValueError(f"z_scale must be >= 0; got {z_scale}")

    p = Path(parquet_path)
    if not p.exists():
        raise FileNotFoundError(f"storm tracks file not found: {p}")

    cols = _read_parquet_or_csv(p)

    storm_ids = cols["storm_id"]
    if hasattr(storm_ids, "tolist"):
        ids_list = storm_ids.tolist()
    else:
        ids_list = list(storm_ids)
    unique_ids = sorted(set(ids_list))

    storms: List[Storm] = []
    for sid in unique_ids:
        # Boolean mask for this storm. Vectorized: O(N) per storm,
        # O(N * S) overall where S is storm count. For ~50k fixes /
        # ~1900 storms this is sub-second.
        mask = np.asarray([s == sid for s in ids_list], dtype=bool)
        lats = cols["lat"][mask].astype(np.float64)
        lons = cols["lon"][mask].astype(np.float64)
        wind = cols["max_wind_kt"][mask].astype(np.float64)

        # Filter pre-projection: require enough valid winds for the
        # z-axis to carry signal. Using >= so a storm with exactly
        # min_fixes valid winds passes.
        valid_wind = ~np.isnan(wind)
        if int(valid_wind.sum()) < min_fixes:
            continue

        # Linearly interpolate any NaN winds against fix_idx so the
        # third axis is always defined. Storms that had >= min_fixes
        # valid winds will have at most a handful of leading-NaN
        # rows; np.interp handles that with edge-fill.
        if (~valid_wind).any():
            valid_idx = np.where(valid_wind)[0]
            invalid_idx = np.where(~valid_wind)[0]
            wind[invalid_idx] = np.interp(invalid_idx, valid_idx, wind[valid_idx])

        x_km, y_km = _equirectangular_project(lats, lons)
        z = wind * z_scale  # broadcast scalar; z_scale=0 zeroes the axis.

        points = np.column_stack([x_km, y_km, z]).astype(np.float64)

        # Pull the metadata columns once so the Storm object can be
        # used for downstream joins (e.g. plotting status codes).
        # We keep numpy arrays here rather than lists so memory
        # usage is predictable.
        meta = {
            "datetime_utc": cols["datetime_utc"][mask],
            "lat": lats.copy(),
            "lon": lons.copy(),
            "max_wind_kt": wind.copy(),
            "min_pressure_mb": cols["min_pressure_mb"][mask].astype(np.float64),
            "status": cols["status"][mask],
        }

        # Resolve name and year off the first row of this storm.
        first_idx = int(np.argmax(mask))
        name = str(cols["name"][first_idx])
        year = int(cols["year"][first_idx])

        storms.append(
            Storm(
                storm_id=sid,
                name=name,
                year=year,
                points=points,
                fix_metadata=meta,
            )
        )

    # Stable order: chronological by year, then storm_id. The
    # downstream backtest splits on year, so the deterministic order
    # makes train/test boundaries reproducible across runs.
    storms.sort(key=lambda s: (s.year, s.storm_id))
    return storms


__all__ = ["Storm", "load_storms"]
