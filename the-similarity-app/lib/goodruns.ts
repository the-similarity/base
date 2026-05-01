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
