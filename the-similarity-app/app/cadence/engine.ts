/**
 * Cadence — self-similarity engine over the user's OWN longitudinal data.
 *
 * The soul of the product: find past 7-day windows in Buba's history that
 * "rhyme" with today's 7-day window across multivariate biomarkers (HRV,
 * RHR, sleep, energy, glucose). For each rhyme, surface the 14-day
 * outcome that followed — the calibrated forecast for what's likely to
 * happen next.
 *
 * This mirrors `app/prudent/engine.ts`'s `findRhyme` but for biomarker
 * tuples instead of valence narratives. The shape of the API is
 * deliberately small and side-effect free so the rhymes screen can call
 * it from a useMemo without owning any caching layer.
 *
 * ─────────── Mathematical formulation ───────────
 *
 * Query window  q ∈ R^{W × C}   (W = 7 days, C = 5 channels)
 * History H = {h_i ∈ R^{W × C} : i = startIdx, …, max-W}
 *
 * For each candidate window h_i:
 *   1. z-normalize each channel of q and h_i independently:
 *         z(x) = (x - mean(x)) / std(x)
 *   2. compute per-channel L2 distance:
 *         d_c = sqrt( Σ_t (z_q[t,c] - z_h[t,c])² / W )
 *   3. average across channels (equal weight; later versions can weight
 *      by channel reliability or user-specified importance):
 *         D(q, h_i) = mean_c d_c
 *   4. similarity score = 100 * exp(-D), bounded [0, 100], sortable
 *      descending. Rationale for exp: D is unbounded and right-skewed for
 *      noisy windows; exp(-D) maps 0 → 100, 1 → ~37, 2 → ~14, which gives
 *      a nice visual scale ("85% similar" feels right when D ≈ 0.16).
 *
 * Top-K rhymes are returned with their similarity score AND a slice of
 * the 14 days AFTER the window (clamped to history length) so the rhymes
 * screen can render "what came next" outcomes.
 *
 * ─────────── Outcome labeling ───────────
 *
 * outcomeLabel(window) summarizes the 14 post-window days into a coarse
 * narrative tag (illness / overtraining / breakthrough / steady / recovery)
 * by checking simple rules over the BASELINE-relative trajectory. This is
 * intentionally rule-based rather than ML — the demo data is small and
 * the rules are interpretable for product-validation review.
 *
 * ─────────── Determinism ───────────
 *
 * Pure function of the inputs. The same DAYS array yields the same rhymes
 * on every render. Screens MUST useMemo the result keyed on (DAYS, k)
 * because the inner loop is O(N · W · C) where N = history length.
 *
 * ─────────── Why this is the soul of the product ───────────
 *
 * The pitch is "your body has rhymed before — here's what came next."
 * This is what makes Cadence the personal-health surface of the
 * Similarity primitive: no cohort, no HIPAA scramble, no "is this
 * stranger like me" question. Pure self-similarity over your own log.
 */

import type { DaySummary, TagKind } from "./_components/data";
import { BASELINE } from "./_components/data";

// ─────────── public types ───────────

export interface RhymeWindow {
  /** Index in DAYS where the window STARTS (most recent of the 7 days). */
  startIdx: number;
  /** Index in DAYS where the window ENDS (oldest of the 7 days). */
  endIdx: number;
  /** Similarity score 0-100; higher = more similar to query. */
  score: number;
  /** Raw average L2 distance (lower = better). */
  distance: number;
  /** The 7-day window slice itself (most recent first, matching DAYS). */
  window: DaySummary[];
  /** Up to 14 days that came after the window in history. */
  outcome: DaySummary[];
  /** Coarse narrative tag for the outcome. */
  outcomeLabel: OutcomeLabel;
  /** Optional context note from any TAGGED_PERIODS overlapping the window. */
  contextTag?: TagKind;
}

export type OutcomeLabel =
  | "illness"
  | "overtraining"
  | "breakthrough"
  | "steady"
  | "recovery"
  | "fatigue cycle";

/**
 * The 5 biomarker channels we compare across. Order matters — keep stable
 * across the engine because per-channel distances are reduced by index.
 *
 * Why these 5: they're the most widely-collected daily metrics from
 * mainstream wearables (Whoop / Oura / Apple Watch + a CGM), and they
 * span autonomic recovery (HRV, RHR), sleep, subjective wellness
 * (energy), and metabolic load (glucose). Adding morning weight or
 * training load would tighten the rhyme but also bias toward
 * weight-fluctuation noise.
 */
export const RHYME_CHANNELS = ["hrv", "rhr", "sleep", "energy", "glucose"] as const;
export type ChannelKey = (typeof RHYME_CHANNELS)[number];

// ─────────── core API ───────────

export interface FindRhymesOptions {
  /** Window length in days (default 7). */
  window?: number;
  /** Top-K to return (default 5). */
  k?: number;
  /** Min separation between query window and matched window (default 14). */
  minLag?: number;
  /** Max history depth to search (default: full DAYS length). */
  maxHistory?: number;
}

/**
 * Find the top-K most-similar past 7-day windows to the query window.
 *
 * @param history full history (DAYS), most recent first.
 * @param query   the 7-day query window (most recent first). Typically
 *                history.slice(0, 7) for "today's window".
 * @param opts    tuning knobs (window, k, minLag, maxHistory).
 * @returns       up to k RhymeWindow records sorted by score desc.
 */
export function findRhymes(
  history: DaySummary[],
  query: DaySummary[],
  opts: FindRhymesOptions = {}
): RhymeWindow[] {
  const { window: W = 7, k = 5, minLag = 14, maxHistory = history.length } = opts;
  if (query.length < W || history.length < W + minLag) return [];

  // Pre-extract z-normalized query channels — done once.
  const qZ: Record<ChannelKey, number[]> = {} as Record<ChannelKey, number[]>;
  for (const c of RHYME_CHANNELS) {
    qZ[c] = znorm(query.slice(0, W).map((d) => d[c] as number));
  }

  const hits: RhymeWindow[] = [];
  // Slide windows across history. We start at minLag (so we don't compare
  // today to yesterday's overlapping window) and end at maxHistory - W so
  // the candidate window has W complete days.
  for (let s = minLag; s <= maxHistory - W; s++) {
    const w = history.slice(s, s + W);
    let dSum = 0;
    let dCount = 0;
    for (const c of RHYME_CHANNELS) {
      const cz = znorm(w.map((d) => d[c] as number));
      dSum += rmse(qZ[c], cz);
      dCount += 1;
    }
    const distance = dSum / dCount;
    const score = Math.round(100 * Math.exp(-distance));

    // Outcome = the 14 days BEFORE (older days are higher idx, but in
    // wall-clock terms they came AFTER the window; remember history is
    // most-recent-first, so outcome days have idx LESS than s).
    const outcomeStart = Math.max(0, s - 14);
    const outcomeEnd = s; // exclusive
    const outcome = history.slice(outcomeStart, outcomeEnd);
    const outcomeLabel = labelOutcome(outcome);

    // Pull the most distinctive context tag in the window (if any).
    const contextTag = w.find((d) => d.tag && d.tag !== "normal")?.tag;

    hits.push({
      startIdx: s,
      endIdx: s + W - 1,
      score,
      distance,
      window: w,
      outcome,
      outcomeLabel,
      contextTag,
    });
  }

  // Sort by score desc, take top k. We do this rather than a partial sort
  // because k <= 50 and N <= 365, so Array.sort is comfortably under 1ms.
  hits.sort((a, b) => b.score - a.score);
  return hits.slice(0, k);
}

/**
 * Given the 14 days that followed a rhyming window, summarize what
 * happened. Coarse rule-based labels keep the demo legible.
 *
 * Rules (checked in priority order — first match wins):
 *   illness       — 3+ days where RHR > baseline+8 and HRV < baseline-15
 *   overtraining  — 5+ days where HRV stays > 10 below baseline AND
 *                   training load drops below 4 (forced backoff)
 *   breakthrough  — 3+ days where HRV > baseline+10 and recovery > 80
 *   recovery      — average HRV trend +5 ms across the 14d
 *   fatigue cycle — average energy < 60 across the 14d AND no illness
 *   steady        — fallthrough
 */
function labelOutcome(after: DaySummary[]): OutcomeLabel {
  if (after.length === 0) return "steady";
  const sickDays = after.filter(
    (d) => d.rhr > BASELINE.rhr + 8 && d.hrv < BASELINE.hrv - 15
  ).length;
  if (sickDays >= 3) return "illness";

  const overtrainDays = after.filter(
    (d) => d.hrv < BASELINE.hrv - 10 && d.trainingLoad < 4
  ).length;
  if (overtrainDays >= 5) return "overtraining";

  const breakDays = after.filter(
    (d) => d.hrv > BASELINE.hrv + 10 && d.recovery > 80
  ).length;
  if (breakDays >= 3) return "breakthrough";

  // HRV trend: avg of first 4 vs last 4 days
  const head = after.slice(after.length - 4);
  const tail = after.slice(0, 4);
  const trend = avg(tail.map((d) => d.hrv)) - avg(head.map((d) => d.hrv));
  if (trend > 5) return "recovery";

  if (avg(after.map((d) => d.energy)) < 60) return "fatigue cycle";
  return "steady";
}

// ─────────── projection (forecast cone) ───────────

export interface ForecastPoint {
  day: number;     // 1..14 days from now
  median: number;  // p50 HRV projection
  p10: number;     // p10 (worst 10%)
  p90: number;     // p90 (best 10%)
}

/**
 * Build a 14-day forecast cone from the top-K rhymes.
 *
 * For each day d in 1..14, take the HRV value of each rhyme's outcome at
 * the corresponding offset (most-recent-first), weighted by the rhyme's
 * similarity score. The median, p10, p90 are taken across this weighted
 * sample.
 *
 * Weighting: w_i = score_i / sum(scores). This is intentionally simple
 * (not exponential decay) because k is small (≤5) and a sharper weight
 * would collapse the cone to almost just the top-1 rhyme, hiding the
 * disagreement between analogues — which is exactly what the cone width
 * is supposed to communicate.
 */
export function projectFromRhymes(rhymes: RhymeWindow[], horizon = 14): ForecastPoint[] {
  if (rhymes.length === 0) return [];
  const totalW = rhymes.reduce((s, r) => s + r.score, 0) || 1;
  const out: ForecastPoint[] = [];
  for (let d = 1; d <= horizon; d++) {
    const samples: { v: number; w: number }[] = [];
    for (const r of rhymes) {
      // Outcome is most-recent-first, so day d means r.outcome[d-1] when
      // counting forward in time from the window's "end".
      const pt = r.outcome[Math.min(r.outcome.length - 1, d - 1)];
      if (pt) samples.push({ v: pt.hrv, w: r.score / totalW });
    }
    if (samples.length === 0) continue;
    samples.sort((a, b) => a.v - b.v);
    out.push({
      day: d,
      median: weightedQuantile(samples, 0.5),
      p10: weightedQuantile(samples, 0.1),
      p90: weightedQuantile(samples, 0.9),
    });
  }
  return out;
}

// ─────────── helpers ───────────

function znorm(arr: number[]): number[] {
  const m = avg(arr);
  const s = std(arr, m) || 1;
  return arr.map((x) => (x - m) / s);
}

function rmse(a: number[], b: number[]): number {
  const n = Math.min(a.length, b.length);
  let s = 0;
  for (let i = 0; i < n; i++) s += (a[i] - b[i]) ** 2;
  return Math.sqrt(s / n);
}

function avg(arr: number[]): number {
  if (arr.length === 0) return 0;
  return arr.reduce((s, x) => s + x, 0) / arr.length;
}

function std(arr: number[], m?: number): number {
  if (arr.length === 0) return 0;
  const mean = m ?? avg(arr);
  return Math.sqrt(avg(arr.map((x) => (x - mean) ** 2)));
}

function weightedQuantile(samples: { v: number; w: number }[], q: number): number {
  // Samples must be pre-sorted by v ascending.
  const total = samples.reduce((s, x) => s + x.w, 0);
  let acc = 0;
  for (const sm of samples) {
    acc += sm.w;
    if (acc / total >= q) return sm.v;
  }
  return samples[samples.length - 1].v;
}

// ─────────── outcome label display helpers ───────────

export const OUTCOME_META: Record<OutcomeLabel, { label: string; color: string; tone: "pos" | "neg" | "warn" | "default" }> = {
  illness: { label: "→ got sick", color: "#c2655c", tone: "neg" },
  overtraining: { label: "→ overtraining cycle", color: "#b14a3a", tone: "neg" },
  breakthrough: { label: "→ breakthrough week", color: "#5b8a72", tone: "pos" },
  recovery: { label: "→ recovery curve", color: "#5b8a72", tone: "pos" },
  steady: { label: "→ steady", color: "#7a7a75", tone: "default" },
  "fatigue cycle": { label: "→ extended fatigue", color: "#c89a4a", tone: "warn" },
};
