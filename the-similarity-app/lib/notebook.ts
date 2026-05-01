/**
 * Notebook — durable per-user list of free-text observations the workstation
 * user attaches to a query window.
 *
 * Why this exists
 * ---------------
 * The workstation's left rail historically rendered a hardcoded "Nine lenses
 * agree…" prose paragraph. Decorative, never updated, the same words for
 * every dataset. A workstation that demands attention has to let the user
 * *write* — observations they wrote yesterday should be visible today, with
 * one click to restore the dataset + window they wrote them against. This
 * module is the persistence half of that loop.
 *
 * Storage
 * -------
 * localStorage under the key {@link STORAGE_KEY}. The full list is kept as
 * a single JSON array because:
 *   1. The list is bounded by {@link MAX_ENTRIES}, so re-serializing on
 *      every write is O(small) — no need for an indexed scheme.
 *   2. A single key makes the "I cleared notebook" UX a one-liner
 *      (`localStorage.removeItem(STORAGE_KEY)`), and gives us atomic
 *      replace semantics on each write.
 *
 * Failure mode
 * ------------
 * Every read/write is wrapped in try/catch and falls back to an empty list
 * or a no-op. localStorage can throw in incognito mode, when quota is
 * exceeded, or when accessed from a non-browser environment (SSR). The
 * workstation must never crash because the notebook couldn't be persisted —
 * losing a single entry is acceptable; an unmounted page is not.
 *
 * Capacity
 * --------
 * Capped at {@link MAX_ENTRIES} entries (newest first). Adding past the cap
 * trims the tail. This bounds storage growth and keeps the rendered list
 * O(small). Users with more entries than this should be querying a real
 * backend — the localStorage notebook is the workbench, not the archive.
 */

/** localStorage key. Single bucket because the entry list is bounded. */
export const STORAGE_KEY = "ts-notebook";

/**
 * Soft cap on how many notebook entries we keep in localStorage. Adding
 * past the cap trims the OLDEST entries (preserving newest-first order in
 * {@link listEntries}). 200 is roughly a year of one-per-trading-day notes
 * for the single-user workbench, well under the 5MB localStorage budget.
 */
export const MAX_ENTRIES = 200;

/**
 * One notebook entry. The {@link dataset}/{@link windowStart}/
 * {@link windowEnd} triple is the **restore key** — clicking the entry in
 * the UI rehydrates the workstation's active dataset and query window so
 * the user is back at exactly the moment they wrote the note.
 *
 * `windowStart`/`windowEnd` are integer bar indices (matching
 * `windowState.start` and `windowState.start + windowState.len` in
 * `components/workstation/workstation.tsx`). They are NOT date strings —
 * date semantics belong to the loaded series, which the workstation owns.
 */
export interface NotebookEntry {
  /** Stable id — `nb-<epoch-ms>-<base36 4-char suffix>`, generated client-side. */
  id: string;
  /** Wall-clock UTC ISO timestamp of when the entry was created. */
  ts: string;
  /** The actual note text. Trimmed; empty/whitespace-only entries are rejected by {@link addEntry}. */
  text: string;
  /** Dataset descriptor (e.g. `"stocks/spy/1d"`). May be empty when no dataset is loaded. */
  dataset: string;
  /** Inclusive bar index of the query window's left edge. */
  windowStart: number;
  /** Exclusive bar index of the query window's right edge (i.e. start + len). */
  windowEnd: number;
}

/**
 * Generate an id for a new entry. Format mirrors `newGoodrunId()` so the
 * two persistence layers feel consistent in the inspector. The base36
 * suffix is enough to disambiguate concurrent saves at sub-millisecond
 * resolution (collision probability: ~1 / 1.6M per millisecond).
 */
export function newEntryId(): string {
  const ms = Date.now();
  const rand = Math.floor(Math.random() * 36 ** 4)
    .toString(36)
    .padStart(4, "0");
  return `nb-${ms}-${rand}`;
}

/**
 * Read the persisted entry list. Newest-first. Returns `[]` for any
 * failure (SSR, missing key, malformed JSON, non-array shape). The
 * workstation treats this as the source of truth for its left-rail
 * notebook panel, so silent fallback is correct: an unreadable list
 * surfaces as "no entries yet," not as a crash.
 */
export function listEntries(): NotebookEntry[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    // Defensive: drop entries missing required fields rather than throwing.
    // A single corrupted entry should not nuke the whole list.
    return parsed.filter(isEntry);
  } catch {
    return [];
  }
}

/**
 * Append a new entry and return the trimmed, newest-first list. The
 * input is normalized: {@link NotebookEntry.text} is trimmed; the entry
 * is rejected (function returns the existing list unchanged) when text
 * is empty after trimming.
 *
 * Capacity: if adding the entry would exceed {@link MAX_ENTRIES}, the
 * oldest entries are dropped. The cap is a soft contract — callers do
 * NOT need to check size beforehand.
 */
export function addEntry(input: {
  text: string;
  dataset: string;
  windowStart: number;
  windowEnd: number;
}): NotebookEntry[] {
  const text = input.text.trim();
  if (!text) return listEntries();
  const entry: NotebookEntry = {
    id: newEntryId(),
    ts: new Date().toISOString(),
    text,
    dataset: input.dataset,
    windowStart: input.windowStart | 0,
    windowEnd: input.windowEnd | 0,
  };
  const next = [entry, ...listEntries()].slice(0, MAX_ENTRIES);
  writeAll(next);
  return next;
}

/**
 * Remove a single entry by id and return the resulting list (newest
 * first). No-op when the id isn't found.
 */
export function removeEntry(id: string): NotebookEntry[] {
  const next = listEntries().filter((e) => e.id !== id);
  writeAll(next);
  return next;
}

/**
 * Replace the entire list. Exposed for the rare case a caller wants to
 * batch-delete or import from a backup; the workstation itself only ever
 * uses {@link addEntry} / {@link removeEntry}.
 */
export function writeAll(entries: NotebookEntry[]): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(entries));
  } catch {
    // Quota / disabled / private mode — accept the loss.
  }
}

// ── Internals ─────────────────────────────────────────────────────────

/**
 * Type-guard for a parsed JSON record matching {@link NotebookEntry}.
 * Used to filter out corrupted persisted entries on read.
 */
function isEntry(v: unknown): v is NotebookEntry {
  if (!v || typeof v !== "object") return false;
  const o = v as Record<string, unknown>;
  return (
    typeof o.id === "string" &&
    typeof o.ts === "string" &&
    typeof o.text === "string" &&
    typeof o.dataset === "string" &&
    typeof o.windowStart === "number" &&
    typeof o.windowEnd === "number"
  );
}
