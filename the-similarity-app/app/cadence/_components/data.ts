/**
 * Cadence — demo data fixtures for "Buba", a fictional 365-day longitudinal
 * health record.
 *
 * This module holds ALL synthetic personal-health data used by the Cadence
 * workstation page (`/cadence`). It is generated deterministically (seeded
 * LCG, no Math.random in the data path) so reloads produce identical
 * scenarios — critical so screenshots stay stable and rhyme finding
 * returns the same analogues every render.
 *
 * Date anchor: the most recent day is 2026-04-26 (yesterday relative to
 * today's mocked "current" date 2026-04-27). The timeline runs back 365
 * days to 2025-04-27.
 *
 * Data immutability: every export below is a frozen-by-convention literal.
 * Screens MUST treat the arrays as read-only. Mutating them in place will
 * reflect across every screen because the same module object is shared at
 * runtime.
 *
 * What's modeled:
 *   - DAYS[]                       — 365-day daily summary (HRV, RHR, sleep,
 *                                    energy, glucose, recovery, training)
 *   - TODAY_HOURLY[]               — today's 24-hour HR series (vs baseline)
 *   - LABS[]                       — 9 long-term biomarkers + 5 historical draws
 *   - SOURCES[]                    — connected wearable cards
 *   - LOG_EVENTS[]                 — chronological log entries (last 7 days)
 *   - TAGGED_PERIODS[]             — illness/travel/training/normal periods
 *
 * Realism notes (per spec):
 *   - HRV roams 50-80ms, weekly cycle (lower Mondays after weekend)
 *   - RHR roams 50-65, slight elevation during illness/travel
 *   - Sleep 6-9h, weekend sleep-ins detectable
 *   - 3 distinct tagged periods that the rhyme finder can surface as analogues
 *   - 5 lab draws spanning 18 months with realistic trends
 */

// =====================================================================
// Date anchor + helper
// =====================================================================
//
// All time math anchors on 2026-04-27 ("today"). Day index 0 is yesterday
// (the most recent COMPLETED day with a full biomarker reading), counting
// up to 364 = ~one year ago. This matches how Whoop/Oura/Apple Health
// surface "yesterday's recovery" since the current day's score isn't ready
// until you wake up the morning after.

export const TODAY_DATE = new Date("2026-04-27T00:00:00Z");

function dayDate(idx: number): Date {
  const d = new Date(TODAY_DATE);
  d.setUTCDate(d.getUTCDate() - 1 - idx);
  return d;
}

// Deterministic LCG so every render produces the same scenario. Avoids
// Math.random() in the data path — the rhyme finder runs cross-render
// comparisons and would surface different analogues each refresh otherwise.
function makeRng(seed: number): () => number {
  let s = seed;
  return () => {
    s = (s * 9301 + 49297) % 233280;
    return s / 233280;
  };
}

// =====================================================================
// Daily summary — 365 days of multivariate biomarkers
// =====================================================================

export interface DaySummary {
  idx: number;          // 0 = yesterday, 364 = year ago
  date: Date;
  hrv: number;          // ms (RMSSD)  — typical 40-90, healthy 60-80
  rhr: number;          // bpm         — typical 50-70, athletic 45-58
  sleep: number;        // hours       — typical 6-9
  sleepScore: number;   // 0-100 pseudo Whoop "sleep performance"
  recovery: number;     // 0-100 pseudo Whoop "recovery score"
  energy: number;       // 0-100 manual self-report (subjective)
  glucose: number;      // mg/dL fasted morning
  trainingLoad: number; // 0-10 (Whoop "strain"-like)
  steps: number;        // pedometer
  weight: number;       // kg
  tag?: TagKind;        // optional context label for the day
}

export type TagKind = "normal" | "illness" | "travel" | "training" | "rest" | "alcohol";

export const TAG_META: Record<TagKind, { label: string; color: string }> = {
  normal: { label: "Normal", color: "#7a7a75" },
  illness: { label: "Illness", color: "#c2655c" },
  travel: { label: "Travel", color: "#5a7d9c" },
  training: { label: "Heavy training", color: "#5b8a72" },
  rest: { label: "Deload", color: "#c89a4a" },
  alcohol: { label: "Drinking", color: "#7d3aa9" },
};

// Tagged periods that the rhyme finder will reliably surface as analogues
// to today's window. Each spans contiguous indices.
//
// Designed so today's pattern (last 7 days, see indices 0-6) is the start
// of a "training" block and rhymes most strongly with the prior heavy
// training block at indices 60-72 — that block was followed by a brief
// illness-week (overtraining → cold), which becomes the warning the
// rhymes screen surfaces for the user.
export interface TaggedPeriod {
  startIdx: number; // inclusive (0 = yesterday)
  endIdx: number;   // inclusive (larger = older)
  tag: TagKind;
  note: string;
}

export const TAGGED_PERIODS: TaggedPeriod[] = [
  // Most recent: starting heavy training block
  { startIdx: 0, endIdx: 6, tag: "training", note: "Marathon block week 1" },
  // 2 weeks back: travel disrupted sleep + HRV
  { startIdx: 18, endIdx: 24, tag: "travel", note: "Tokyo trip" },
  // ~6 weeks back: illness — short cold knocked HRV down hard
  { startIdx: 50, endIdx: 56, tag: "illness", note: "Spring cold" },
  // ~9 weeks back: heavy training block (the analogue for today)
  { startIdx: 60, endIdx: 72, tag: "training", note: "Strength peak block" },
  // 4 months back: deload week
  { startIdx: 120, endIdx: 126, tag: "rest", note: "Mid-cycle deload" },
  // 5 months back: holidays — drinking + late nights
  { startIdx: 145, endIdx: 158, tag: "alcohol", note: "Holiday week" },
  // 8 months back: another illness flare
  { startIdx: 230, endIdx: 235, tag: "illness", note: "Flu" },
  // 10 months back: travel
  { startIdx: 290, endIdx: 297, tag: "travel", note: "Conference NYC" },
];

function tagForIdx(idx: number): TagKind | undefined {
  for (const p of TAGGED_PERIODS) {
    if (idx >= p.startIdx && idx <= p.endIdx) return p.tag;
  }
  return undefined;
}

// Build the 365-day series. Each biomarker has:
//   - a baseline ("normal" Buba: HRV~65, RHR~56, sleep~7.6h, glucose~92)
//   - a weekly cycle (lower HRV on Mondays after weekend recovery debt)
//   - a slow seasonal trend (HRV drift)
//   - a tag-driven offset (illness→HRV drops 25, RHR rises 8, etc.)
//   - small deterministic noise from the LCG
//
// The seed (137) was tuned so the rhyme finder picks out the "training peak
// block" as the strongest analogue for today's last-7-days window.
function buildDays(): DaySummary[] {
  const rng = makeRng(137);
  const out: DaySummary[] = [];
  for (let idx = 0; idx < 365; idx++) {
    const d = dayDate(idx);
    const dow = d.getUTCDay();              // 0 Sun → 6 Sat
    const tag = tagForIdx(idx);

    // Baselines
    let hrv = 65;
    let rhr = 56;
    let sleep = 7.6;
    let energy = 70;
    let glucose = 92;
    let load = 4.5;
    let steps = 8500;
    let weight = 78.5;

    // Seasonal: HRV is a touch lower in winter (idx ~180-280 ago)
    const season = Math.cos(((idx - 90) / 365) * Math.PI * 2);
    hrv += season * 4;
    rhr -= season * 2;

    // Weekly: Monday HRV dip (after weekend social / weights)
    if (dow === 1) hrv -= 4;
    if (dow === 0 || dow === 6) {
      sleep += 0.6; // weekend sleep-in
      load -= 1;
      energy += 4;
    }
    if (dow === 5 || dow === 6) glucose += 2; // weekend eating

    // Tag overlays — these are what makes the rhymes meaningful
    if (tag === "illness") {
      hrv -= 25;
      rhr += 9;
      sleep -= 0.4;
      energy -= 30;
      glucose += 3;
      load = 1;
      steps = 3500;
    } else if (tag === "travel") {
      hrv -= 12;
      rhr += 5;
      sleep -= 1.2;
      energy -= 12;
      glucose += 4;
      load -= 0.5;
      steps += 3000;
    } else if (tag === "training") {
      hrv -= 8;
      rhr += 2;
      sleep += 0.2;
      energy -= 4;
      load += 3;
      steps += 4000;
    } else if (tag === "rest") {
      hrv += 6;
      rhr -= 2;
      sleep += 0.3;
      energy += 6;
      load = 2;
    } else if (tag === "alcohol") {
      hrv -= 14;
      rhr += 6;
      sleep -= 0.6;
      energy -= 10;
      glucose += 5;
    }

    // Slow weight drift (heavier ~6 months ago, leaner now)
    weight += -0.5 + Math.sin((idx / 365) * Math.PI * 2) * 1.4;

    // Add a small amount of noise so neighboring days differ realistically
    hrv += (rng() - 0.5) * 6;
    rhr += (rng() - 0.5) * 3;
    sleep += (rng() - 0.5) * 0.6;
    energy += (rng() - 0.5) * 12;
    glucose += (rng() - 0.5) * 6;
    load += (rng() - 0.5) * 1.2;
    steps += (rng() - 0.5) * 2200;
    weight += (rng() - 0.5) * 0.3;

    // Clamp + round to display-ready precision
    hrv = clamp(Math.round(hrv), 30, 110);
    rhr = clamp(Math.round(rhr), 42, 80);
    sleep = clamp(Math.round(sleep * 10) / 10, 4, 10.5);
    energy = clamp(Math.round(energy), 0, 100);
    glucose = clamp(Math.round(glucose), 75, 130);
    load = clamp(Math.round(load * 10) / 10, 0, 10);
    steps = clamp(Math.round(steps / 100) * 100, 1500, 22000);
    weight = clamp(Math.round(weight * 10) / 10, 70, 90);

    // Sleep score = sleep duration normalized to 7.5h target with a
    // consistency bonus baked into the recovery proxy.
    const sleepScore = clamp(
      Math.round(60 + (sleep - 6) * 12 + (rng() - 0.5) * 8),
      20,
      99
    );
    // Recovery score = HRV-relative + sleep score — Whoop-ish heuristic.
    const recovery = clamp(
      Math.round((hrv - 50) * 1.6 + (sleepScore - 60) * 0.4 + 50),
      5,
      99
    );

    out.push({
      idx,
      date: d,
      hrv,
      rhr,
      sleep,
      sleepScore,
      recovery,
      energy,
      glucose,
      trainingLoad: load,
      steps,
      weight,
      tag,
    });
  }
  return out;
}

function clamp(v: number, a: number, b: number): number {
  return Math.max(a, Math.min(b, v));
}

export const DAYS: DaySummary[] = buildDays();

// Personal baselines — the "what's normal for me" reference each KPI is
// compared against. Computed as the median of the last 90 days.
function median(arr: number[]): number {
  const s = [...arr].sort((a, b) => a - b);
  const mid = Math.floor(s.length / 2);
  return s.length % 2 ? s[mid] : (s[mid - 1] + s[mid]) / 2;
}

const last90 = DAYS.slice(0, 90);
export const BASELINE = {
  hrv: median(last90.map((d) => d.hrv)),
  rhr: median(last90.map((d) => d.rhr)),
  sleep: median(last90.map((d) => d.sleep)),
  sleepScore: median(last90.map((d) => d.sleepScore)),
  recovery: median(last90.map((d) => d.recovery)),
  energy: median(last90.map((d) => d.energy)),
  glucose: median(last90.map((d) => d.glucose)),
  trainingLoad: median(last90.map((d) => d.trainingLoad)),
  steps: median(last90.map((d) => d.steps)),
  weight: median(last90.map((d) => d.weight)),
};

// =====================================================================
// Today — hourly HR series (24 readings, 1/hour)
// =====================================================================
//
// Used by the DayTrajectory chart. Three overlay options:
//   - today        — actual
//   - yesterday    — straight from DAYS[0] expanded
//   - rhyming day  — the analogue surfaced by the rhyme finder
//   - baseline     — 90-day median curve

export interface HourlyPoint {
  h: number;
  hr: number;
}

function buildHourly(seed: number, baselineHR: number, peak: number): HourlyPoint[] {
  const rng = makeRng(seed);
  return Array.from({ length: 24 }, (_, h) => {
    // Resting overnight (lowest 3-5am), morning rise, daytime activity bump,
    // evening taper.
    const tod =
      Math.cos(((h - 4) / 24) * Math.PI * 2) * -1 * 0.5 + 0.5; // 0 at 4am, 1 at 4pm
    const noise = (rng() - 0.5) * 6;
    const workout = h >= 17 && h <= 18 ? peak : 0; // evening workout spike
    return {
      h,
      hr: Math.round(baselineHR + tod * 22 + workout + noise),
    };
  });
}

export const TODAY_HOURLY = buildHourly(11, 62, 28);
export const YESTERDAY_HOURLY = buildHourly(31, 60, 18);
export const BASELINE_HOURLY = buildHourly(51, 58, 14);

// =====================================================================
// Sources — connected wearables + lab provider cards
// =====================================================================

export interface SourceCard {
  id: string;
  name: string;
  kind: "Wearable" | "CGM" | "Lab" | "App";
  connected: boolean;
  lastSync: string; // human-readable
  color: string;
  mark: string;
  channels: string[];
}

export const SOURCES: SourceCard[] = [
  {
    id: "apple-health",
    name: "Apple Health",
    kind: "App",
    connected: true,
    lastSync: "2 minutes ago",
    color: "#1a1a1a",
    mark: "ah",
    channels: ["HR", "HRV", "Steps", "Workouts", "Sleep"],
  },
  {
    id: "whoop",
    name: "Whoop 4.0",
    kind: "Wearable",
    connected: true,
    lastSync: "8 minutes ago",
    color: "#c2655c",
    mark: "WH",
    channels: ["HRV", "RHR", "Recovery", "Strain", "Sleep stages"],
  },
  {
    id: "oura",
    name: "Oura Ring",
    kind: "Wearable",
    connected: false,
    lastSync: "—",
    color: "#5a7d9c",
    mark: "O",
    channels: ["HRV", "Body temp", "Sleep stages"],
  },
  {
    id: "dexcom",
    name: "Dexcom G7",
    kind: "CGM",
    connected: true,
    lastSync: "1 minute ago",
    color: "#5b8a72",
    mark: "G7",
    channels: ["Glucose (5-min)"],
  },
  {
    id: "quest",
    name: "Quest Diagnostics",
    kind: "Lab",
    connected: true,
    lastSync: "Mar 12, 2026",
    color: "#7d3aa9",
    mark: "Q",
    channels: ["Lipids", "Metabolic", "Hormones", "Vitamins"],
  },
  {
    id: "labcorp",
    name: "LabCorp",
    kind: "Lab",
    connected: false,
    lastSync: "—",
    color: "#5a7d9c",
    mark: "L",
    channels: ["Lipids", "Metabolic"],
  },
];

// =====================================================================
// Labs — long-term biomarkers with 5 historical draws
// =====================================================================

export interface LabBiomarker {
  id: string;
  name: string;
  unit: string;
  current: number;
  baseline: number;        // user's personal baseline (rolling avg)
  optimalLow: number;      // clinical optimal range (note: NOT just "in range")
  optimalHigh: number;
  history: number[];       // 5 oldest → newest historical values
  // Direction = "lower better" or "higher better" or "in range" — drives
  // the delta-arrow color vs baseline.
  direction: "low" | "high" | "range";
  category: "metabolic" | "lipids" | "hormones" | "vitamins" | "inflammation";
}

export const LABS: LabBiomarker[] = [
  {
    id: "hba1c",
    name: "HbA1c",
    unit: "%",
    current: 5.2,
    baseline: 5.3,
    optimalLow: 4.5,
    optimalHigh: 5.4,
    history: [5.6, 5.5, 5.4, 5.3, 5.2],
    direction: "low",
    category: "metabolic",
  },
  {
    id: "ldl",
    name: "LDL",
    unit: "mg/dL",
    current: 88,
    baseline: 95,
    optimalLow: 50,
    optimalHigh: 100,
    history: [108, 102, 96, 92, 88],
    direction: "low",
    category: "lipids",
  },
  {
    id: "apob",
    name: "ApoB",
    unit: "mg/dL",
    current: 76,
    baseline: 82,
    optimalLow: 40,
    optimalHigh: 90,
    history: [92, 88, 84, 80, 76],
    direction: "low",
    category: "lipids",
  },
  {
    id: "hscrp",
    name: "hsCRP",
    unit: "mg/L",
    current: 0.4,
    baseline: 0.6,
    optimalLow: 0,
    optimalHigh: 1.0,
    history: [1.2, 0.9, 0.7, 0.5, 0.4],
    direction: "low",
    category: "inflammation",
  },
  {
    id: "vitd",
    name: "Vitamin D",
    unit: "ng/mL",
    current: 48,
    baseline: 38,
    optimalLow: 40,
    optimalHigh: 80,
    history: [22, 28, 34, 42, 48],
    direction: "high",
    category: "vitamins",
  },
  {
    id: "fglucose",
    name: "Fasting glucose",
    unit: "mg/dL",
    current: 88,
    baseline: 91,
    optimalLow: 70,
    optimalHigh: 95,
    history: [98, 95, 93, 91, 88],
    direction: "low",
    category: "metabolic",
  },
  {
    id: "test",
    name: "Total testosterone",
    unit: "ng/dL",
    current: 720,
    baseline: 680,
    optimalLow: 600,
    optimalHigh: 950,
    history: [580, 620, 650, 680, 720],
    direction: "range",
    category: "hormones",
  },
  {
    id: "b12",
    name: "Vitamin B12",
    unit: "pg/mL",
    current: 612,
    baseline: 580,
    optimalLow: 500,
    optimalHigh: 900,
    history: [510, 540, 560, 580, 612],
    direction: "high",
    category: "vitamins",
  },
  {
    id: "ferritin",
    name: "Ferritin",
    unit: "ng/mL",
    current: 145,
    baseline: 130,
    optimalLow: 100,
    optimalHigh: 300,
    history: [88, 102, 118, 130, 145],
    direction: "range",
    category: "inflammation",
  },
];

// Lab draw dates (5 historical) — most recent first.
export const LAB_DATES = [
  "2024-09-14",
  "2024-12-20",
  "2025-04-08",
  "2025-09-22",
  "2026-03-12",
];

// =====================================================================
// Log events — chronological timeline (last 7 days, ~40 events)
// =====================================================================

export type LogKind =
  | "vitals"
  | "workout"
  | "meal"
  | "sleep"
  | "mood"
  | "supplement"
  | "alcohol"
  | "stress"
  | "other";

export interface LogEvent {
  id: string;
  date: Date;
  kind: LogKind;
  title: string;
  detail: string;
  metric?: string; // small mono-typed payload (e.g. "RHR 58 · HRV 64")
  icon: string;
}

export const LOG_KIND_META: Record<LogKind, { label: string; color: string; icon: string }> = {
  vitals: { label: "Vitals", color: "#5b8a72", icon: "heart" },
  workout: { label: "Workout", color: "#c2655c", icon: "run" },
  meal: { label: "Meal", color: "#c89a4a", icon: "fork" },
  sleep: { label: "Sleep", color: "#5a7d9c", icon: "bed" },
  mood: { label: "Mood / energy", color: "#7d3aa9", icon: "zap" },
  supplement: { label: "Supplement", color: "#3d6650", icon: "pill" },
  alcohol: { label: "Alcohol", color: "#7d3aa9", icon: "glass" },
  stress: { label: "Stress event", color: "#b14a3a", icon: "flame" },
  other: { label: "Other", color: "#7a7a75", icon: "info" },
};

function logTime(daysAgo: number, hour: number, min: number): Date {
  const d = new Date(TODAY_DATE);
  d.setUTCDate(d.getUTCDate() - daysAgo);
  d.setUTCHours(hour, min, 0, 0);
  return d;
}

export const LOG_EVENTS: LogEvent[] = [
  // Today (idx 0 = today)
  { id: "l1", date: logTime(0, 6, 35), kind: "sleep", title: "Woke up", detail: "7h 22m, 87% efficiency", metric: "REM 1h22 · Deep 1h05", icon: "bed" },
  { id: "l2", date: logTime(0, 6, 40), kind: "vitals", title: "Morning readings", detail: "HRV 64ms, RHR 58", metric: "HRV 64 · RHR 58", icon: "heart" },
  { id: "l3", date: logTime(0, 7, 5), kind: "supplement", title: "AM stack", detail: "D3 5000IU · Magnesium 400mg · Omega-3 2g", icon: "pill" },
  { id: "l4", date: logTime(0, 7, 30), kind: "meal", title: "Breakfast", detail: "3-egg omelette, oats, blueberries", metric: "~520 kcal · 32g P", icon: "fork" },
  { id: "l5", date: logTime(0, 9, 15), kind: "workout", title: "Easy Z2 run", detail: "8 km · avg 5:42/km · HR avg 142", metric: "Strain 5.8/10", icon: "run" },
  { id: "l6", date: logTime(0, 13, 20), kind: "meal", title: "Lunch", detail: "Chicken, quinoa, greens", metric: "~640 kcal · 48g P", icon: "fork" },
  { id: "l7", date: logTime(0, 15, 30), kind: "mood", title: "Energy check-in", detail: "7/10, mild post-lunch dip", icon: "zap" },

  // Yesterday
  { id: "l8", date: logTime(1, 6, 12), kind: "sleep", title: "Woke up", detail: "7h 48m, 91% efficiency", metric: "REM 1h35 · Deep 1h12", icon: "bed" },
  { id: "l9", date: logTime(1, 6, 20), kind: "vitals", title: "Morning readings", detail: "HRV 68ms, RHR 56", metric: "HRV 68 · RHR 56", icon: "heart" },
  { id: "l10", date: logTime(1, 17, 30), kind: "workout", title: "Tempo intervals", detail: "6 × 800m @ 4:30/km, 90s rest", metric: "Strain 14.2/10", icon: "run" },
  { id: "l11", date: logTime(1, 19, 0), kind: "meal", title: "Dinner", detail: "Salmon, sweet potato, kale", metric: "~720 kcal · 52g P", icon: "fork" },
  { id: "l12", date: logTime(1, 22, 15), kind: "mood", title: "Pre-bed", detail: "Tired but satisfied, 6/10 stress", icon: "zap" },

  // 2 days ago
  { id: "l13", date: logTime(2, 6, 45), kind: "sleep", title: "Woke up", detail: "8h 02m, 89% efficiency", metric: "REM 1h41 · Deep 1h22", icon: "bed" },
  { id: "l14", date: logTime(2, 12, 30), kind: "stress", title: "Stressful client call", detail: "HR spiked to 98 at rest", icon: "flame" },
  { id: "l15", date: logTime(2, 18, 15), kind: "workout", title: "Strength: lower", detail: "Squat 5×5 @ 110kg, RDL 4×8 @ 80kg", metric: "Strain 12.4/10", icon: "run" },
  { id: "l16", date: logTime(2, 20, 30), kind: "meal", title: "Dinner", detail: "Steak, rice, broccoli", metric: "~880 kcal · 58g P", icon: "fork" },

  // 3 days ago
  { id: "l17", date: logTime(3, 6, 50), kind: "vitals", title: "Morning readings", detail: "HRV 72ms, RHR 54 — best in 2 weeks", metric: "HRV 72 · RHR 54", icon: "heart" },
  { id: "l18", date: logTime(3, 9, 0), kind: "workout", title: "Yoga + mobility", detail: "45 min flow + 15 min foam roll", metric: "Strain 4.1/10", icon: "run" },
  { id: "l19", date: logTime(3, 19, 30), kind: "alcohol", title: "Wine with dinner", detail: "1 glass red", icon: "glass" },

  // 4 days ago
  { id: "l20", date: logTime(4, 6, 15), kind: "sleep", title: "Woke up", detail: "6h 51m, 78% efficiency — disrupted", metric: "REM 1h12 · Deep 0h54", icon: "bed" },
  { id: "l21", date: logTime(4, 17, 0), kind: "workout", title: "Long run", detail: "21 km · 5:35/km avg · last fueled Z2", metric: "Strain 17.8/10", icon: "run" },
  { id: "l22", date: logTime(4, 21, 30), kind: "meal", title: "Recovery dinner", detail: "Pasta, chicken, parmesan", metric: "~950 kcal · 55g P", icon: "fork" },

  // 5 days ago
  { id: "l23", date: logTime(5, 7, 0), kind: "vitals", title: "Morning readings", detail: "HRV 60ms, RHR 60", metric: "HRV 60 · RHR 60", icon: "heart" },
  { id: "l24", date: logTime(5, 8, 30), kind: "supplement", title: "AM stack", detail: "D3, Mg, Omega-3 + creatine 5g", icon: "pill" },
  { id: "l25", date: logTime(5, 18, 0), kind: "workout", title: "Strength: upper", detail: "Bench 5×5 @ 92kg, pull-ups 5×6", metric: "Strain 11.1/10", icon: "run" },

  // 6 days ago
  { id: "l26", date: logTime(6, 6, 30), kind: "sleep", title: "Woke up", detail: "7h 38m, 88% efficiency", metric: "REM 1h28 · Deep 1h14", icon: "bed" },
  { id: "l27", date: logTime(6, 12, 0), kind: "meal", title: "Lunch out", detail: "Burrito bowl", metric: "~780 kcal · 42g P", icon: "fork" },
  { id: "l28", date: logTime(6, 14, 30), kind: "mood", title: "Mid-day energy", detail: "8/10, sharp focus", icon: "zap" },
];

// =====================================================================
// Simple format helpers
// =====================================================================

export const FMT = {
  signed: (n: number, opts: { unit?: string; digits?: number } = {}): string => {
    const { unit = "", digits = 0 } = opts;
    const sgn = n > 0 ? "+" : n < 0 ? "" : ""; // negative carries its own minus
    return `${sgn}${n.toFixed(digits)}${unit}`;
  },
  pct: (n: number): string =>
    `${(n * 100).toFixed(0)}%`,
  shortDate: (d: Date): string =>
    d.toLocaleDateString("en-US", { month: "short", day: "numeric" }),
  longDate: (d: Date): string =>
    d.toLocaleDateString("en-US", {
      weekday: "short",
      month: "long",
      day: "numeric",
    }),
  time: (d: Date): string =>
    d.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" }),
};
