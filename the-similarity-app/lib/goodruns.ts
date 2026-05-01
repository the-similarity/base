/**
 * Goodruns client — thin wrappers over the FastAPI ``/goodruns`` surface.
 *
 * A "goodrun" is a curated query-window ↔ match-window pair that the
 * user explicitly saves from the AnalogDetailDrawer. The backend stores
 * the full raw ``ScoreBreakdown`` (engine math-names like ``dtw``,
 * ``pearsonWarped``, ``bempedelisR2``) alongside both price windows so
 * later sessions can surface the record with faithful lens labels.
 *
 * Responsibility split
 * --------------------
 * - This module ONLY serializes / deserializes the wire shape and
 *   performs the HTTP call. It does not know about the drawer's state,
 *   the workstation's settings, or the dataset descriptor — callers
 *   assemble the payload.
 * - All functions return plain promises. Errors surface as thrown
 *   ``Error`` instances whose ``message`` carries the server's detail
 *   string when available; callers handle UI state (toasts, retry).
 */

import type { ScoreBreakdownRaw } from "./data";
import { normalizeApiBaseUrl, resolveApiBaseUrl } from "./api-base";

export type GoodrunLabel = "goodrun" | "almost_good" | "badrun";

/**
 * Strip a trailing slash so callers can safely concatenate
 * ``normalize(base) + "/goodruns"`` without producing a double slash.
 * Mirrors the helper in ``./api.ts`` — kept local to avoid widening
 * that module's public surface just for a two-line util.
 */
function normalize(value: string): string {
  return normalizeApiBaseUrl(value);
}

/**
 * A single bar-indexed window. Mirrors the ``GoodrunWindow`` pydantic
 * model on the backend. ``values`` is the raw price series for the
 * window — not log returns, not normalized.
 */
export interface GoodrunWindow {
  start_idx: number;
  end_idx: number;
  start_date: string | null;
  end_date: string | null;
  values: number[];
}

/**
 * Wire shape of a stored goodrun record. Returned by GET endpoints and
 * by the POST endpoint on successful creation.
 */
export interface GoodrunRecord {
  id: string;
  saved_at: string;
  dataset: string;
  horizon: number;
  query: GoodrunWindow;
  match_id: string;
  match: GoodrunWindow;
  match_after_values: number[];
  lens_breakdown: ScoreBreakdownRaw;
  composite: number | null;
  note: string | null;
}

/**
 * POST body for ``/goodruns``. ``id`` is client-supplied so retries are
 * idempotent — callers generate a ULID-ish ``goodrun-<ms>-<suffix>``
 * and reuse it across fetch retries for the same save action.
 */
export interface GoodrunCreatePayload {
  id: string;
  dataset: string;
  horizon: number;
  query: GoodrunWindow;
  match_id: string;
  match: GoodrunWindow;
  match_after_values: number[];
  lens_breakdown: ScoreBreakdownRaw;
  composite: number | null;
  note: string | null;
}

/**
 * Parse an HTTP error body for its ``detail`` field, falling back to
 * the status text when the response is not JSON.
 */
async function extractErrorMessage(res: Response): Promise<string> {
  try {
    const body = await res.json();
    if (body && typeof body.detail === "string") return body.detail;
  } catch {
    // fall through to status text
  }
  return `${res.status} ${res.statusText}`;
}

/**
 * Save a goodrun. Rejects when the API is not configured or returns a
 * non-2xx status. Callers must ensure the backend is reachable; this
 * wrapper does not gracefully degrade to a local fallback because
 * persistence IS the feature.
 */
export async function saveGoodrun(
  payload: GoodrunCreatePayload,
  signal?: AbortSignal,
): Promise<GoodrunRecord> {
  const apiBaseUrl = resolveApiBaseUrl();
  if (!apiBaseUrl) {
    throw new Error("API base URL not configured — cannot save goodrun");
  }
  const res = await fetch(`${normalize(apiBaseUrl)}/goodruns`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
    signal,
  });
  if (!res.ok) {
    throw new Error(await extractErrorMessage(res));
  }
  return (await res.json()) as GoodrunRecord;
}

/**
 * List goodruns, newest first. ``dataset`` filters to a single source
 * (e.g. ``stocks/spy/1d``). Returns [] when the API is unreachable so
 * callers can render an "offline" empty state instead of crashing.
 */
export async function listGoodruns(
  options: { dataset?: string; limit?: number; signal?: AbortSignal } = {},
): Promise<GoodrunRecord[]> {
  const apiBaseUrl = resolveApiBaseUrl();
  if (!apiBaseUrl) return [];
  const params = new URLSearchParams();
  if (options.dataset) params.set("dataset", options.dataset);
  if (options.limit) params.set("limit", String(options.limit));
  const qs = params.toString() ? `?${params.toString()}` : "";
  try {
    const res = await fetch(`${normalize(apiBaseUrl)}/goodruns${qs}`, {
      signal: options.signal,
    });
    if (!res.ok) return [];
    return (await res.json()) as GoodrunRecord[];
  } catch {
    return [];
  }
}

/**
 * Generate a client-side id for a new goodrun. Monotonically increasing
 * by timestamp with a short random suffix so concurrent saves don't
 * collide. Format: ``goodrun-<epoch-ms>-<base36 4-char suffix>``.
 */
export function newGoodrunId(): string {
  const ms = Date.now();
  const rand = Math.floor(Math.random() * 36 ** 4).toString(36).padStart(4, "0");
  return `goodrun-${ms}-${rand}`;
}

// ── Local mirror ──────────────────────────────────────────────────────
//
// Why a local mirror exists
// -------------------------
// The workstation's "Saved runs" left-rail panel needs the user's history
// of saved runs to be present immediately on mount, even when the API is
// offline (which is the demo-mode default for many deploys). Hitting
// ``listGoodruns()`` on every mount is fine when the API is up but
// produces an empty rail for any client without a configured backend —
// the artifact loop ("save run, see it again tomorrow") collapses.
//
// The mirror writes a copy of every successful save into localStorage,
// so the rail can render history offline. When the API is online,
// callers merge API + local with API winning on id collisions (the
// API record is the source of truth for shape; the local copy is just
// an opportunistic cache).
//
// What's stored
// -------------
// The mirror persists the full {@link GoodrunRecord} returned by the
// server (so we never have to reconstruct ``saved_at``, ``composite``,
// ``lens_breakdown``, etc.). Single-user assumption: no per-user keying.
// If we add multi-user later, the storage key takes a userId suffix.
//
// Failure mode
// ------------
// All localStorage access is try/catch — quota / SSR / private mode all
// degrade silently. The mirror is opportunistic; losing it is acceptable
// because the API is the durable record. The workstation's UI must work
// with mirror = [].

/** localStorage key for the mirror. Single bucket for the whole list. */
export const GOODRUNS_LOCAL_KEY = "ts-goodruns-local";

/**
 * Soft cap on cached records. Older entries trim first. This is a
 * cache, not the durable store, so a low cap is fine — clients with
 * more saved runs than this should be reading from the API.
 */
export const GOODRUNS_LOCAL_MAX = 50;

/**
 * Read the local mirror, newest first. Returns ``[]`` for any failure.
 *
 * Uses {@link GoodrunRecord} as the persisted shape so the rail can
 * render straight from this without a separate adapter — the wire
 * format and the cache format are identical by design.
 */
export function listLocalGoodruns(): GoodrunRecord[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(GOODRUNS_LOCAL_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.filter(isGoodrunRecord);
  } catch {
    return [];
  }
}

/**
 * Insert (or update) a record in the local mirror. Idempotent on
 * {@link GoodrunRecord.id}: a second save with the same id replaces
 * the previous entry rather than duplicating it. Order: newest first.
 *
 * Returns the resulting list so callers can update their UI state in
 * one go without re-reading.
 */
export function saveLocalGoodrun(record: GoodrunRecord): GoodrunRecord[] {
  const existing = listLocalGoodruns().filter((r) => r.id !== record.id);
  const next = [record, ...existing].slice(0, GOODRUNS_LOCAL_MAX);
  writeLocalGoodruns(next);
  return next;
}

/**
 * Remove a record from the local mirror by id. No-op when not present.
 * The remote ``/goodruns`` record (if any) is unaffected — callers must
 * separately call a delete API to remove the durable copy. Right now
 * there is no such API; the local mirror is the only place a user can
 * "forget" a run from the UI.
 */
export function removeLocalGoodrun(id: string): GoodrunRecord[] {
  const next = listLocalGoodruns().filter((r) => r.id !== id);
  writeLocalGoodruns(next);
  return next;
}

/**
 * Replace the whole mirror. Exposed for completeness and for tests;
 * the workstation only ever calls {@link saveLocalGoodrun} and
 * {@link removeLocalGoodrun}.
 */
export function writeLocalGoodruns(records: GoodrunRecord[]): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(GOODRUNS_LOCAL_KEY, JSON.stringify(records));
  } catch {
    // Quota / disabled / private mode — accept the loss.
  }
}

/**
 * Type-guard for a parsed record matching {@link GoodrunRecord}. Used
 * to filter out corrupted entries on read; the shape of a single bad
 * record must not poison the whole list.
 */
function isGoodrunRecord(v: unknown): v is GoodrunRecord {
  if (!v || typeof v !== "object") return false;
  const o = v as Record<string, unknown>;
  return (
    typeof o.id === "string" &&
    typeof o.saved_at === "string" &&
    typeof o.dataset === "string" &&
    typeof o.horizon === "number" &&
    typeof o.match_id === "string" &&
    typeof o.query === "object" &&
    typeof o.match === "object" &&
    Array.isArray(o.match_after_values) &&
    typeof o.lens_breakdown === "object"
  );
}
