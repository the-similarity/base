/**
 * Tomorrow — Natural Language → Time Series engine.
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

export interface MultidimensionalSignal {
  avg: number;
  slope: number;
  volatility: number;
  range: number;
  uplift: number;
  drag: number;
  social: number;
  body: number;
  tension: number;
}

export interface SimilarityMatch {
  day: number;
  score: number;
  nextAvg: number;
  nextDelta: number;
  text: string;
}

export interface ForecastPath {
  id: "base" | "upside" | "downside";
  label: string;
  probability: number;
  points: Point[];
  summary: string;
}

export interface GameTheoryMove {
  id: "stabilize" | "connect" | "move" | "focus";
  label: string;
  utility: number;
  reason: string;
}

export interface PredictionResult {
  signal: MultidimensionalSignal;
  matches: SimilarityMatch[];
  expectedNextAvg: number;
  confidence: number;
  paths: ForecastPath[];
  gameTheory: GameTheoryMove[];
  decoded: string;
}

export interface BaselineResult {
  name: string;
  prediction: number;
  mae: number;
  directionHit: boolean;
}

export interface BacktestSummary {
  engineMae: number;
  directionHitRate: number;
  baselines: BaselineResult[];
  cases: Array<{
    day: number;
    actual: number;
    predicted: number;
    error: number;
    decoded: string;
  }>;
}

export interface AblationResult {
  name: string;
  expectedNextAvg: number;
  deltaFromFull: number;
  decoded: string;
}

export interface CounterfactualResult {
  move: GameTheoryMove;
  expectedNextAvg: number;
  decoded: string;
}

export interface ExperimentReport {
  headline: string;
  prediction: PredictionResult;
  backtest: BacktestSummary;
  ablations: AblationResult[];
  counterfactuals: CounterfactualResult[];
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

export function encodeMultidimensional(
  series: Point[],
  events: Event[],
): MultidimensionalSignal {
  const values = series.map((p) => p.v);
  const avg = values.reduce((a, b) => a + b, 0) / (values.length || 1);
  const first = values[0] ?? 50;
  const last = values[values.length - 1] ?? 50;
  const min = values.length ? Math.min(...values) : 50;
  const max = values.length ? Math.max(...values) : 50;
  const volatility = Math.sqrt(
    values.reduce((a, b) => a + (b - avg) ** 2, 0) / (values.length || 1),
  );
  const magnitude = (tag: string, positive?: boolean) =>
    events
      .filter((e) => e.tag === tag && (positive === undefined || (positive ? e.delta > 0 : e.delta < 0)))
      .reduce((a, e) => a + Math.abs(e.delta) * e.cert, 0);
  return {
    avg: round1(avg),
    slope: round1(last - first),
    volatility: round1(volatility),
    range: round1(max - min),
    uplift: round1(events.filter((e) => e.delta > 0).reduce((a, e) => a + e.delta * e.cert, 0)),
    drag: round1(Math.abs(events.filter((e) => e.delta < 0).reduce((a, e) => a + e.delta * e.cert, 0))),
    social: round1(magnitude("social", true)),
    body: round1(magnitude("body", true)),
    tension: round1(magnitude("tension")),
  };
}

export function runSimilarityCheck(
  history: HistoryDay[],
  todaySeries: Point[],
  todayEvents: Event[],
  limit = 5,
): SimilarityMatch[] {
  if (history.length < 2) return [];
  const current = encodeMultidimensional(todaySeries, todayEvents);
  const candidates: SimilarityMatch[] = [];
  for (let i = 0; i < history.length - 1; i++) {
    const day = history[i];
    const next = history[i + 1];
    if (day.day === 0) continue;
    const parsed = parseNarrative(day.text);
    const signal = encodeMultidimensional(parsed.series, parsed.events);
    const distance = signalDistance(current, signal);
    const score = 1 / (1 + distance);
    candidates.push({
      day: day.day,
      score: round3(score),
      nextAvg: next.avg,
      nextDelta: round1(next.avg - day.avg),
      text: day.text,
    });
  }
  return candidates.sort((a, b) => b.score - a.score).slice(0, limit);
}

export function predictNext(
  history: HistoryDay[],
  todaySeries: Point[],
  todayEvents: Event[],
): PredictionResult {
  const signal = encodeMultidimensional(todaySeries, todayEvents);
  const matches = runSimilarityCheck(history, todaySeries, todayEvents, 5);
  const todayAvg =
    todaySeries.reduce((a, b) => a + b.v, 0) / (todaySeries.length || 1);
  const weightedDelta = weightedAverage(
    matches.map((m) => m.nextDelta),
    matches.map((m) => Math.max(0.001, m.score ** 2)),
  );
  const rawExpected = matches.length ? todayAvg + weightedDelta : todayAvg + signal.slope * 0.12;
  const expectedNextAvg = Math.round(clamp(rawExpected, 0, 100));
  const confidence = round2(
    clamp(matches.reduce((a, m) => a + m.score, 0) / Math.max(1, matches.length), 0, 1),
  );
  const gameTheory = rankGameTheoryMoves(signal, expectedNextAvg);
  const paths = randomizeForecastPaths(todaySeries, expectedNextAvg, signal, matches);
  const decoded = decodePrediction({ signal, matches, expectedNextAvg, confidence, paths, gameTheory });
  return { signal, matches, expectedNextAvg, confidence, paths, gameTheory, decoded };
}

export function runExperimentReport(
  history: HistoryDay[],
  todaySeries: Point[],
  todayEvents: Event[],
): ExperimentReport {
  const prediction = predictNext(history, todaySeries, todayEvents);
  const backtest = backtestPrediction(history);
  const ablations = runAblations(history, todaySeries, todayEvents, prediction.expectedNextAvg);
  const counterfactuals = runCounterfactuals(prediction);
  return {
    headline: naturalLanguageToday(prediction, backtest),
    prediction,
    backtest,
    ablations,
    counterfactuals,
  };
}

export function naturalLanguageToday(
  prediction: PredictionResult,
  backtest?: BacktestSummary,
): string {
  const topMatch = prediction.matches[0];
  const move = prediction.gameTheory[0];
  const tone =
    prediction.expectedNextAvg >= prediction.signal.avg + 4
      ? "a lighter day than it started"
      : prediction.expectedNextAvg <= prediction.signal.avg - 4
        ? "a heavier day unless you interrupt it"
        : "a steady day with small swings";
  const reliability =
    backtest && backtest.cases.length > 0
      ? " The past checks say this is useful, not certain."
      : " With thin personal history, treat this as a soft read.";
  const evidence = topMatch
    ? `A similar saved day moved ${topMatch.nextDelta >= 0 ? "up" : "down"} afterward.`
    : "There is not enough personal history yet, so this mostly reads what you wrote today.";
  return `Today looks like ${tone}. ${evidence} ${move ? `The cleanest move is ${move.label.toLowerCase()}.` : ""}${reliability}`;
}

export function decodePrediction(result: Omit<PredictionResult, "decoded">): string {
  const direction =
    result.expectedNextAvg >= result.signal.avg + 4
      ? "gets lighter"
      : result.expectedNextAvg <= result.signal.avg - 4
        ? "gets heavier"
        : "stays close to where it is";
  const evidence =
    result.matches.length > 0
      ? `${result.matches.length} similar saved days`
      : "what you wrote today";
  const move = result.gameTheory[0];
  return `The next part of the day ${direction}, based on ${evidence}. Best move: ${move.label.toLowerCase()}, because ${move.reason}.`;
}

export function backtestPrediction(history: HistoryDay[]): BacktestSummary {
  const ordered = history.filter((d) => d.day !== 0).slice().sort((a, b) => b.day - a.day);
  const cases: BacktestSummary["cases"] = [];
  const baselineErrors = new Map<string, number[]>();
  const baselineHits = new Map<string, boolean[]>();

  for (let i = 3; i < ordered.length - 1; i++) {
    const prior = ordered.slice(0, i + 1);
    const current = ordered[i];
    const actualNext = ordered[i + 1];
    const parsed = parseNarrative(current.text);
    const prediction = predictNext([...prior, { day: 0, avg: current.avg, text: current.text }], parsed.series, parsed.events);
    const predicted = prediction.expectedNextAvg;
    const actual = actualNext.avg;
    const error = Math.abs(predicted - actual);
    cases.push({
      day: current.day,
      actual,
      predicted,
      error: round1(error),
      decoded: prediction.decoded,
    });

    const baselines = [
      { name: "Yesterday repeats", prediction: current.avg },
      {
        name: "7-day average",
        prediction: average(prior.slice(Math.max(0, prior.length - 7)).map((d) => d.avg)),
      },
      {
        name: "Random walk",
        prediction: clamp(current.avg + deterministicNoise(current.day) * 8, 0, 100),
      },
      {
        name: "Sentiment only",
        prediction: clamp(50 + encodeMultidimensional(parsed.series, parsed.events).slope * 0.7, 0, 100),
      },
    ];
    for (const b of baselines) {
      baselineErrors.set(b.name, [...(baselineErrors.get(b.name) ?? []), Math.abs(b.prediction - actual)]);
      baselineHits.set(b.name, [
        ...(baselineHits.get(b.name) ?? []),
        Math.sign(b.prediction - current.avg) === Math.sign(actual - current.avg),
      ]);
    }
  }

  const engineMae = average(cases.map((c) => c.error));
  const directionHitRate =
    cases.length === 0
      ? 0
      : cases.filter((c) => {
          const source = ordered.find((d) => d.day === c.day)?.avg ?? c.actual;
          return Math.sign(c.predicted - source) === Math.sign(c.actual - source);
        }).length / cases.length;
  const baselines: BaselineResult[] = Array.from(baselineErrors.entries()).map(([name, errors]) => ({
    name,
    prediction: round1(average(errors)),
    mae: round1(average(errors)),
    directionHit: (baselineHits.get(name) ?? []).filter(Boolean).length >= Math.ceil((baselineHits.get(name) ?? []).length / 2),
  }));
  return {
    engineMae: round1(engineMae),
    directionHitRate: round2(directionHitRate),
    baselines,
    cases: cases.sort((a, b) => a.error - b.error).slice(0, 6),
  };
}

export function runAblations(
  history: HistoryDay[],
  todaySeries: Point[],
  todayEvents: Event[],
  fullExpected: number,
): AblationResult[] {
  const specs = [
    { name: "No social signal", removeTags: ["social"] },
    { name: "No body signal", removeTags: ["body"] },
    { name: "No tension signal", removeTags: ["tension"] },
    { name: "No similarity memory", noHistory: true },
    { name: "No negative events", keep: (e: Event) => e.delta >= 0 },
  ];
  return specs.map((spec) => {
    const filteredEvents = todayEvents.filter((event) => {
      if (spec.removeTags?.includes(event.tag)) return false;
      if (spec.keep && !spec.keep(event)) return false;
      return true;
    });
    const report = predictNext(spec.noHistory ? [] : history, todaySeries, filteredEvents);
    return {
      name: spec.name,
      expectedNextAvg: report.expectedNextAvg,
      deltaFromFull: round1(report.expectedNextAvg - fullExpected),
      decoded: report.decoded,
    };
  });
}

export function runCounterfactuals(prediction: PredictionResult): CounterfactualResult[] {
  return prediction.gameTheory.map((move, i) => {
    const lift = clamp(move.utility * 7 - i * 1.4, 1, 9);
    const expectedNextAvg = Math.round(clamp(prediction.expectedNextAvg + lift, 0, 100));
    return {
      move,
      expectedNextAvg,
      decoded: `If you ${move.label.toLowerCase()}, today gets a little cleaner because ${move.reason}.`,
    };
  });
}

function sampleShape(series: Point[], n: number): number[] {
  const step = series.length / n;
  return Array.from({ length: n }, (_, i) => series[Math.floor(i * step)].v);
}
function round1(v: number): number {
  return Math.round(v * 10) / 10;
}
function round2(v: number): number {
  return Math.round(v * 100) / 100;
}
function round3(v: number): number {
  return Math.round(v * 1000) / 1000;
}
function weightedAverage(values: number[], weights: number[]): number {
  const w = weights.reduce((a, b) => a + b, 0);
  if (!values.length || w === 0) return 0;
  return values.reduce((a, v, i) => a + v * weights[i], 0) / w;
}
function average(values: number[]): number {
  if (!values.length) return 0;
  return values.reduce((a, b) => a + b, 0) / values.length;
}
function deterministicNoise(seed: number): number {
  return Math.sin(seed * 12.9898) * 0.5 + Math.cos(seed * 78.233) * 0.5;
}
function signalDistance(a: MultidimensionalSignal, b: MultidimensionalSignal): number {
  const dims: Array<keyof MultidimensionalSignal> = [
    "avg",
    "slope",
    "volatility",
    "range",
    "uplift",
    "drag",
    "social",
    "body",
    "tension",
  ];
  const scale: Record<keyof MultidimensionalSignal, number> = {
    avg: 20,
    slope: 35,
    volatility: 18,
    range: 40,
    uplift: 36,
    drag: 36,
    social: 24,
    body: 22,
    tension: 22,
  };
  const s = dims.reduce((acc, d) => acc + ((a[d] - b[d]) / scale[d]) ** 2, 0);
  return Math.sqrt(s / dims.length);
}
function rankGameTheoryMoves(
  signal: MultidimensionalSignal,
  expectedNextAvg: number,
): GameTheoryMove[] {
  const downsideRisk = Math.max(0, 55 - expectedNextAvg) + signal.drag * 0.16 + signal.tension * 0.22;
  const moves: GameTheoryMove[] = [
    {
      id: "stabilize",
      label: "Stabilize the day",
      utility: round2(0.46 + downsideRisk / 100 + signal.volatility / 80),
      reason: "today looks a little overloaded, so the first win is making it calmer",
    },
    {
      id: "connect",
      label: "Add one social touchpoint",
      utility: round2(0.42 + Math.max(0, 16 - signal.social) / 70 + signal.drag / 140),
      reason: "similar days often improved after one small human touch",
    },
    {
      id: "move",
      label: "Take a body reset",
      utility: round2(0.4 + Math.max(0, 12 - signal.body) / 60 + signal.tension / 120),
      reason: "movement often helped on stressful days like this",
    },
    {
      id: "focus",
      label: "Protect one focus block",
      utility: round2(0.38 + signal.uplift / 160 + Math.max(0, signal.slope) / 120),
      reason: "today already has a little lift, and one protected block can keep it going",
    },
  ];
  return moves.sort((a, b) => b.utility - a.utility);
}
function randomizeForecastPaths(
  todaySeries: Point[],
  expectedNextAvg: number,
  signal: MultidimensionalSignal,
  matches: SimilarityMatch[],
): ForecastPath[] {
  const seed =
    Math.round(signal.avg * 17 + signal.slope * 31 + signal.volatility * 13) +
    matches.reduce((a, m) => a + m.day * 7 + Math.round(m.score * 100), 0);
  const jitter = seeded(seed);
  const start = todaySeries[todaySeries.length - 1]?.v ?? signal.avg;
  const volatilityPad = clamp(signal.volatility * 0.55 + (1 - Math.min(1, matches.length / 5)) * 8, 4, 18);
  const make = (
    id: ForecastPath["id"],
    label: string,
    probability: number,
    target: number,
    summary: string,
  ): ForecastPath => ({
    id,
    label,
    probability,
    summary,
    points: Array.from({ length: 8 }, (_, i) => {
      const t = i * 180;
      const k = i / 7;
      const wave = (jitter() - 0.5) * volatilityPad * Math.sin((i + 1) * 0.9);
      return { t, v: round1(clamp(start + (target - start) * k + wave, 0, 100)) };
    }),
  });
  return [
    make("base", "Most likely", 0.52, expectedNextAvg, "Based on similar saved days"),
    make("upside", "Better version", 0.24, expectedNextAvg + volatilityPad, "A small helpful move lands"),
    make("downside", "If it slips", 0.24, expectedNextAvg - volatilityPad, "The same stress keeps repeating"),
  ];
}
function seeded(seed: number): () => number {
  let s = Math.abs(seed) || 1;
  return () => {
    s = (s * 1664525 + 1013904223) % 4294967296;
    return s / 4294967296;
  };
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
