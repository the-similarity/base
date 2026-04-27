/**
 * Cadence — localStorage persistence layer for journal entries.
 *
 * This module provides CRUD helpers for the personal valence journal that
 * Cadence produces. Each entry captures a single "log" by the user: the
 * raw text they typed, the events/series produced by the parser, a human
 * day-index (days-ago at time-of-log), and the computed average for that
 * entry. Entries are stored in `localStorage` under a versioned key so
 * the schema can evolve without wiping existing data.
 *
 * Invariants / lifecycle:
 *   - Storage is browser-only. Every read/write guards with a
 *     `typeof window !== 'undefined'` check so Next.js SSR / route
 *     handlers / static prerender never crash. In server contexts the
 *     helpers degrade gracefully to a no-op (reads return [], writes
 *     silently drop).
 *   - `loadEntries()` returns entries sorted by `createdAt` DESC (newest
 *     first). This matches how a "journal" is naturally consumed.
 *   - Entries are kept forever — we never auto-prune — but callers can
 *     use the `day` field (days-ago at log time) to decide what to show.
 *     A consumer that wants "last 30 days" can filter client-side.
 *   - The storage key is namespaced (`cadence:entries:v1`) so a future
 *     schema migration can read the old key, transform, and write under
 *     `v2` without data loss.
 *   - Serialization is JSON. Malformed stored data (e.g. user tampered
 *     with devtools) is swallowed and treated as an empty list; we never
 *     throw out of the public API.
 *
 * Consumers:
 *   - Dashboard will call `saveEntry()` when the user commits a log.
 *   - Nav "Export" button will call `exportEntriesAsJSON()` to produce
 *     a download payload.
 *   - `buildHistoryFromEntries()` bridges real entries to the
 *     `HistoryDay[]` shape that `engine.ts#buildHistory` produces, so a
 *     30-day ribbon can switch from synthetic to real data once the
 *     user has enough entries logged.
 */

import type { Event, Point, HistoryDay } from "./engine";
import { buildHistory } from "./engine";

// Storage key is versioned so we can evolve the entry schema without
// silently corrupting or dropping user data. Bump the suffix (v1 → v2)
// when the `StoredEntry` shape changes in a breaking way and add a
// migration path that reads the old key.
const STORAGE_KEY = "cadence:entries:v1";

/**
 * A single persisted journal entry.
 *
 * `id` is an opaque string; callers should treat it as unique but not
 * parse it. The `entry-${Date.now()}-${rand}` construction is used so
 * entries created in the same millisecond still disambiguate.
 *
 * `day` is the "days-ago" index at the time the entry was logged. An
 * entry logged today has `day === 0`; a log made "three days back" has
 * `day === 3`. This is NOT adjusted as real time passes — we intentionally
 * freeze the user's perception at log time, because that's what they
 * wrote the narrative about. A consumer that wants a calendar-aligned
 * view should recompute from `createdAt`.
 *
 * `series` carries the full 193-step series so history rendering does
 * not need to re-parse.
 */
export interface StoredEntry {
  /** Opaque unique id. Not guaranteed to be lexicographically ordered. */
  id: string;
  /** ISO 8601 timestamp of when the entry was persisted. */
  createdAt: string;
  /** Days-ago index at log time. 0 = today, 1 = yesterday, etc. */
  day: number;
  /** Raw narrative text the user typed. */
  text: string;
  /** Parsed events from the narrative. */
  events: Event[];
  /** 193-step valence series integrated from the events. */
  series: Point[];
  /** Average valence for the series; pre-computed for ribbon rendering. */
  avg: number;
}

/**
 * Internal helper — returns true when running in a browser context that
 * exposes `localStorage`. Node / SSR contexts fail the `window` guard;
 * sandboxed iframes and some privacy-mode browsers throw when
 * `localStorage` is accessed, so we additionally try/catch.
 */
function hasStorage(): boolean {
  if (typeof window === "undefined") return false;
  try {
    // Touching the property is enough; some browsers throw on read in
    // strict privacy modes.
    return typeof window.localStorage !== "undefined";
  } catch {
    return false;
  }
}

/**
 * Read all entries from localStorage, sorted newest-first.
 *
 * Returns an empty array on SSR, when storage is unavailable, when no
 * entries have been saved, or when the stored payload is malformed.
 * Never throws.
 */
export function loadEntries(): StoredEntry[] {
  if (!hasStorage()) return [];
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    // Defensive filter: drop anything that doesn't look like a
    // StoredEntry, so a partial schema migration can't crash the UI.
    const entries = parsed.filter(
      (e): e is StoredEntry =>
        e &&
        typeof e === "object" &&
        typeof e.id === "string" &&
        typeof e.createdAt === "string" &&
        typeof e.day === "number" &&
        typeof e.text === "string" &&
        Array.isArray(e.events) &&
        Array.isArray(e.series) &&
        typeof e.avg === "number",
    );
    // Sort by createdAt DESC. Lexicographic compare is sufficient for
    // ISO 8601 strings. Newer entries bubble to the front.
    entries.sort((a, b) => (a.createdAt < b.createdAt ? 1 : a.createdAt > b.createdAt ? -1 : 0));
    return entries;
  } catch {
    // Corrupt JSON, quota error, etc. — treat as empty.
    return [];
  }
}

/**
 * Persist a single entry. If an entry with the same `id` already exists
 * it is replaced (upsert semantics). No-op when storage is unavailable.
 *
 * This is idempotent on `id` so a caller that accidentally double-saves
 * doesn't duplicate the journal.
 */
export function saveEntry(entry: StoredEntry): void {
  if (!hasStorage()) return;
  try {
    const current = loadEntries();
    // Upsert by id. We drop any existing record with the same id, then
    // prepend the new one. The final sort happens on the next load.
    const next = [entry, ...current.filter((e) => e.id !== entry.id)];
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
  } catch {
    // QuotaExceededError or private-mode storage: swallow. The user's
    // in-memory state is still valid; we just can't persist.
  }
}

/**
 * Wipe every persisted entry. Used by a "clear history" affordance.
 * No-op when storage is unavailable. Never throws.
 */
export function clearEntries(): void {
  if (!hasStorage()) return;
  try {
    window.localStorage.removeItem(STORAGE_KEY);
  } catch {
    // Intentionally silent — nothing to surface for a clear op.
  }
}

/**
 * Serialize the full journal to a JSON string suitable for download.
 *
 * The output is stable (sorted newest-first by `createdAt`) and
 * pretty-printed so users can open the file in a text editor without a
 * JSON formatter. Returns `"[]"` when there are no entries.
 */
export function exportEntriesAsJSON(): string {
  const entries = loadEntries();
  return JSON.stringify(entries, null, 2);
}

/**
 * Bridge real entries into the `HistoryDay[]` shape used by
 * `engine.ts#buildHistory`.
 *
 * When the user has accumulated at least 7 real entries, we return
 * those as a real history (with `day` = days-ago at log time). Below
 * that threshold we fall back to the synthetic ribbon so the UI never
 * shows an obviously-empty chart during onboarding.
 *
 * `syntheticFallback` is the average valence to seed the synthetic
 * history with — typically the average of today's in-progress entry.
 *
 * The 7-entry threshold is a product choice: with fewer entries the
 * ribbon would be sparse and uninformative; once the user has a week
 * of data the real signal becomes more interesting than the fake one.
 */
export function buildHistoryFromEntries(
  entries: StoredEntry[],
  syntheticFallback: number,
): HistoryDay[] {
  // Threshold below which the ribbon would be too sparse to be
  // meaningful. Product decision — bump up for a stricter bar.
  const MIN_REAL_ENTRIES = 7;
  if (!entries || entries.length < MIN_REAL_ENTRIES) {
    return buildHistory(syntheticFallback);
  }
  // Map each stored entry to the HistoryDay shape. `day` is days-ago
  // at log time, which is exactly the shape `findRhyme` / history
  // rendering expects.
  return entries.map((e) => ({
    day: e.day,
    avg: Math.round(e.avg),
    text: e.text,
  }));
}
