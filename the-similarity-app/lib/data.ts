/**
 * Synthetic finance data + match engine + 9-lens scoring + forecast cone.
 *
 * Ported from the HTML prototype's data.jsx. Generates ~30 years of synthetic
 * "SPX-like" daily closes with regime changes, then provides a 9-lens scoring
 * engine (9 lenses: Shape, Dynamics, Scaling, Rhythm, Engine, Decomposition,
 * Topology, Carry, Consensus) plus analog finding and forecast cone construction.
 *
 * Uses a seeded PRNG for deterministic output — no randomness at runtime.
 */

// ── Seeded PRNG ─────────────────────────────────────────────────────────
// Linear congruential generator with seed 1337. Must produce identical
// output across every page load so the workstation is visually stable.
const makeRand = () => {
  let s = 1337;
  return () => {
    s = (s * 1664525 + 1013904223) >>> 0;
    return s / 0xffffffff;
  };
};

const rand = makeRand();

// ── Data point type ─────────────────────────────────────────────────────
export interface DataPoint {
  /** Unix timestamp in ms */
  t: number;
  /** Date object */
  d: Date;
  /** Price */
  p: number;
  /** Log return (0 for first element) */
  r: number;
}

/** 9-lens score bundle for a single analog match.
 * Keys are opaque lens identifiers (lens1..lens9) to protect the engine's
 * internal method names from being exposed in the UI or network traffic.
 */
export interface LensScores {
  lens1: number;  // Shape (structural alignment)
  lens2: number;  // Dynamics (temporal co-movement)
  lens3: number;  // Scaling (power-law structure)
  lens4: number;  // Rhythm (multiscale texture)
  lens5: number;  // Engine (dynamical signature)
  lens6: number;  // Decomposition (trend & residual)
  lens7: number;  // Topology (geometric persistence)
  lens8: number;  // Carry (predictive transfer)
  lens9: number;  // Consensus (cross-lens agreement)
}

/** A single analog match result */
export interface AnalogMatch {
  id: string;
  rank: number;
  startIdx: number;
  date: Date;
  endDate: Date;
  label: string;
  composite: number;
  lenses: LensScores;
  priceWindow: number[];
  after: number[];
  afterReturn: number;
  note: string;
}

/** Forecast cone quantile at a single time step */
export interface ConePoint {
  t: number;
  p10: number;
  p25: number;
  p50: number;
  p75: number;
  p90: number;
}

// ── Series generation ───────────────────────────────────────────────────
// Builds ~30 years of synthetic "SPX-like" daily closes with regimes.
// Regimes inject drift/vol shifts matching real historical episodes
// (dotcom, GFC, covid, 2022 rate hike).
function buildSeries(n = 7500): DataPoint[] {
  const out: DataPoint[] = [];
  let price = 320;
  const start = new Date(1995, 0, 3).getTime();
  const day = 86400000;

  // Regime table: each entry changes drift+vol from its start index onward
  const regimes = [
    { start: 0, drift: 0.00055, vol: 0.009 },
    { start: 900, drift: -0.0003, vol: 0.021 },   // dotcom crash
    { start: 1800, drift: 0.00045, vol: 0.010 },
    { start: 3100, drift: -0.0008, vol: 0.028 },   // GFC
    { start: 3600, drift: 0.00060, vol: 0.011 },
    { start: 5700, drift: -0.0015, vol: 0.045 },   // covid crash
    { start: 5800, drift: 0.00085, vol: 0.017 },   // recovery
    { start: 6600, drift: -0.0004, vol: 0.020 },   // 2022 drawdown
    { start: 7000, drift: 0.00055, vol: 0.012 },
  ];

  for (let i = 0; i < n; i++) {
    // Find active regime (last one whose start <= i)
    let reg = regimes[0];
    for (let r = regimes.length - 1; r >= 0; r--) {
      if (i >= regimes[r].start) { reg = regimes[r]; break; }
    }
    const drift = reg.drift;
    const vol = reg.vol;
    // Box-Muller-ish: sum of 3 uniform => approximate normal
    const shock = (rand() + rand() + rand() - 1.5) * 2 * vol;
    price = price * (1 + drift + shock);
    // Prevent price collapse below floor
    if (price < 50) price = 50 * (1 + Math.abs(shock));
    out.push({
      t: start + i * day,
      d: new Date(start + i * day),
      p: price,
      r: 0, // filled below
    });
  }

  // Compute log returns
  out.forEach((pt, i) => {
    pt.r = i > 0 ? Math.log(pt.p / out[i - 1].p) : 0;
  });

  return out;
}

/** The full synthetic series — computed once, stable across renders */
export const SERIES = buildSeries();

// ── Statistical helpers ─────────────────────────────────────────────────
function zscore(arr: number[]): number[] {
  const m = arr.reduce((a, b) => a + b, 0) / arr.length;
  const v = arr.reduce((a, b) => a + (b - m) * (b - m), 0) / arr.length;
  const s = Math.sqrt(v) || 1;
  return arr.map(x => (x - m) / s);
}

function corr(a: number[], b: number[]): number {
  const za = zscore(a), zb = zscore(b);
  let s = 0;
  for (let i = 0; i < za.length; i++) s += za[i] * zb[i];
  return s / za.length;
}

// Lightweight DTW on z-scored windows with Sakoe-Chiba band=8
function dtw(a: number[], b: number[]): number {
  const za = zscore(a), zb = zscore(b);
  const n = za.length, m = zb.length;
  const band = 8;
  const INF = 1e9;
  let prev = new Array(m + 1).fill(INF);
  prev[0] = 0;
  for (let i = 1; i <= n; i++) {
    const cur = new Array(m + 1).fill(INF);
    const jmin = Math.max(1, i - band), jmax = Math.min(m, i + band);
    for (let j = jmin; j <= jmax; j++) {
      const c = Math.abs(za[i - 1] - zb[j - 1]);
      cur[j] = c + Math.min(prev[j], cur[j - 1], prev[j - 1]);
    }
    prev = cur;
  }
  return prev[m] / (n + m);
}

// Hurst exponent via rescaled range (R/S analysis)
function hurst(arr: number[]): number {
  const N = arr.length;
  const cuts = [8, 16, 32, 64].filter(c => c <= N);
  const xs: number[] = [], ys: number[] = [];
  for (const c of cuts) {
    const segs = Math.floor(N / c);
    let rs = 0;
    for (let s = 0; s < segs; s++) {
      const seg = arr.slice(s * c, (s + 1) * c);
      const mean = seg.reduce((a, b) => a + b, 0) / c;
      let cumMin = 0, cumMax = 0, cum = 0;
      for (const v of seg) {
        cum += v - mean;
        if (cum < cumMin) cumMin = cum;
        if (cum > cumMax) cumMax = cum;
      }
      const r = cumMax - cumMin;
      const std = Math.sqrt(seg.reduce((a, b) => a + (b - mean) ** 2, 0) / c) || 1e-9;
      rs += r / std;
    }
    rs /= segs;
    xs.push(Math.log(c));
    ys.push(Math.log(rs + 1e-9));
  }
  // Linear fit slope = Hurst exponent estimate
  const n = xs.length;
  const mx = xs.reduce((a, b) => a + b, 0) / n;
  const my = ys.reduce((a, b) => a + b, 0) / n;
  let num = 0, den = 0;
  for (let i = 0; i < n; i++) { num += (xs[i] - mx) * (ys[i] - my); den += (xs[i] - mx) ** 2; }
  return den ? num / den : 0.5;
}

function clip01(x: number): number { return Math.max(0, Math.min(1, x)); }

function rollStd(a: number[], w: number): number[] {
  const out: number[] = [];
  for (let i = 0; i + w <= a.length; i++) {
    const s = a.slice(i, i + w);
    const m = s.reduce((x, y) => x + y, 0) / w;
    const v = s.reduce((x, y) => x + (y - m) ** 2, 0) / w;
    out.push(Math.sqrt(v));
  }
  return out;
}

function ema(a: number[], w: number): number[] {
  const k = 2 / (w + 1);
  const out = [a[0]];
  for (let i = 1; i < a.length; i++) out.push(a[i] * k + out[i - 1] * (1 - k));
  return out;
}

function ar1(a: number[]): number {
  let num = 0, den = 0;
  for (let i = 1; i < a.length; i++) { num += a[i] * a[i - 1]; den += a[i - 1] * a[i - 1]; }
  return den ? num / den : 0;
}

function turningStats(a: number[]): { count: number; spread: number } {
  let count = 0;
  const tps: number[] = [];
  for (let i = 1; i < a.length - 1; i++) {
    if ((a[i] > a[i - 1] && a[i] > a[i + 1]) || (a[i] < a[i - 1] && a[i] < a[i + 1])) {
      count++;
      tps.push(a[i]);
    }
  }
  const mean = tps.reduce((x, y) => x + y, 0) / (tps.length || 1);
  const spread = Math.sqrt(tps.reduce((x, y) => x + (y - mean) ** 2, 0) / (tps.length || 1));
  return { count, spread };
}

function laggedCorr(a: number[], b: number[], k: number): number {
  if (a.length !== b.length) return 0;
  const x = a.slice(0, a.length - k);
  const y = b.slice(k);
  return corr(x, y);
}

// ── 9-Lens scoring engine ───────────────────────────────────────────────
/**
 * Score a query window against a candidate match window using all 9 lenses.
 * Returns per-lens scores (0..1) and a composite mean.
 */
export function scoreMatch(qp: number[], mp: number[]): { lenses: LensScores; composite: number } {
  // Price arrays normalized to start=1
  const qn = qp.map(x => x / qp[0]);
  const mn = mp.map(x => x / mp[0]);
  const qr = qp.slice(1).map((x, i) => Math.log(x / qp[i]));
  const mr = mp.slice(1).map((x, i) => Math.log(x / mp[i]));

  const pearson = Math.max(0, corr(qn, mn));
  const dtwDist = dtw(qn, mn);
  const dtwScore = Math.max(0, 1 - dtwDist * 2.5);
  const hQ = hurst(qr), hM = hurst(mr);
  const bempedelis = Math.max(0, 1 - Math.abs(hQ - hM) * 2.5);

  // Wavelet leaders proxy: vol-of-vol similarity across 4 scales
  const scales = [4, 8, 16, 32];
  let wlSum = 0;
  for (const s of scales) {
    const qv = rollStd(qr, s);
    const mv = rollStd(mr, s);
    const lenW = Math.min(qv.length, mv.length);
    if (lenW < 4) continue;
    wlSum += Math.max(0, corr(qv.slice(0, lenW), mv.slice(0, lenW)));
  }
  const wavelet = Math.max(0, wlSum / scales.length);

  // Koopman proxy: AR(1) coefficient similarity
  const arQ = ar1(qr), arM = ar1(mr);
  const koopman = Math.max(0, 1 - Math.abs(arQ - arM) * 2.5);

  // EMD proxy: trend (EMA-20) + residual similarity
  const tQ = ema(qn, 20), tM = ema(mn, 20);
  const rQ = qn.map((v, i) => v - tQ[i]);
  const rM = mn.map((v, i) => v - tM[i]);
  const emdScore = Math.max(0, corr(tQ, tM)) * 0.6 + Math.max(0, corr(rQ, rM)) * 0.4;

  // TDA persistence proxy: turning point count + spread
  const tpQ = turningStats(qn), tpM = turningStats(mn);
  const tda = Math.max(0, 1 - Math.abs(tpQ.count - tpM.count) / 15
    - Math.abs(tpQ.spread - tpM.spread) * 0.5);

  // Transfer entropy proxy: lagged correlation
  const lag = laggedCorr(mr, qr, 3);
  const te = Math.max(0, Math.abs(lag));

  const lenses: LensScores = {
    lens1: dtwScore,        // Shape
    lens2: pearson,         // Dynamics
    lens3: clip01(bempedelis), // Scaling
    lens4: clip01(wavelet),    // Rhythm
    lens5: clip01(koopman),    // Engine
    lens6: clip01(emdScore),   // Decomposition
    lens7: clip01(tda),        // Topology
    lens8: clip01(te * 1.4),   // Carry
    lens9: 0, // Consensus — computed below
  };

  // 9th lens: consensus = mean - 0.35*std of the other 8
  const arr = Object.values(lenses).slice(0, 8); // exclude consensus placeholder
  const mean = arr.reduce((a, b) => a + b, 0) / arr.length;
  const variance = arr.reduce((a, b) => a + (b - mean) ** 2, 0) / arr.length;
  lenses.lens9 = clip01(mean - 0.35 * Math.sqrt(variance));

  const composite = Object.values(lenses).reduce((a, b) => a + b, 0) / 9;
  return { lenses, composite };
}

// ── Analog labeling ─────────────────────────────────────────────────────
function analogLabel(d: Date): string {
  const y = d.getFullYear(), mo = d.getMonth();
  if (y === 2000 && mo <= 6) return "Pre-dotcom topping pattern";
  if (y === 2001) return "Post-dotcom grind";
  if (y === 2002) return "Late-bear consolidation";
  if (y === 2007 && mo >= 6) return "Pre-GFC distribution";
  if (y === 2008) return "Lehman-era dislocation";
  if (y === 2011) return "Euro sovereign scare";
  if (y === 2015) return "China devaluation shock";
  if (y === 2018) return "Q4 vol regime-shift";
  if (y === 2020 && mo <= 2) return "Covid pre-crash coiling";
  if (y === 2020) return "Post-Covid recovery";
  if (y === 2022) return "Rate-hike drawdown";
  if (y === 2023) return "Mid-cycle base";
  return "Regime transition";
}

function analogNote(l: LensScores): string {
  const parts: string[] = [];
  if (l.lens1 > 0.7) parts.push("strong shape alignment");
  if (l.lens2 > 0.75) parts.push("temporal co-movement");
  if (l.lens5 > 0.7) parts.push("dynamical signature match");
  if (l.lens7 > 0.7) parts.push("geometric persistence");
  if (l.lens8 > 0.5) parts.push("predictive carry");
  if (!parts.length) parts.push("mixed-quality match");
  return parts.slice(0, 2).join(" \u00B7 ");
}

// ── Analog finder ───────────────────────────────────────────────────────
/**
 * Find the top-K analog matches for a query window starting at
 * queryStartIdx with length windowLen. Strides by 14 for perf.
 */
export function findAnalogs(
  queryStartIdx: number,
  windowLen: number,
  opts: { k?: number; horizon?: number } = {}
): AnalogMatch[] {
  const { k = 6, horizon = 60 } = opts;
  const qp = SERIES.slice(queryStartIdx, queryStartIdx + windowLen).map(d => d.p);
  const candidates: { startIdx: number; composite: number; lenses: LensScores }[] = [];
  const step = 14; // stride for speed

  for (let i = 200; i < queryStartIdx - windowLen - horizon; i += step) {
    const mp = SERIES.slice(i, i + windowLen).map(d => d.p);
    if (mp.length < windowLen) continue;
    const { lenses, composite } = scoreMatch(qp, mp);
    candidates.push({ startIdx: i, composite, lenses });
  }

  candidates.sort((a, b) => b.composite - a.composite);

  // Deduplicate overlapping neighbors
  const picked: typeof candidates = [];
  for (const c of candidates) {
    if (picked.some(p => Math.abs(p.startIdx - c.startIdx) < windowLen * 0.5)) continue;
    picked.push(c);
    if (picked.length >= k) break;
  }

  return picked.map((c, rank) => {
    const date = SERIES[c.startIdx].d;
    const endDate = SERIES[c.startIdx + windowLen - 1].d;
    const after = SERIES.slice(c.startIdx + windowLen, c.startIdx + windowLen + horizon).map(d => d.p);
    const afterReturn = after.length ? (after[after.length - 1] / SERIES[c.startIdx + windowLen - 1].p - 1) : 0;
    return {
      id: "A" + c.startIdx,
      rank: rank + 1,
      startIdx: c.startIdx,
      date,
      endDate,
      label: analogLabel(date),
      composite: c.composite,
      lenses: c.lenses,
      priceWindow: SERIES.slice(c.startIdx, c.startIdx + windowLen).map(d => d.p),
      after,
      afterReturn,
      note: analogNote(c.lenses),
    };
  });
}

// ── Forecast cone ───────────────────────────────────────────────────────
/**
 * Build quantile forecast cone from analogs' "what happened next" paths.
 * Returns an array of ConePoints with p10/p25/p50/p75/p90 price levels.
 */
export function buildCone(analogs: AnalogMatch[], horizon: number, queryLastPrice: number): ConePoint[] {
  const quants: ConePoint[] = [];
  for (let t = 0; t < horizon; t++) {
    const rets = analogs
      .map(a => a.after[t] ? (a.after[t] / a.priceWindow[a.priceWindow.length - 1]) : null)
      .filter((v): v is number => v !== null);
    if (!rets.length) break;
    rets.sort((a, b) => a - b);
    const q = (p: number) => {
      const idx = Math.max(0, Math.min(rets.length - 1, Math.floor(p * (rets.length - 1))));
      return rets[idx];
    };
    quants.push({
      t,
      p10: queryLastPrice * q(0.10),
      p25: queryLastPrice * q(0.25),
      p50: queryLastPrice * q(0.50),
      p75: queryLastPrice * q(0.75),
      p90: queryLastPrice * q(0.90),
    });
  }
  return quants;
}

// ── Calibration metrics from the analog set ────────────────────────────
/**
 * Calibration metric shape — mirrors the TS `CalibrationMetrics` in
 * `./types.ts`. Redeclared here so `data.ts` has no dependency on the
 * API types module (which would pull zod + schemas into the synthetic
 * path). Keep both in sync.
 */
export interface CalibrationResult {
  coverage: number;
  crps: number;
  hitRate: number;
  grade: "A" | "B" | "C" | "D" | "F" | "unknown";
  regimeDrift: "low" | "elevated" | "high" | "unknown";
  reliability: Array<{ predicted: number; observed: number }>;
  nAnalogs: number;
}

/**
 * Derive the grade band from the three continuous metrics.
 * Thresholds match `the-similarity-api/app/services.py::_grade_from_metrics`
 * exactly so the live and synthetic UIs render the same badge color.
 */
function gradeFromMetrics(coverageGap: number, crpsValue: number, hit: number): CalibrationResult["grade"] {
  if (coverageGap <= 0.05 && crpsValue <= 0.05 && hit >= 0.58) return "A";
  if (coverageGap <= 0.10 && crpsValue <= 0.08 && hit >= 0.54) return "B";
  if (coverageGap <= 0.15 && crpsValue <= 0.12 && hit >= 0.52) return "C";
  if (coverageGap <= 0.20 || crpsValue <= 0.20) return "D";
  return "F";
}

/**
 * Bucket cross-analog terminal-return dispersion into a regime drift
 * label. Same thresholds as `_regime_drift_from_dispersion` in the
 * Python service — see that function for the rationale.
 */
function regimeDriftFromDispersion(dispersion: number): CalibrationResult["regimeDrift"] {
  if (dispersion < 0.03) return "low";
  if (dispersion < 0.07) return "elevated";
  return "high";
}

/**
 * Compute calibration / trust metrics from the analog set + forecast cone.
 *
 * This is the client-side mirror of `build_calibration_metrics_response`
 * in the Python services module. It runs in two situations:
 *   1. Synthetic-fallback mode (no backend) — metrics change per query
 *      because the analog set changes.
 *   2. Live mode when the backend returned `null` for metrics — UI still
 *      shows *something* rather than the old hardcoded "78.4%".
 *
 * Input convention:
 *   - `analogs[i].after` is an array of *prices* (not returns) post-match
 *     for the synthetic engine, anchored at `priceWindow[last]`.
 *   - `cone[t].p50` etc. are absolute prices relative to the query's last
 *     price, produced by `buildCone`.
 *
 * All values are converted to cumulative returns before comparison so the
 * reliability buckets and coverage calculation are in a unit-free space.
 * When fewer than 3 analogs have forward windows, the function returns
 * an "unknown" grade with zeroed numerics (fail-closed).
 */
export function computeCalibrationMetrics(
  analogs: AnalogMatch[],
  cone: ConePoint[],
  queryLastPrice: number,
): CalibrationResult {
  // Collect realized terminal cumulative returns (per analog).
  const realized: number[] = [];
  for (const a of analogs) {
    if (!a.after || a.after.length === 0) continue;
    const terminalIdx = Math.min(a.after.length, cone.length) - 1;
    if (terminalIdx < 0) continue;
    const anchor = a.priceWindow[a.priceWindow.length - 1];
    if (!Number.isFinite(anchor) || anchor === 0) continue;
    const r = a.after[terminalIdx] / anchor - 1;
    if (!Number.isFinite(r)) continue;
    realized.push(r);
  }

  const nAnalogs = realized.length;
  if (cone.length === 0 || nAnalogs < 3 || !Number.isFinite(queryLastPrice) || queryLastPrice === 0) {
    return {
      coverage: 0,
      crps: 0,
      hitRate: 0,
      grade: "unknown",
      regimeDrift: "unknown",
      reliability: [],
      nAnalogs,
    };
  }

  // Convert the terminal cone prices to cumulative returns relative to the
  // query's last price so we can compare against `realized` directly.
  const terminal = cone[cone.length - 1];
  const pctToLevel: Record<string, number> = {
    "10": terminal.p10 / queryLastPrice - 1,
    "25": terminal.p25 / queryLastPrice - 1,
    "50": terminal.p50 / queryLastPrice - 1,
    "75": terminal.p75 / queryLastPrice - 1,
    "90": terminal.p90 / queryLastPrice - 1,
  };

  // Coverage: fraction of realized terminals inside the P10-P90 envelope.
  const lo = pctToLevel["10"];
  const hi = pctToLevel["90"];
  let inside = 0;
  for (const r of realized) if (r >= lo && r <= hi) inside++;
  const coverage = inside / nAnalogs;

  // Hit rate: sign(P50) vs sign(realized). Zero-P50 never scores a hit.
  const p50 = pctToLevel["50"];
  const p50Dir = p50 > 0 ? 1 : p50 < 0 ? -1 : 0;
  let hits = 0;
  for (const r of realized) {
    const realDir = r > 0 ? 1 : r < 0 ? -1 : 0;
    if (p50Dir !== 0 && p50Dir === realDir) hits++;
  }
  const hitRate = hits / nAnalogs;

  // Discrete CRPS across native percentile grid (10, 25, 50, 75, 90).
  const pcts = [10, 25, 50, 75, 90];
  const terminals = pcts.map(p => pctToLevel[String(p)]);
  const cdfLevels = pcts.map(p => p / 100);
  const crpsPer: number[] = [];
  for (const r of realized) {
    let sum = 0;
    for (let i = 0; i < pcts.length; i++) {
      const indicator = r <= terminals[i] ? 1 : 0;
      const diff = indicator - cdfLevels[i];
      sum += diff * diff;
    }
    crpsPer.push(sum / pcts.length);
  }
  const crpsValue = crpsPer.length ? crpsPer.reduce((a, b) => a + b, 0) / crpsPer.length : 0;

  // Reliability: for each percentile, empirical fraction of realized at/below.
  const reliability = pcts.map((p, i) => {
    const observed = realized.filter(r => r <= terminals[i]).length / nAnalogs;
    return {
      predicted: p / 100,
      observed: Math.max(0, Math.min(1, observed)),
    };
  });

  // Regime drift from terminal-return dispersion.
  const meanR = realized.reduce((a, b) => a + b, 0) / nAnalogs;
  const variance = realized.reduce((a, b) => a + (b - meanR) ** 2, 0) / nAnalogs;
  const dispersion = Math.sqrt(variance);
  const regimeDrift = regimeDriftFromDispersion(dispersion);

  const coverageGap = Math.abs(coverage - 0.80);
  const grade = gradeFromMetrics(coverageGap, crpsValue, hitRate);

  return {
    coverage: Math.max(0, Math.min(1, coverage)),
    crps: Math.max(0, crpsValue),
    hitRate: Math.max(0, Math.min(1, hitRate)),
    grade,
    regimeDrift,
    reliability,
    nAnalogs,
  };
}

// ── Formatting helpers ──────────────────────────────────────────────────
export function fmtDate(d: Date): string {
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

export function fmtDateShort(d: Date): string {
  return d.toLocaleDateString("en-US", { month: "short", year: "numeric" });
}

export function fmtPct(x: number, dig = 1): string {
  return (x >= 0 ? "+" : "") + (x * 100).toFixed(dig) + "%";
}

// ── Lens definitions ────────────────────────────────────────────────────
// Keys are opaque identifiers (lens1..lens9). Display names are vague but
// real-sounding — they describe the *kind* of similarity measured without
// revealing the underlying algorithm (DTW, Koopman, TDA, etc.).
export const LENS_DEFS = [
  { key: "lens1" as const, name: "Shape",         q: "Structural alignment" },
  { key: "lens2" as const, name: "Dynamics",      q: "Temporal co-movement" },
  { key: "lens3" as const, name: "Scaling",       q: "Power-law structure" },
  { key: "lens4" as const, name: "Rhythm",        q: "Multiscale texture" },
  { key: "lens5" as const, name: "Engine",        q: "Dynamical signature" },
  { key: "lens6" as const, name: "Decomposition", q: "Trend & residual" },
  { key: "lens7" as const, name: "Topology",      q: "Geometric persistence" },
  { key: "lens8" as const, name: "Carry",         q: "Predictive transfer" },
  { key: "lens9" as const, name: "Consensus",     q: "Cross-lens agreement" },
];
