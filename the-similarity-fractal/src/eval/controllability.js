/**
 * Controllability checks — does varying knob X actually move metric Y?
 *
 * For each (knob, metric) pair we compute:
 *   - Pearson correlation between knob value and the cell-aggregated metric
 *   - A permutation p-value for that correlation (two-sided)
 *
 * Why not a closed-form t-test: knob distributions in a grid sweep are
 * coarse (often 2–5 unique values) and non-gaussian, so a permutation test is
 * a better honest-signal indicator and keeps us dependency-free.
 *
 * Cell-aggregation rule:
 *   A single "observation" per (knobs, seed) cell is the terminal-window
 *   mean of the metric — specifically the mean over the LAST 20% of ticks.
 *   Transient startup dynamics are noisy; the tail reflects steady state
 *   and is what a product decision would actually care about ("does setting
 *   food_spawn_rate=0.1 give me more mean_energy at t=end?").
 *
 * Non-numeric knobs are skipped — we only compute effect sizes on knobs that
 * vary over real numbers. If every knob setting is identical (0 variance)
 * we emit `effect_size: 0, p_value: 1` so downstream consumers don't have
 * to special-case "knob never moved."
 *
 * @module eval/controllability
 */

/** Metrics we score by default. Override via `opts.metrics`. */
const DEFAULT_METRICS = Object.freeze([
  'alive', 'mean_energy', 'mean_age',
  'food_count', 'cumulative_deaths', 'cumulative_food_eaten',
]);

/** Pearson correlation — returns 0 when either series has zero variance. */
function pearson(xs, ys) {
  const n = xs.length;
  if (n !== ys.length || n < 2) return 0;
  let sx = 0, sy = 0;
  for (let i = 0; i < n; i++) { sx += xs[i]; sy += ys[i]; }
  const mx = sx / n, my = sy / n;
  let num = 0, dx2 = 0, dy2 = 0;
  for (let i = 0; i < n; i++) {
    const dx = xs[i] - mx, dy = ys[i] - my;
    num += dx * dy;
    dx2 += dx * dx;
    dy2 += dy * dy;
  }
  const denom = Math.sqrt(dx2 * dy2);
  return denom > 0 ? num / denom : 0;
}

/**
 * Deterministic Fisher–Yates shuffle using a seeded Lehmer RNG. Seeding
 * makes the permutation test reproducible — a fixed telemetry input gives a
 * fixed p-value, which is important for test stability.
 */
function seededShuffle(arr, seed) {
  const out = arr.slice();
  let state = (seed | 0) || 1;
  const rand = () => {
    state = Math.imul(state, 48271) | 0;
    if (state <= 0) state += 0x7fffffff;
    return (state & 0x7fffffff) / 0x7fffffff;
  };
  for (let i = out.length - 1; i > 0; i--) {
    const j = Math.floor(rand() * (i + 1));
    [out[i], out[j]] = [out[j], out[i]];
  }
  return out;
}

/**
 * Two-sided permutation p-value for Pearson correlation.
 * Returns ~1.0 under the null (no relationship), near 0 when the knob
 * strongly predicts the metric.
 */
export function permutationPValue(xs, ys, { nPerm = 500, seed = 1 } = {}) {
  const observed = Math.abs(pearson(xs, ys));
  if (observed === 0) return 1;
  let as_extreme = 0;
  for (let p = 0; p < nPerm; p++) {
    const shuffled = seededShuffle(ys, seed + p);
    if (Math.abs(pearson(xs, shuffled)) >= observed) as_extreme += 1;
  }
  // +1 smoothing so p is never exactly 0 — conservative and standard for
  // Monte Carlo permutation tests with finite nPerm.
  return (as_extreme + 1) / (nPerm + 1);
}

/**
 * Aggregate telemetry into one observation per (knobs, seed) cell, where
 * the observation is the mean of each metric over the final `tailFrac` of
 * ticks. Exported so tests can assert aggregation behavior independently of
 * the correlation logic.
 */
export function aggregateCells(telemetry, { metrics, tailFrac = 0.2 } = {}) {
  if (tailFrac <= 0 || tailFrac > 1) {
    throw new RangeError(`aggregateCells: tailFrac must be in (0, 1], got ${tailFrac}`);
  }
  // Group rows by (seed, knobs) — we build the key from every non-metric,
  // non-`tick` field on the row.
  const metricSet = new Set(metrics ?? DEFAULT_METRICS);
  const groups = new Map();
  for (const row of telemetry) {
    const idParts = [];
    const idObj = {};
    for (const k of Object.keys(row).sort()) {
      if (k === 'tick' || metricSet.has(k)) continue;
      idParts.push(`${k}=${JSON.stringify(row[k])}`);
      idObj[k] = row[k];
    }
    const key = idParts.join('|');
    if (!groups.has(key)) groups.set(key, { id: idObj, rows: [] });
    groups.get(key).rows.push(row);
  }
  const cells = [];
  for (const { id, rows } of groups.values()) {
    rows.sort((a, b) => a.tick - b.tick);
    // Tail window = last ceil(N * tailFrac) ticks, minimum 1.
    const tailN = Math.max(1, Math.ceil(rows.length * tailFrac));
    const tail = rows.slice(-tailN);
    const means = {};
    for (const m of metricSet) {
      let s = 0;
      let c = 0;
      for (const r of tail) {
        if (typeof r[m] === 'number' && Number.isFinite(r[m])) { s += r[m]; c += 1; }
      }
      means[m] = c > 0 ? s / c : 0;
    }
    cells.push({ id, means });
  }
  return cells;
}

/**
 * Compute controllability: { knob → { metric → {effect_size, p_value, n} } }.
 *
 * effect_size is Pearson r in [-1, 1]; p_value is a two-sided permutation
 * p-value against the null of no relationship. Only knobs with ≥2 distinct
 * numeric values are scored.
 */
export function controllability(telemetry, {
  knobNames,
  metrics = DEFAULT_METRICS,
  tailFrac = 0.2,
  nPerm = 500,
  seed = 1,
} = {}) {
  const cells = aggregateCells(telemetry, { metrics, tailFrac });
  // Infer knob names if not provided — any key on id that isn't `seed`.
  let knobs = knobNames;
  if (!knobs) {
    const s = new Set();
    for (const c of cells) for (const k of Object.keys(c.id)) if (k !== 'seed') s.add(k);
    knobs = [...s].sort();
  }

  const result = {};
  for (const knob of knobs) {
    // Only score knobs where every cell has a finite numeric value.
    const xs = [];
    const present = [];
    for (const c of cells) {
      const v = c.id[knob];
      if (typeof v !== 'number' || !Number.isFinite(v)) { xs.length = 0; break; }
      xs.push(v);
      present.push(c);
    }
    if (xs.length === 0) continue; // non-numeric knob — skip silently
    const distinct = new Set(xs);
    if (distinct.size < 2) continue; // no variance, effect is undefined

    const perKnob = {};
    for (const m of metrics) {
      const ys = present.map((c) => c.means[m] ?? 0);
      const r = pearson(xs, ys);
      const p = permutationPValue(xs, ys, { nPerm, seed });
      perKnob[m] = {
        effect_size: r,
        p_value: p,
        n: xs.length,
      };
    }
    result[knob] = perKnob;
  }
  return result;
}
