/**
 * Cadence — demo seed data generator.
 *
 * Writes 14 days of hand-crafted journal entries into localStorage so a
 * first-time visitor (typically an investor walking through the product)
 * can see the full experience on first click: heatmap, rhymes, patterns,
 * sparklines all populated, no empty states.
 *
 * ──────────────────────────────────────────────────────────────────────
 * Design contract
 * ──────────────────────────────────────────────────────────────────────
 *
 * The seed MUST produce entries whose derived views are immediately
 * impressive:
 *
 *   1. `/cadence` (Today) — ThreadRibbon shows 14 dots with varied avgs;
 *      heatmap shows diverse intensity; KeyMetrics compute real values.
 *   2. `/cadence/rhymes` — the similarity detector finds at least one
 *      rhyming pair. We engineer this by writing day 3 and day 10
 *      narratives that share the same event skeleton (rough morning →
 *      midday lift → productive afternoon → quiet evening) so the
 *      z-normalized RMSE over shape matches.
 *   3. `/cadence/patterns` — with 14 entries spread across valence
 *      ranges, every pattern card (best-day, worst-day, tag frequency,
 *      day-of-week, time-of-day, volatility) has enough signal to
 *      populate.
 *
 * ──────────────────────────────────────────────────────────────────────
 * Lifecycle and invariants
 * ──────────────────────────────────────────────────────────────────────
 *
 *  - This module is browser-only. `seedDemoEntries()` is a no-op when
 *    `window` / `localStorage` is unavailable — the storage helpers in
 *    `../storage.ts` degrade gracefully so the caller never crashes.
 *  - `seedDemoEntries()` is idempotent: each entry carries a deterministic
 *    `id` (`demo-seed-${i}`) and `saveEntry()` upserts by id, so calling
 *    the function twice leaves the journal in the same shape. Real user
 *    entries (any id not starting with `demo-seed-`) are preserved.
 *  - `createdAt` ISO strings are computed from `Date.now() - i * 86400000`
 *    with an hour-of-day in [21, 23] so sparkline / time-of-day patterns
 *    show a realistic evening-logging cadence.
 *  - The narratives are intentionally verbose (5–8 sentences each) so
 *    `parseNarrative()` generates enough Events for every pattern card to
 *    render non-trivially.
 *
 * ──────────────────────────────────────────────────────────────────────
 * How to extend
 * ──────────────────────────────────────────────────────────────────────
 *
 *  - To add a new day, append to `DEMO_NARRATIVES` and bump the constant
 *    used in the day loop. Keep the 14-entry default so the heatmap
 *    (7-day × 12-hour grid in today-view) is fully populated.
 *  - To tune rhyme strength, edit the day-3 and day-10 narratives; keep
 *    their event ordering (low → rise → high → quiet) mirrored so
 *    `findRhyme()` produces a tight match.
 */

import { parseNarrative } from "../engine";
import { saveEntry, type StoredEntry } from "../storage";

// ──────────────────────────────────────────────────────────────────────
// Narrative pool
// ──────────────────────────────────────────────────────────────────────
//
// Index 0 is "today" (day === 0). Index 13 is "two weeks ago" (day === 13).
// Each entry is 5–8 sentences and leans on words present in the parser
// lexicon (engine.ts) so the series has genuine ups, downs, and tags.
//
// ~ Structural rhyme engineered into indices 3 and 10 ~
// Both narratives follow the arc: rough morning → midday walk → friend
// reunion → flow afternoon → calm evening. This produces a low→high→flat
// shape that the z-normalized RMSE matcher in engine.ts#findRhyme picks
// up as a tight rhyme. Don't re-order these without re-testing the
// Rhymes page.
const DEMO_NARRATIVES: readonly string[] = [
  // day 0 (today) — calm productive day
  "Woke up clear and had a quiet morning with coffee. Standup was short and focused. Spent the afternoon in flow, the code finally clicked. Went for a long walk before dinner. Evening was peaceful with a book.",

  // day 1 (yesterday) — rough Monday commute
  "Monday hit hard. Rough commute, the subway was packed and late. Morning meeting dragged and I felt drained afterward. Lunch was okay but I was still sluggish. Powered through emails in the afternoon. Ordered dinner in and slept early.",

  // day 2 — Tuesday flow state
  "Great morning run before work. Flow state all morning, breakthrough on the refactor. Lunch with a friend, we laughed about old stories. Afternoon was productive but tiring. Calm dinner, read a little before bed.",

  // day 3 — STRUCTURAL TWIN of day 10 (rough → walk → friend → flow → calm)
  "Woke up heavy and anxious about the deadline. Morning was rough, emails piled up before coffee. Around noon I went for a walk in the park and things started to lift. Ran into a friend who'd just moved back, we laughed for twenty minutes. The afternoon clicked and I got into a flow. Dinner was calm, read before bed.",

  // day 4 — friend reunion Thursday
  "Tired start but the weather was nice. Productive morning clearing my inbox. Had lunch with my sister, she texted me after and we kept laughing. Afternoon was flat but fine. Went to a friend's birthday dinner, felt genuinely happy. Walked home slow.",

  // day 5 — long walk Friday
  "Slow Friday morning, coffee and a book. Work was light, just a review and a short meeting. Long walk through the city after lunch, felt really good. Nap in the afternoon. Quiet evening, watched a film and ate leftovers. Happy to have a peaceful night.",

  // day 6 — low energy Saturday
  "Woke up tired, kind of sad for no reason. Stayed in bed too long. Tried to read but felt flat. Forced a walk in the afternoon, it helped a little. Evening was lonely, didn't talk to anyone. Slept early hoping tomorrow is better.",

  // day 7 — rebound Sunday
  "Better morning. Made a real breakfast and sat with it. Called mom, we talked for an hour. Afternoon was productive, cleaned the apartment. Cooked a proper dinner and felt calm. Evening walk under the streetlights, peaceful.",

  // day 8 — anxious Wednesday
  "Anxious all morning about the review. Couldn't focus, kept refreshing email. The meeting itself was fine but I was drained after. Skipped lunch which made it worse. Forced myself to the gym, felt a little better. Quiet dinner alone.",

  // day 9 — breakthrough day
  "Focused morning, the problem finally cracked open. Excited about the results, energy was high all day. Lunch with the team, lots of laughing. Kept the momentum into the afternoon, shipped the feature. Dinner was a celebration, felt alive. Great sleep.",

  // day 10 — STRUCTURAL TWIN of day 3 (rough → walk → friend → flow → calm)
  "Woke up heavy and worried about the week ahead. Morning was hard, too much on my plate before coffee. Around midday I went for a walk by the river and my mood started to lift. Met a friend for coffee, we laughed about nothing and it helped a lot. Afternoon finally clicked, got into real flow on the draft. Peaceful dinner, read in bed.",

  // day 11 — flat Tuesday
  "Okay morning, nothing special. Meetings back to back, felt bored. Lunch was meh. Afternoon dragged, couldn't get started on anything real. Evening was flat but not bad. Read a little and went to bed.",

  // day 12 — rough Monday
  "Terrible start, woke up exhausted. Commute was miserable, rain and delays. Standup was tense, the project is behind. Grinded through emails feeling drained. Skipped the gym, napped instead. Dinner was quiet, went to bed early.",

  // day 13 — mixed two weeks ago
  "Morning started slow but picked up after coffee. Productive meeting in the afternoon, felt good about it. Walked home through the park, the light was beautiful. Friend called, we talked for an hour. Cooked a good dinner. Happy, calm night.",
];

// ──────────────────────────────────────────────────────────────────────
// Timing helpers
// ──────────────────────────────────────────────────────────────────────
//
// Investors expect a realistic "evening journaling" cadence — not entries
// logged at 3am. We spread the hours across the 21:00–23:00 window using
// a cheap deterministic modulo so sparklines and time-of-day patterns
// show a plausible cluster rather than a single repeated timestamp.
function eveningHourForIndex(i: number): number {
  return 21 + (i % 3); // 21, 22, or 23
}
function evenMinuteForIndex(i: number): number {
  // Spread minutes across the hour so two consecutive days don't overlap
  // to the minute. 7 is coprime with 60 → full cycle over many days.
  return (i * 7) % 60;
}

/**
 * Build a single StoredEntry for the given days-ago offset.
 *
 * `daysAgo` MUST be in [0, DEMO_NARRATIVES.length). The function parses
 * the narrative synchronously through `parseNarrative()` so the saved
 * entry carries the full `events` + `series` payload — matching what a
 * real user entry would contain.
 */
function buildDemoEntry(daysAgo: number): StoredEntry {
  const narrative = DEMO_NARRATIVES[daysAgo];
  const parsed = parseNarrative(narrative);

  // Compute a realistic createdAt. `Date.now()` anchors to the current
  // wall clock; subtracting whole-day millis lands us on the same
  // wall-clock hour N days ago, which we then override to a 21–23 hour
  // to simulate end-of-day journaling.
  const base = new Date(Date.now() - daysAgo * 86_400_000);
  base.setHours(eveningHourForIndex(daysAgo), evenMinuteForIndex(daysAgo), 0, 0);
  const createdAt = base.toISOString();

  // Avg over series — mirrors what today-view computes for live parse.
  const avg =
    parsed.series.length > 0
      ? parsed.series.reduce((a, p) => a + p.v, 0) / parsed.series.length
      : 50;

  return {
    // Deterministic id so repeated calls upsert rather than duplicate.
    id: `demo-seed-${daysAgo}`,
    createdAt,
    day: daysAgo,
    text: narrative,
    events: parsed.events,
    series: parsed.series,
    avg,
  };
}

/**
 * Seed 14 days of demo journal entries into localStorage.
 *
 * Safe to call multiple times — existing `demo-seed-*` ids are replaced
 * in place and user-created entries (any id not matching that prefix)
 * are preserved by `saveEntry()`'s upsert semantics.
 *
 * Caller is expected to follow up with `reloadEntries()` from the engine
 * context so the in-memory state reflects the new storage contents.
 */
export function seedDemoEntries(): void {
  // Iterate newest → oldest so the final sort in loadEntries() (newest
  // first by createdAt) is stable from the first read.
  for (let i = 0; i < DEMO_NARRATIVES.length; i++) {
    saveEntry(buildDemoEntry(i));
  }
}

/**
 * Exported for tests or debugging surfaces that want to inspect the
 * narratives without touching storage.
 */
export const DEMO_NARRATIVE_COUNT = DEMO_NARRATIVES.length;
