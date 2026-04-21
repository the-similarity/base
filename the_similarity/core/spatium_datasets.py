"""
Python mirror of ``the-similarity-app/app/spatium/datasets.ts``.

Why this module exists
----------------------
The Spatium 3D dashboard synthesises its demo point cloud client-side
in TypeScript so the page renders without a backend round-trip. That
generator (9 dataset recipes × a seeded mulberry32 PRNG × an 8-field
feature extractor) is the source of truth for the *shape* of the demo
manifold, but the algorithm itself is deterministic and framework
agnostic — it therefore belongs in the Python side too, for three
reasons:

1. **Backend fixtures.** Python tests (and notebooks) need a stable,
   reproducible Spatium-style point cloud without spawning a
   headless browser. This module produces JSON that the TS side and
   the Python side agree on byte-for-byte.
2. **Cross-language parity.** Drift between the two implementations
   would silently corrupt offline evaluations. A single canonical
   fixture (``the_similarity/tests/fixtures/spatium/points_d0.json``)
   is produced here and asserted against by both the Python test
   suite and the vitest test suite.
3. **Offline data generation.** Downstream platforms (the registry,
   the synthetic data pipeline) can ingest Spatium-flavoured points
   as a quick synthetic regression target — see
   ``the_similarity.synthetic`` for the full production pipeline.

Lifecycle / immutability
------------------------
* Pure module — no global state, no I/O except the optional
  ``write_fixture()`` helper.
* ``mulberry32`` and ``hash_str`` implement the exact JS semantics
  (``uint32`` wrap-around, ``Math.imul`` low-32-bit multiply); any
  change here must be mirrored in ``datasets.ts`` and vice versa.
* All ``Dataset`` and ``FeatureVec`` instances are ``frozen=True``
  dataclasses — callers cannot accidentally mutate them after
  ``build_points`` returns.

Mathematical notes
------------------
* The feature-space embedding is an 8-field descriptor (mean, sd,
  slope via closed-form linear regression, peak index, zero-crossings
  of the first difference, lag-10 autocovariance, a Hurst proxy from
  rolling-variance scaling between lag-5 and lag-30, value range).
* The 3D layout places each domain on a ring at radius 9, derives a
  per-dataset offset from ``FNV-1a(dataset.id)``, then spreads points
  inside the cluster via ``(slope, hurst, sd)`` — the same geometry
  the TS implementation uses.

See Also
--------
the-similarity-app/app/spatium/datasets.ts
    Canonical TypeScript implementation — keep in lock-step.
the_similarity/tests/test_spatium_datasets.py
    Python-side parity + determinism tests.
"""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable, Iterable, List, Sequence, Tuple

# ────────────────────────────────────────────────────────────────────
# Constants — must match datasets.ts line-for-line.
# ────────────────────────────────────────────────────────────────────

#: Mask that clamps a Python integer to a JS ``uint32``. Used everywhere
#: the algorithm depends on 32-bit wrap-around semantics.
U32_MASK = 0xFFFFFFFF

#: Series kinds produced by ``gen_series`` — the order matches the TS
#: ``SERIES_KINDS`` constant (used by the Add-dataset popover dropdown).
SERIES_KINDS: Tuple[str, ...] = (
    "volatile-momentum",
    "trending-drift",
    "slow-momentum",
    "regime-switch",
    "long-cycle",
    "seasonal-spike",
    "burst-decay",
    "seasonal-smooth",
    "bubble-collapse",
)

#: Canonical domain ring order — determines the angular slot for each
#: built-in dataset. Keep in sync with ``DOMAIN_ORDER`` in datasets.ts.
DOMAIN_ORDER: Tuple[str, ...] = (
    "crypto",
    "equity",
    "commod.",
    "macro",
    "epi",
    "sentiment",
    "energy",
    "history",
)


@dataclass(frozen=True)
class Dataset:
    """One dataset recipe. Mirror of the TS ``Dataset`` interface.

    ``color`` is a 24-bit packed RGB (Three.js convention). ``era`` is a
    ``(start_year, end_year)`` inclusive pair used to map window index
    to a synthetic sampling year.
    """

    id: str
    name: str
    domain: str
    color: int
    kind: str
    era: Tuple[int, int]


@dataclass(frozen=True)
class FeatureVec:
    """8-field descriptor. Field semantics match TS verbatim."""

    mean: float
    sd: float
    slope: float
    peak: float  # peak index / N  — ∈ [0, 1]
    zc: float  # zero-crossings of diff / N
    ac: float  # lag-10 autocovariance (un-normalised, on purpose)
    hurst: float  # [0, 1] clamp of lag-30/lag-5 variance ratio
    range: float


@dataclass
class SpatiumPoint:
    """A point in the demo manifold — mirrors the TS shape exactly.

    We intentionally leave ``series`` mutable-looking for cheap
    construction, but callers must treat it as read-only (the
    fixture writer and the parity tests do).
    """

    id: str
    ds: str
    ds_name: str
    domain: str
    color: int
    year: int
    series: List[float]
    feat: FeatureVec
    idx_in_ds: int
    pos: Tuple[float, float, float]


#: The 9 built-in datasets. Colours and eras are byte-for-byte identical
#: to the TS ``DATASETS`` constant so the Python-produced fixture and
#: the TS-produced fixture agree.
DATASETS: Tuple[Dataset, ...] = (
    Dataset("btc", "BTC / USD", "crypto", 0x4FA8FF, "volatile-momentum", (2017, 2025)),
    Dataset("spy", "S&P 500", "equity", 0x8FC5FF, "trending-drift", (1990, 2025)),
    Dataset("gold", "Gold (XAU)", "commod.", 0xE2A846, "slow-momentum", (1975, 2025)),
    Dataset("oil", "Brent crude", "commod.", 0xBF7D3A, "regime-switch", (1986, 2025)),
    Dataset("cpi", "US CPI YoY", "macro", 0xD47676, "long-cycle", (1960, 2025)),
    Dataset("flu", "Influenza-like·US", "epi", 0x5FB88A, "seasonal-spike", (2000, 2025)),
    Dataset(
        "trends",
        "Google Trends ‘recession’",
        "sentiment",
        0xA886D8,
        "burst-decay",
        (2004, 2025),
    ),
    Dataset("power", "Grid demand · PJM", "energy", 0x80D0C7, "seasonal-smooth", (2005, 2025)),
    Dataset("tulip", "Tulip index · 1636", "history", 0xC48A6A, "bubble-collapse", (1634, 1637)),
)


# ────────────────────────────────────────────────────────────────────
# PRNG + string hashing (must be bit-exact with the JS side).
# ────────────────────────────────────────────────────────────────────


def _imul(a: int, b: int) -> int:
    """Return the low 32 bits of ``a * b`` — mirror of ``Math.imul``.

    We only consume the bit pattern via subsequent xor/shift ops, so a
    plain low-32 multiply is indistinguishable from JS's signed-result
    imul for our purposes.
    """
    return (a * b) & U32_MASK


def mulberry32(seed: int) -> Callable[[], float]:
    """Seed a mulberry32 PRNG and return a 0-arg sampler.

    Byte-for-byte mirror of the ``mulberry32`` helper in datasets.ts.
    The returned closure advances internal state on each call and
    yields a float in ``[0, 1)`` — the same sequence the TS side
    produces for an identical seed.
    """
    state = seed & U32_MASK

    def rng() -> float:
        nonlocal state
        # ``seed += 0x6d2b79f5`` — wrap at uint32.
        state = (state + 0x6D2B79F5) & U32_MASK
        t = state
        # ``Math.imul(t ^ (t >>> 15), t | 1)``
        t = _imul(t ^ (t >> 15), t | 1)
        # ``t ^= t + Math.imul(t ^ (t >>> 7), t | 61)``
        t = (t ^ ((t + _imul(t ^ (t >> 7), t | 61)) & U32_MASK)) & U32_MASK
        # ``((t ^ (t >>> 14)) >>> 0) / 4294967296``
        return ((t ^ (t >> 14)) & U32_MASK) / 4294967296.0

    return rng


def _to_int32(u: int) -> int:
    """Reinterpret a ``uint32`` as a signed ``int32``.

    JavaScript's arithmetic operators (``>>``, unary ``-``, ``|``) treat
    bit patterns as signed 32-bit; Python's ``int`` is arbitrary
    precision and always treats values as their numeric magnitude. To
    reproduce the JS behaviour for shifts/modulo we have to flip the
    high bit into a negative number first.
    """
    u &= U32_MASK
    return u - 0x1_0000_0000 if u & 0x8000_0000 else u


def _js_shr_signed(u: int, n: int) -> int:
    """Mirror of JS ``>>`` (signed arithmetic shift right on int32).

    For values with the high bit set, sign-extends during the shift so
    the result can be negative — unlike Python's ``>>`` on unsigned
    ints which always yields a non-negative result.
    """
    return _to_int32(u) >> n


def _js_mod(a: int, b: int) -> int:
    """Mirror of JS ``%`` — remainder takes the sign of the dividend.

    Python's ``%`` returns a remainder with the sign of the divisor
    (so ``-5 % 3 == 1``); JS returns with the sign of the dividend
    (``-5 % 3 === -2``). Match JS so fixtures line up byte-for-byte.
    """
    r = abs(a) % b
    return -r if a < 0 else r


def hash_str(s: str) -> int:
    """FNV-1a over the UTF-16 code units of ``s`` — mirror of JS hash.

    JavaScript strings are UTF-16; Python strings iterate code points.
    For ASCII / BMP the two coincide, which is all the dataset ids and
    domain names ever use. If we ever feed a surrogate-pair character
    into the hasher the result would diverge — keep ids ASCII-only.
    """
    h = 2166136261
    for ch in s:
        h ^= ord(ch)
        h = _imul(h, 16777619)
    return h & U32_MASK


def clamp(x: float, lo: float, hi: float) -> float:
    """Numeric clamp. Behaves like ``max(lo, min(hi, x))``."""
    if x < lo:
        return lo
    if x > hi:
        return hi
    return x


# ────────────────────────────────────────────────────────────────────
# Series generators. Every branch mirrors the TS ``genSeries`` switch.
# ────────────────────────────────────────────────────────────────────


def gen_series(kind: str, seed: int) -> List[float]:
    """Return a 180-sample synthetic series of shape ``kind``.

    Each branch consumes the RNG in exactly the same order as the TS
    switch so two runs of ``mulberry32(seed)`` agree on call count
    (and therefore on each emitted value).
    """
    r = mulberry32(seed)
    n = 180
    a = [0.0] * n

    if kind == "volatile-momentum":
        v = 0.0
        drift = 0.003 + r() * 0.006
        for i in range(n):
            v += drift + (r() - 0.5) * 0.045
            a[i] = v
        if r() < 0.7:
            # ``Math.floor(r() * 80)`` — r() ∈ [0, 1), so ``int`` truncation matches.
            k = 80 + int(r() * 80)
            for j in range(k, n):
                a[j] -= (j - k) * 0.02 * (0.6 + r() * 0.8)
        return a

    if kind == "trending-drift":
        v = 0.0
        for i in range(n):
            v += 0.0022 + (r() - 0.5) * 0.012
            a[i] = v
        return a

    if kind == "slow-momentum":
        v = 0.0
        for i in range(n):
            v += 0.0015 + (r() - 0.5) * 0.008
            a[i] = v
        return a

    if kind == "regime-switch":
        v = 0.0
        mode = 1 if r() < 0.5 else -1
        for i in range(n):
            if r() < 0.004:
                mode *= -1
            v += mode * 0.003 + (r() - 0.5) * 0.02
            a[i] = v
        return a

    if kind == "long-cycle":
        freq = 0.015 + r() * 0.01
        phase = r() * math.pi * 2
        for i in range(n):
            a[i] = math.sin(i * freq + phase) * 0.5 + (r() - 0.5) * 0.08 + i * 0.001
        return a

    if kind == "seasonal-spike":
        phase = r() * math.pi * 2
        for i in range(n):
            a[i] = max(0.0, math.sin(i * 0.035 + phase)) ** 3 + (r() - 0.5) * 0.05
        return a

    if kind == "burst-decay":
        k = 30 + int(r() * 50)
        for i in range(n):
            a[i] = (r() - 0.5) * 0.05
        for i in range(k, n):
            a[i] += math.exp(-(i - k) * 0.04) * (0.8 + r() * 0.5)
        return a

    if kind == "seasonal-smooth":
        phase = r() * math.pi * 2
        for i in range(n):
            a[i] = (
                math.sin(i * 0.05 + phase) * 0.4
                + math.sin(i * 0.008) * 0.2
                + (r() - 0.5) * 0.02
            )
        return a

    if kind == "bubble-collapse":
        peak = 100 + int(r() * 40)
        for i in range(n):
            if i < peak:
                a[i] = ((i / peak) ** 1.5) * (1 + r() * 0.05)
            else:
                a[i] = ((1 - (i - peak) / (n - peak)) ** 2.2) * (1 - r() * 0.1)
        return a

    raise ValueError(f"unknown series kind: {kind}")


# ────────────────────────────────────────────────────────────────────
# Feature extractor — 8-field descriptor exactly like datasets.ts.
# ────────────────────────────────────────────────────────────────────


def features(series: Sequence[float]) -> FeatureVec:
    """Compute the 8-field descriptor for one window.

    Uses closed-form formulas identical to the TS side (slope via
    ``(n·Σxy − Σx·Σy) / (n·Σx² − Σx²)``, Hurst via log-ratio of lag-30
    to lag-5 rolling variance). Any cosmetic rewrite that changes the
    floating-point order of operations will diverge from the fixture
    and break the parity test — don't refactor without updating the
    golden JSON.
    """
    n = len(series)
    mean = sum(series) / n
    mn = min(series)
    mx = max(series)

    # Variance via two-pass; matches TS (which also uses two-pass).
    sd_sum = 0.0
    for x in series:
        sd_sum += (x - mean) ** 2
    sd = math.sqrt(sd_sum / n)

    # Closed-form linear regression slope.
    sx = 0.0
    sy = 0.0
    sxy = 0.0
    sxx = 0.0
    for i in range(n):
        sx += i
        sy += series[i]
        sxy += i * series[i]
        sxx += i * i
    slope = (n * sxy - sx * sy) / (n * sxx - sx * sx)

    # First-argmax peak index (TS uses strict `===` comparison against max).
    pk_idx = 0
    for i in range(n):
        if series[i] == mx:
            pk_idx = i
            break

    # Zero-crossings of the first difference.
    diffs = [series[i] - series[i - 1] for i in range(1, n)]
    zc = 0
    for i in range(1, len(diffs)):
        if (diffs[i - 1] >= 0) != (diffs[i] >= 0):
            zc += 1

    # Lag-10 autocovariance (not normalised — TS keeps raw magnitude).
    ac = 0.0
    for i in range(10, n):
        ac += (series[i] - mean) * (series[i - 10] - mean)
    ac /= n - 10

    # Hurst-ish proxy.
    near_var = 0.0
    far_var = 0.0
    for i in range(5, n):
        near_var += (series[i] - series[i - 5]) ** 2
    for i in range(30, n):
        far_var += (series[i] - series[i - 30]) ** 2
    hurstish = clamp(
        (0.5 * math.log((far_var + 1e-6) / (near_var + 1e-6))) / math.log(30 / 5),
        0.0,
        1.0,
    )
    return FeatureVec(
        mean=mean,
        sd=sd,
        slope=slope,
        peak=pk_idx / n,
        zc=zc / n,
        ac=ac,
        hurst=hurstish,
        range=mx - mn,
    )


# ────────────────────────────────────────────────────────────────────
# 3D layout — one cluster per domain, feature-driven intra spread.
# ────────────────────────────────────────────────────────────────────


@dataclass
class BuildResult:
    """Return shape of ``build_points`` — deliberately flat for JSON."""

    points: List[SpatiumPoint] = field(default_factory=list)
    datasets: List[Dataset] = field(default_factory=list)


def _density_count(density: int) -> int:
    """Map density 0/1/2 → 15/32/60 (matches TS ``buildPoints``)."""
    return (15, 32, 60)[density]


def _domain_center(domain: str, canonical_index: int | None) -> Tuple[float, float, float]:
    """Return the ring-centre coordinate for ``domain``.

    * Canonical domains (those in ``DOMAIN_ORDER``) use their fixed
      angular slot so the visual layout is identical across runs.
    * Unknown domains (user-added datasets) derive a deterministic slot
      from ``FNV-1a("domain:" + domain)`` — any two sessions agree on
      where a given domain lands even if datasets were added in
      different orders.
    """
    if canonical_index is not None:
        n = len(DOMAIN_ORDER)
        a = (canonical_index / n) * math.pi * 2
        r = 9.0
        return (math.cos(a) * r, math.sin(canonical_index * 1.7) * 3.5, math.sin(a) * r)
    dh = hash_str("domain:" + domain)
    # Matches TS: ``(dh % 1000)`` — uint32 mod is unambiguous. But
    # ``(dh >> 10)`` in JS is a signed shift that can go negative when
    # the uint32 has its high bit set; replicate via _js_shr_signed +
    # _js_mod so the sign flows through identically.
    a = (_js_mod(dh, 1000) / 1000.0) * math.pi * 2
    r = 9.0
    y = math.sin(_js_mod(_js_shr_signed(dh, 10), 1000) / 1000.0 * math.pi * 2) * 3.5
    return (math.cos(a) * r, y, math.sin(a) * r)


def build_points(
    density: int = 1,
    extras: Sequence[Dataset] | None = None,
) -> BuildResult:
    """Build the deterministic Spatium point cloud.

    Mirrors the TS ``buildPoints`` contract: same density → same points
    → same layout. ``extras`` is the Python equivalent of the ``extras``
    parameter on the TS function — user-added datasets get appended
    after the built-ins and their points come last in the output list.

    The output is stable across Python versions so long as the
    ``math`` module's double-precision transcendentals agree
    (``sin``/``cos``/``log`` all use the platform libm, which is IEEE
    754 on every target we ship on).
    """
    if density not in (0, 1, 2):
        raise ValueError(f"density must be 0/1/2, got {density}")
    per_ds = _density_count(density)
    all_datasets: List[Dataset] = list(DATASETS)
    if extras:
        all_datasets.extend(extras)

    canonical = {d: i for i, d in enumerate(DOMAIN_ORDER)}

    points: List[SpatiumPoint] = []
    next_id = 0
    for ds in all_datasets:
        span = max(1, ds.era[1] - ds.era[0])
        for i in range(per_ds):
            # TS: ``const t = i / (perDs - 1)`` — division by zero cannot
            # occur because per_ds is always ≥ 15.
            t = i / (per_ds - 1)
            # ``Math.round`` in JavaScript rounds half toward +∞ (so
            # ``round(2.5) == 3``) whereas Python's builtin ``round``
            # uses banker's rounding (``round(2.5) == 2``). Years land
            # on exact halves for several (span, t) combos — use
            # ``floor(x + 0.5)`` to match JS semantics and keep the
            # cross-language fixture byte-for-byte identical.
            year = math.floor(ds.era[0] + t * span + 0.5)
            seed = hash_str(ds.id + "/" + str(i))
            series = gen_series(ds.kind, seed)
            feat = features(series)
            points.append(
                SpatiumPoint(
                    id=f"p{next_id}",
                    ds=ds.id,
                    ds_name=ds.name,
                    domain=ds.domain,
                    color=ds.color,
                    year=year,
                    series=series,
                    feat=feat,
                    idx_in_ds=i,
                    pos=(0.0, 0.0, 0.0),
                )
            )
            next_id += 1

    # Cache the ring-centre for each unique domain we see (canonical or not).
    centers: dict[str, Tuple[float, float, float]] = {}

    for p in points:
        ds = next(d for d in all_datasets if d.id == p.ds)
        if ds.domain not in centers:
            centers[ds.domain] = _domain_center(ds.domain, canonical.get(ds.domain))
        c = centers[ds.domain]
        off_seed = hash_str(ds.id)
        # Use JS-semantics shift/mod so signed-shift + mod-of-negative
        # produce the exact offsets the TS generator produces. See
        # _js_shr_signed / _js_mod for why Python's native operators
        # don't suffice for ``uint32`` values above 0x8000_0000.
        off = (
            (_js_mod(off_seed, 97) - 48) / 40.0,
            (_js_mod(_js_shr_signed(off_seed, 8), 97) - 48) / 40.0,
            (_js_mod(_js_shr_signed(off_seed, 16), 97) - 48) / 40.0,
        )
        f = p.feat
        dx = f.slope * 40 + (f.peak - 0.5) * 3 + (f.zc - 0.1) * 3
        dy = (f.hurst - 0.5) * 5 + f.ac * 0.3
        dz = f.sd * 6 + (f.range - 0.5) * 1.5
        r = mulberry32(hash_str(p.id))
        j = lambda: (r() - 0.5) * 0.9  # noqa: E731 — match TS lambda-as-local
        p.pos = (
            c[0] + off[0] + dx + j(),
            c[1] + off[1] + dy + j(),
            c[2] + off[2] + dz + j(),
        )

    return BuildResult(points=points, datasets=all_datasets)


# ────────────────────────────────────────────────────────────────────
# Distance / similarity — same weights as the TS side.
# ────────────────────────────────────────────────────────────────────


def distance(a: SpatiumPoint, b: SpatiumPoint) -> float:
    """Weighted Euclidean distance in feature space. Matches TS."""
    fa, fb = a.feat, b.feat
    dfs = (
        (fa.slope - fb.slope) * 2,
        fa.peak - fb.peak,
        fa.zc - fb.zc,
        (fa.hurst - fb.hurst) * 1.5,
        (fa.sd - fb.sd) * 0.8,
        (fa.ac - fb.ac) * 0.02,
    )
    return math.sqrt(sum(x * x for x in dfs))


def similarity_from_dist(d: float) -> float:
    """Map feature-space distance → ``[0, 1]`` similarity. Matches TS."""
    return clamp(1 - d / 3, 0.0, 1.0)


def regime_label(f: FeatureVec) -> str:
    """Bucket a feature vector into Trending / Mean-rev / Random."""
    if f.hurst > 0.58:
        return "Trending"
    if f.hurst < 0.42:
        return "Mean-rev"
    return "Random"


# ────────────────────────────────────────────────────────────────────
# Fixture I/O — used by the test suite and CLI.
# ────────────────────────────────────────────────────────────────────


def to_export_dict(result: BuildResult, *, include_series: bool = False) -> dict:
    """Serialise ``build_points`` output into a JSON-friendly dict.

    The shape mirrors the TS ``ExportedEmbedding`` contract so the same
    fixture JSON can round-trip between the two language runtimes. We
    omit the raw ``series`` by default to keep fixture blobs small —
    they are deterministically recoverable from ``(kind, idxInDs)`` via
    ``gen_series``.
    """
    return {
        "schemaVersion": 1,
        "datasets": [
            {
                "id": d.id,
                "name": d.name,
                "domain": d.domain,
                "color": d.color,
                "kind": d.kind,
                "era": list(d.era),
            }
            for d in result.datasets
        ],
        "points": [
            {
                "id": p.id,
                "ds": p.ds,
                "domain": p.domain,
                "year": p.year,
                "idxInDs": p.idx_in_ds,
                "pos": list(p.pos),
                "feat": asdict(p.feat),
                **({"series": p.series} if include_series else {}),
            }
            for p in result.points
        ],
    }


def write_fixture(path: Path, density: int = 0, *, include_series: bool = False) -> Path:
    """Write a canonical fixture JSON to ``path`` and return the path.

    Used by the CLI (``python -m the_similarity.core.spatium_datasets``)
    and by the regenerate-fixtures helper in the test suite. Emits
    sorted keys + trailing newline so diffs are reviewable.
    """
    payload = to_export_dict(build_points(density), include_series=include_series)
    path.parent.mkdir(parents=True, exist_ok=True)
    # ``sort_keys=True`` stabilises field order across Python versions;
    # ``indent=2`` matches the TS exporter.
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _cli(argv: Iterable[str] | None = None) -> int:
    """Tiny CLI: ``python -m the_similarity.core.spatium_datasets --out FILE --density N``.

    Kept minimal on purpose — it only exists so a developer can
    regenerate the golden fixture without touching tests.
    """
    import argparse

    parser = argparse.ArgumentParser(description="Emit Spatium point cloud fixture JSON.")
    parser.add_argument("--density", type=int, default=0, choices=(0, 1, 2))
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--series", action="store_true", help="include raw series in output")
    args = parser.parse_args(list(argv) if argv is not None else None)
    write_fixture(args.out, density=args.density, include_series=args.series)
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":  # pragma: no cover — CLI entrypoint
    raise SystemExit(_cli())
