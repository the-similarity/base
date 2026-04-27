/**
 * Cadence — Natural Language → Time Series engine.
 *
 * Deterministic fake-NLP parser that converts a free-text narrative of a
 * user's day into a sequence of valence events, then integrates those events
 * into a continuous series sampled at 5-minute intervals over a 16-hour
 * waking window.
 *
 * The output shape is the contract relied on by dashboard.tsx:
 *   - events: Event[]   (parsed sentence → {text, delta, tag, time, cert})
 *   - series: Point[]   (5-min samples across 16h, valence ∈ [0, 100])
 *
 * The parser is intentionally deterministic so the dashboard re-renders
 * predictably as the user types. The "30-day history" is pseudo-random but
 * seeded, so reloads produce identical data until the real engine ships.
 */

export interface Event {
  id: number;
  text: string;
  delta: number;
  tag: string;
  cert: number;
  time: number;
  appliedAt?: number;
}

export interface Point {
  t: number;
  v: number;
}

export interface HistoryDay {
  day: number;
  avg: number;
  text: string;
}

export interface Rhyme {
  startIdx: number;
  score: number;
}

// Lexicon: regex → valence delta, tag, certainty.
const LEXICON: { re: RegExp; d: number; tag: string; cert: number }[] = [
  { re: /\b(terrible|awful|devastat\w*|miserable|wrecked|shattered)\b/i, d: -28, tag: "low", cert: 0.9 },
  { re: /\b(bad|rough|hard|tough|difficult|painful|stressful)\b/i, d: -14, tag: "low", cert: 0.75 },
  { re: /\b(tired|exhausted|drained|sluggish|heavy|groggy)\b/i, d: -10, tag: "energy", cert: 0.7 },
  { re: /\b(anxious|worried|nervous|on edge|panicky)\b/i, d: -12, tag: "tension", cert: 0.8 },
  { re: /\b(annoyed|frustrated|irritated|angry|pissed)\b/i, d: -11, tag: "tension", cert: 0.8 },
  { re: /\b(sad|down|low|blue|gloomy|melanchol\w*)\b/i, d: -13, tag: "low", cert: 0.8 },
  { re: /\b(lonely|isolated|alone)\b/i, d: -10, tag: "low", cert: 0.75 },
  { re: /\b(bored|flat|dull|meh|okay|ok|fine)\b/i, d: -2, tag: "flat", cert: 0.5 },
  { re: /\b(work\w*|meeting|email\w*|standup|review)\b/i, d: -3, tag: "work", cert: 0.4 },
  { re: /\b(commut\w*|subway|traffic|drive|bus)\b/i, d: -2, tag: "move", cert: 0.4 },
  { re: /\b(lunch|dinner|breakfast|coffee|ate|eating|food)\b/i, d: 2, tag: "food", cert: 0.5 },
  { re: /\b(walk\w*|run|gym|yoga|stretch\w*|bike|ride)\b/i, d: 7, tag: "body", cert: 0.7 },
  { re: /\b(read\w*|book|music|listen\w*|podcast)\b/i, d: 4, tag: "quiet", cert: 0.6 },
  { re: /\b(nap|slept|sleep|rest\w*)\b/i, d: 5, tag: "rest", cert: 0.6 },
  { re: /\b(friend|texted|called|saw|met|talked to|hug\w*)\b/i, d: 9, tag: "social", cert: 0.75 },
  { re: /\b(laugh\w*|joke|funny|smile\w*)\b/i, d: 10, tag: "social", cert: 0.75 },
  { re: /\b(better|improv\w*|lift\w*|rebound\w*|recover\w*)\b/i, d: 12, tag: "rise", cert: 0.8 },
  { re: /\b(good|nice|pleasant|calm|peaceful)\b/i, d: 8, tag: "rise", cert: 0.7 },
  { re: /\b(great|wonderful|amazing|brilliant|love\w*|happy|joy\w*)\b/i, d: 18, tag: "high", cert: 0.85 },
  { re: /\b(breakthrough|flow|focused|productive|clicked)\b/i, d: 16, tag: "high", cert: 0.85 },
  { re: /\b(excited|energized|alive|thrilled)\b/i, d: 15, tag: "high", cert: 0.8 },
];

// Time-of-day anchors (minutes after wake, wake = 7am).
const TIME_ANCHORS: { re: RegExp; t: number }[] = [
  { re: /\bmorning\b/i, t: 2 * 60 },
  { re: /\bdawn|sunrise\b/i, t: 0 },
  { re: /\bnoon|midday|lunch\b/i, t: 5 * 60 },
  { re: /\bafternoon\b/i, t: 7 * 60 },
  { re: /\bevening|dinner\b/i, t: 11 * 60 },
  { re: /\bnight|bedtime\b/i, t: 14 * 60 },
  { re: /\blate night\b/i, t: 16 * 60 },
];

const INTENSIFIERS: { re: RegExp; mul: number }[] = [
  { re: /\b(really|very|so|extremely|incredibly|deeply)\s+/i, mul: 1.5 },
  { re: /\b(kind of|sort of|a little|slightly|barely|somewhat)\s+/i, mul: 0.5 },
];
const NEG = /\b(not|didn't|didnt|don't|dont|never|no longer|wasn't|wasnt)\s+(\w+\s+){0,3}/i;

function clamp(v: number, a: number, b: number): number {
  return Math.max(a, Math.min(b, v));
}

function splitSentences(text: string): string[] {
  const parts = text
    .replace(/\s+/g, " ")
    .trim()
    .split(/(?<=[.!?])\s+|(?<=,\s(?:then|and then|after that))\s+|\.\s+|,\s+(?=then|and then)/i);
  return parts.map((s) => s.trim()).filter(Boolean);
}

interface ParsedSentence {
  text: string;
  delta: number;
  tag: string;
  cert: number;
  time: number;
}

function parseSentence(sent: string, baseTime: number): ParsedSentence | null {
  const hits: { delta: number; tag: string; cert: number }[] = [];
  for (const lex of LEXICON) {
    const m = sent.match(lex.re);
    if (!m) continue;
    let d = lex.d;
    const idx = m.index ?? 0;
    const pre = sent.slice(Math.max(0, idx - 24), idx);
    for (const i of INTENSIFIERS) {
      if (i.re.test(pre)) d *= i.mul;
    }
    if (NEG.test(pre)) d = -d * 0.6;
    hits.push({ delta: d, tag: lex.tag, cert: lex.cert });
  }
  if (!hits.length) return null;

  // Sublinear aggregation so many hits don't explode.
  const delta = hits.reduce((a, h) => a + h.delta, 0) / Math.sqrt(hits.length);
  const tag = [...hits].sort((a, b) => Math.abs(b.delta) - Math.abs(a.delta))[0].tag;
  const cert = Math.min(0.95, hits.reduce((a, h) => a + h.cert, 0) / hits.length);

  let time = baseTime;
  for (const a of TIME_ANCHORS) {
    if (a.re.test(sent)) {
      time = a.t;
      break;
    }
  }
  return { text: sent, delta: Math.round(delta * 10) / 10, tag, cert, time };
}

export function parseNarrative(text: string): { events: Event[]; series: Point[] } {
  const sentences = splitSentences(text);
  if (!sentences.length) return { events: [], series: emptySeries() };

  const events: Event[] = [];
  let t = 60;
  sentences.forEach((s, i) => {
    const parsed = parseSentence(s, t);
    if (parsed) {
      events.push({ id: i, ...parsed });
      // Deterministic forward drift: 45-75 min between sentences unless
      // anchored. Using a sine of sentence index avoids Math.random() so
      // the output is stable across re-renders.
      t = parsed.time + 45 + Math.floor(Math.abs(Math.sin(i * 7.31)) * 30);
      if (t > 16 * 60) t = 16 * 60;
    }
  });
  events.sort((a, b) => a.time - b.time);

  const steps = (16 * 60) / 5 + 1;
  const series: Point[] = new Array(steps);
  let y = 50;
  let target = 50;
  const applied = new Set<number>();
  for (let i = 0; i < steps; i++) {
    const minute = i * 5;
    for (const ev of events) {
      if (applied.has(ev.id)) continue;
      if (ev.time <= minute) {
        target = clamp(target + ev.delta, 0, 100);
        applied.add(ev.id);
        ev.appliedAt = minute;
      }
    }
    y += (target - y) * 0.25;
    y += (Math.sin(minute / 23) + Math.cos(minute / 17)) * 0.4;
    series[i] = { t: minute, v: clamp(y, 0, 100) };
  }
  return { events, series };
}

function emptySeries(): Point[] {
  const steps = (16 * 60) / 5 + 1;
  return Array.from({ length: steps }, (_, i) => ({ t: i * 5, v: 50 }));
}

// Build a 30-day personal history with pre-seeded narratives.
// Deterministic via a linear-congruential RNG so reloads are stable.
export function buildHistory(todayAvg: number): HistoryDay[] {
  const days: HistoryDay[] = [];
  const narratives = [
    "slow morning. rough commute. lunch helped. productive afternoon. long walk. read before bed.",
    "woke up tired. bad meeting. lunch with a friend. afternoon was good. evening got heavy.",
    "great morning run. flow state all morning. lunch fine. afternoon dragged. nice dinner.",
    "anxious about the deadline. pushed through. friend called at night. felt better.",
    "low energy all day. napped. evening walk. okay night.",
    "really good day. breakthrough at work. laughed at dinner. calm night.",
  ];
  let seed = 7;
  const rand = () => {
    seed = (seed * 9301 + 49297) % 233280;
    return seed / 233280;
  };
  for (let d = 29; d >= 1; d--) {
    const pick = narratives[Math.floor(rand() * narratives.length)];
    const avg = 40 + rand() * 40;
    days.push({ day: d, avg: Math.round(avg), text: pick });
  }
  days.push({ day: 0, avg: todayAvg, text: "today" });
  return days;
}

// Find the 7-day rolling window that best "rhymes" (shape match) with today.
// Uses z-normalized RMSE over 7 sampled points.
export function findRhyme(history: HistoryDay[], today: Point[]): Rhyme | null {
  if (!today || today.length === 0) return null;
  const lastShape = sampleShape(today, 12);
  let best: Rhyme = { score: -Infinity, startIdx: 0 };
  for (let i = 0; i < history.length - 7; i++) {
    const window = history.slice(i, i + 7);
    const shape = window.map((d) => d.avg);
    const s1 = normalize(lastShape.slice(0, 7));
    const s2 = normalize(shape);
    const score = -rmse(s1, s2);
    if (score > best.score) best = { score, startIdx: i };
  }
  return best;
}

function sampleShape(series: Point[], n: number): number[] {
  const step = series.length / n;
  return Array.from({ length: n }, (_, i) => series[Math.floor(i * step)].v);
}
function normalize(arr: number[]): number[] {
  const mean = arr.reduce((a, b) => a + b, 0) / arr.length;
  const std = Math.sqrt(arr.reduce((a, b) => a + (b - mean) ** 2, 0) / arr.length) || 1;
  return arr.map((x) => (x - mean) / std);
}
function rmse(a: number[], b: number[]): number {
  const n = Math.min(a.length, b.length);
  let s = 0;
  for (let i = 0; i < n; i++) s += (a[i] - b[i]) ** 2;
  return Math.sqrt(s / n);
}
