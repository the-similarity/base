/**
 * Spatium dataset definitions and pure-function helpers.
 *
 * This module is the deterministic, framework-agnostic data layer for the
 * /spatium page. It contains:
 *   - The 9 cross-domain DATASETS (id, name, domain, color, series kind, era).
 *   - A small mulberry32-seeded PRNG + FNV-1a string hasher so every series,
 *     feature vector, and layout coordinate is reproducible across renders
 *     and across agents.
 *   - Synthetic series generators keyed by `kind` (volatile-momentum,
 *     trending-drift, slow-momentum, regime-switch, long-cycle,
 *     seasonal-spike, burst-decay, seasonal-smooth, bubble-collapse).
 *   - A tiny hand-rolled feature extractor standing in for the real
 *     9-method embedding pipeline (wavelet-leader / DTW / Hurst / spectral).
 *   - A deterministic 3D point layout in feature space — one cluster per
 *     domain, intra-cluster spread driven by slope / hurst / volatility.
 *   - distance()/similarityFromDist() used for nearest-neighbour search
 *     and the cross-domain "rhymes" panel.
 *
 * Invariants:
 *   - All randomness is seeded by `hashStr(id + "/" + i)` so the same
 *     density produces the same points on every mount.
 *   - buildPoints() is PURE: it never mutates DATASETS or global state.
 *   - Feature vector dimensions are stable (8 fields). Downstream code
 *     (distance, colorForPoint) assumes these exact fields.
 *
 * Mutability notes:
 *   - DATASETS and DOMAIN_ORDER are module-scoped and frozen-by-convention;
 *     treat as read-only.
 *   - SpatiumPoint.series is a numeric array; it is not mutated after
 *     construction — consumers must not write into it.
 *
 * Math:
 *   - features(): returns mean, sd, slope (linreg), peak position,
 *     zero-crossings-of-diff, lag-10 autocorrelation, Hurst-ish proxy
 *     (ratio of lag-30 to lag-5 variance), and value range.
 *   - distance(): weighted Euclidean on a 6-dim projection of features.
 *     Weights chosen so `distance ∈ [0, ~3]` typically, mapped to
 *     similarity ∈ [0, 1] via `1 - d/3` clamped.
 */

/* ─── Types ────────────────────────────────────────────────────────── */

export type SeriesKind =
  | "volatile-momentum"
  | "trending-drift"
  | "slow-momentum"
  | "regime-switch"
  | "long-cycle"
  | "seasonal-spike"
  | "burst-decay"
  | "seasonal-smooth"
  | "bubble-collapse";

export interface Dataset {
  id: string;
  name: string;
  domain: string;
  /** 24-bit RGB packed into a number (three.js convention). */
  color: number;
  kind: SeriesKind;
  era: [number, number];
}

export interface FeatureVec {
  mean: number;
  sd: number;
  slope: number;
  /** Peak index divided by series length, in [0, 1]. */
  peak: number;
  /** Zero-crossings of diff divided by N, rough oscillation proxy. */
  zc: number;
  /** Lag-10 autocorrelation (un-normalised). */
  ac: number;
  /** Hurst-ish proxy in [0, 1]. */
  hurst: number;
  range: number;
}

export interface SpatiumPoint {
  id: string;
  /** Dataset id. */
  ds: string;
  dsName: string;
  domain: string;
  color: number;
  year: number;
  series: number[];
  feat: FeatureVec;
  /** Index of the window within its dataset (0-based). */
  idxInDs: number;
  /** World-space 3D coordinates. */
  pos: [number, number, number];
}

/* ─── Constants ───────────────────────────────────────────────────── */

export const DATASETS: readonly Dataset[] = [
  { id: "btc", name: "BTC / USD", domain: "crypto", color: 0x4fa8ff, kind: "volatile-momentum", era: [2017, 2025] },
  { id: "spy", name: "S&P 500", domain: "equity", color: 0x8fc5ff, kind: "trending-drift", era: [1990, 2025] },
  { id: "gold", name: "Gold (XAU)", domain: "commod.", color: 0xe2a846, kind: "slow-momentum", era: [1975, 2025] },
  { id: "oil", name: "Brent crude", domain: "commod.", color: 0xbf7d3a, kind: "regime-switch", era: [1986, 2025] },
  { id: "cpi", name: "US CPI YoY", domain: "macro", color: 0xd47676, kind: "long-cycle", era: [1960, 2025] },
  { id: "flu", name: "Influenza-like\u00b7US", domain: "epi", color: 0x5fb88a, kind: "seasonal-spike", era: [2000, 2025] },
  {
    id: "trends",
    name: "Google Trends \u2018recession\u2019",
    domain: "sentiment",
    color: 0xa886d8,
    kind: "burst-decay",
    era: [2004, 2025],
  },
  { id: "power", name: "Grid demand \u00b7 PJM", domain: "energy", color: 0x80d0c7, kind: "seasonal-smooth", era: [2005, 2025] },
  { id: "tulip", name: "Tulip index \u00b7 1636", domain: "history", color: 0xc48a6a, kind: "bubble-collapse", era: [1634, 1637] },
] as const;

export const DOMAIN_ORDER: readonly string[] = [
  "crypto",
  "equity",
  "commod.",
  "macro",
  "epi",
  "sentiment",
  "energy",
  "history",
];

/* ─── Seeded RNG + hashing ────────────────────────────────────────── */

/**
 * mulberry32 — 32-bit hash-based PRNG.
 *
 * Identical to the design prototype's generator. Yields the same sequence
 * for a given 32-bit seed so layouts/series are reproducible across React
 * strict-mode double mounts and across agents reviewing the diff.
 */
export function mulberry32(seed: number): () => number {
  return function rng() {
    let t = (seed += 0x6d2b79f5);
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/** FNV-1a on a UTF-16 string. Used to derive stable seeds from ids. */
export function hashStr(s: string): number {
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}

export function clamp(x: number, lo: number, hi: number): number {
  return Math.max(lo, Math.min(hi, x));
}

/* ─── Synthetic time-series generators ────────────────────────────── */

/**
 * Generate a 180-sample window keyed by (kind, seed).
 *
 * The series are rough, hand-crafted profiles — stand-ins until the real
 * backend embeddings come online. Each profile encodes a recognisable
 * shape (bubble, seasonal, burst, etc.) so the 3D manifold produces
 * intuitively clustered regions.
 */
export function genSeries(kind: SeriesKind, seed: number): number[] {
  const r = mulberry32(seed);
  const n = 180;
  const a = new Array<number>(n);
  switch (kind) {
    case "volatile-momentum": {
      let v = 0;
      const drift = 0.003 + r() * 0.006;
      for (let i = 0; i < n; i++) {
        v += drift + (r() - 0.5) * 0.045;
        a[i] = v;
      }
      // Occasional sharp correction tail — produces BTC-like profiles.
      if (r() < 0.7) {
        const k = 80 + Math.floor(r() * 80);
        for (let j = k; j < n; j++) a[j] -= (j - k) * 0.02 * (0.6 + r() * 0.8);
      }
      return a;
    }
    case "trending-drift": {
      let v = 0;
      for (let i = 0; i < n; i++) {
        v += 0.0022 + (r() - 0.5) * 0.012;
        a[i] = v;
      }
      return a;
    }
    case "slow-momentum": {
      let v = 0;
      for (let i = 0; i < n; i++) {
        v += 0.0015 + (r() - 0.5) * 0.008;
        a[i] = v;
      }
      return a;
    }
    case "regime-switch": {
      let v = 0;
      let mode = r() < 0.5 ? 1 : -1;
      for (let i = 0; i < n; i++) {
        if (r() < 0.004) mode *= -1;
        v += mode * 0.003 + (r() - 0.5) * 0.02;
        a[i] = v;
      }
      return a;
    }
    case "long-cycle": {
      const freq = 0.015 + r() * 0.01;
      const phase = r() * Math.PI * 2;
      for (let i = 0; i < n; i++) {
        a[i] = Math.sin(i * freq + phase) * 0.5 + (r() - 0.5) * 0.08 + i * 0.001;
      }
      return a;
    }
    case "seasonal-spike": {
      const phase = r() * Math.PI * 2;
      for (let i = 0; i < n; i++) {
        a[i] = Math.max(0, Math.sin(i * 0.035 + phase)) ** 3 + (r() - 0.5) * 0.05;
      }
      return a;
    }
    case "burst-decay": {
      const k = 30 + Math.floor(r() * 50);
      for (let i = 0; i < n; i++) a[i] = (r() - 0.5) * 0.05;
      for (let i = k; i < n; i++) a[i] += Math.exp(-(i - k) * 0.04) * (0.8 + r() * 0.5);
      return a;
    }
    case "seasonal-smooth": {
      const phase = r() * Math.PI * 2;
      for (let i = 0; i < n; i++) {
        a[i] = Math.sin(i * 0.05 + phase) * 0.4 + Math.sin(i * 0.008) * 0.2 + (r() - 0.5) * 0.02;
      }
      return a;
    }
    case "bubble-collapse": {
      const peak = 100 + Math.floor(r() * 40);
      for (let i = 0; i < n; i++) {
        if (i < peak) a[i] = Math.pow(i / peak, 1.5) * (1 + r() * 0.05);
        else a[i] = (1 - (i - peak) / (n - peak)) ** 2.2 * (1 - r() * 0.1);
      }
      return a;
    }
  }
  return a;
}

/* ─── Feature extraction ──────────────────────────────────────────── */

/**
 * Compute an 8-field descriptor for a 1D window.
 *
 * This is intentionally the same stand-in used by the design file so the
 * visual output matches pixel-for-pixel. Swap for the real
 * wavelet-leader / Hurst / DTW / spectral embedding once the backend
 * /embedding endpoint lands.
 */
export function features(s: number[]): FeatureVec {
  const n = s.length;
  let mean = 0;
  let min = Infinity;
  let max = -Infinity;
  for (const x of s) {
    mean += x;
    if (x < min) min = x;
    if (x > max) max = x;
  }
  mean /= n;
  let sd = 0;
  for (const x of s) sd += (x - mean) ** 2;
  sd = Math.sqrt(sd / n);
  // Trend via closed-form simple linear regression against the index.
  let sx = 0;
  let sy = 0;
  let sxy = 0;
  let sxx = 0;
  for (let i = 0; i < n; i++) {
    sx += i;
    sy += s[i];
    sxy += i * s[i];
    sxx += i * i;
  }
  const slope = (n * sxy - sx * sy) / (n * sxx - sx * sx);
  // Peak location (first-argmax).
  let pkIdx = 0;
  for (let i = 0; i < n; i++) {
    if (s[i] === max) {
      pkIdx = i;
      break;
    }
  }
  // Zero-crossings of the first difference — oscillation proxy.
  const diffs: number[] = [];
  for (let i = 1; i < n; i++) diffs.push(s[i] - s[i - 1]);
  let zc = 0;
  for (let i = 1; i < diffs.length; i++) {
    if ((diffs[i - 1] >= 0) !== (diffs[i] >= 0)) zc++;
  }
  // Autocorr at lag 10 (un-normalised on purpose — matches design).
  let ac = 0;
  for (let i = 10; i < n; i++) ac += (s[i] - mean) * (s[i - 10] - mean);
  ac /= n - 10;
  // Hurst-ish proxy: scaling exponent of rolling variance between lag-5
  // and lag-30. Mapped into [0, 1] so the scene legend (anti-persistent
  // / random / trending) makes sense.
  let nearVar = 0;
  let farVar = 0;
  for (let i = 5; i < n; i++) nearVar += (s[i] - s[i - 5]) ** 2;
  for (let i = 30; i < n; i++) farVar += (s[i] - s[i - 30]) ** 2;
  const hurstish = clamp((0.5 * Math.log((farVar + 1e-6) / (nearVar + 1e-6))) / Math.log(30 / 5), 0, 1);
  return { mean, sd, slope, peak: pkIdx / n, zc: zc / n, ac, hurst: hurstish, range: max - min };
}

/* ─── Point layout ────────────────────────────────────────────────── */

/**
 * Build the 3D point cloud for a given density setting.
 *
 * Density → windows per dataset: 0 → 15 (sparse), 1 → 32 (medium),
 * 2 → 60 (dense). Points are deterministically laid out:
 *   1. Each domain sits at a fixed angle on a ring of radius 9.
 *   2. Same-domain datasets get a small per-dataset offset so they
 *      separate visibly.
 *   3. Intra-dataset spread is driven by feature vector components
 *      (slope → x, hurst → y, volatility → z) plus tiny jitter.
 *
 * The result is a stable manifold — same density always produces the
 * same coordinates, which is what makes the scene feel "real".
 */
export function buildPoints(density: 0 | 1 | 2 = 1): SpatiumPoint[] {
  const perDs = [15, 32, 60][density];
  const points: SpatiumPoint[] = [];
  let id = 0;
  for (const ds of DATASETS) {
    const span = Math.max(1, ds.era[1] - ds.era[0]);
    for (let i = 0; i < perDs; i++) {
      const t = i / (perDs - 1);
      const year = Math.round(ds.era[0] + t * span);
      const seed = hashStr(ds.id + "/" + i);
      const series = genSeries(ds.kind, seed);
      const feat = features(series);
      points.push({
        id: "p" + id++,
        ds: ds.id,
        dsName: ds.name,
        domain: ds.domain,
        color: ds.color,
        year,
        series,
        feat,
        idxInDs: i,
        pos: [0, 0, 0], // replaced below
      });
    }
  }

  // Precompute domain ring centres — deterministic, closed-form.
  const domainCenters: Record<string, [number, number, number]> = {};
  DOMAIN_ORDER.forEach((d, i) => {
    const n = DOMAIN_ORDER.length;
    const a = (i / n) * Math.PI * 2;
    const r = 9;
    domainCenters[d] = [Math.cos(a) * r, Math.sin(i * 1.7) * 3.5, Math.sin(a) * r];
  });

  for (const p of points) {
    const ds = DATASETS.find((d) => d.id === p.ds)!;
    const c = domainCenters[ds.domain];
    const offSeed = hashStr(ds.id);
    const off: [number, number, number] = [
      ((offSeed % 97) - 48) / 40,
      (((offSeed >> 8) % 97) - 48) / 40,
      (((offSeed >> 16) % 97) - 48) / 40,
    ];
    const f = p.feat;
    const dx = f.slope * 40 + (f.peak - 0.5) * 3 + (f.zc - 0.1) * 3;
    const dy = (f.hurst - 0.5) * 5 + f.ac * 0.3;
    const dz = f.sd * 6 + (f.range - 0.5) * 1.5;
    const r = mulberry32(hashStr(p.id));
    const j = () => (r() - 0.5) * 0.9;
    p.pos = [c[0] + off[0] + dx + j(), c[1] + off[1] + dy + j(), c[2] + off[2] + dz + j()];
  }
  return points;
}

/* ─── Distance / similarity ───────────────────────────────────────── */

/**
 * Feature-space distance between two points (design-parity).
 *
 * Weights chosen so slope and Hurst dominate — matching the design's
 * intuition that the scene's x/y axes should reflect trend and memory.
 */
export function distance(a: SpatiumPoint, b: SpatiumPoint): number {
  const fa = a.feat;
  const fb = b.feat;
  const df = [
    (fa.slope - fb.slope) * 2,
    fa.peak - fb.peak,
    fa.zc - fb.zc,
    (fa.hurst - fb.hurst) * 1.5,
    (fa.sd - fb.sd) * 0.8,
    (fa.ac - fb.ac) * 0.02,
  ];
  let s = 0;
  for (const x of df) s += x * x;
  return Math.sqrt(s);
}

/** Map feature-space distance ∈ [0, 3] → similarity ∈ [0, 1]. */
export function similarityFromDist(d: number): number {
  return clamp(1 - d / 3, 0, 1);
}

/** Human-readable regime label for a feature vector. */
export function regimeLabel(f: FeatureVec): string {
  if (f.hurst > 0.58) return "Trending";
  if (f.hurst < 0.42) return "Mean-rev";
  return "Random";
}
