/**
 * Platform API client — typed fetch wrappers for the /platform/* endpoints.
 *
 * Base URL resolves from NEXT_PUBLIC_API_URL env var (default http://localhost:8000).
 * All functions return typed promises matching the API wire shapes defined in
 * `the-similarity-api/app/platform_routes.py`.
 *
 * Design:
 * - No caching — caller decides freshness policy.
 * - Throws on non-2xx responses with the server detail message when available.
 * - Interfaces mirror the Pydantic models in platform_routes.py so the TS
 *   consumer and Python producer stay in lock-step.
 */

// ---------------------------------------------------------------------------
// Base URL resolution
// ---------------------------------------------------------------------------

const API_BASE =
  (typeof process !== "undefined" && process.env?.NEXT_PUBLIC_API_URL) ||
  "http://localhost:8000";

/** Strip trailing slashes so callers can use template literals safely. */
function base(): string {
  return API_BASE.replace(/\/+$/, "");
}

// ---------------------------------------------------------------------------
// TypeScript interfaces — mirror platform_routes.py Pydantic models
// ---------------------------------------------------------------------------

/** Matches RunRecordModel in platform_routes.py. */
export interface Run {
  run_id: string;
  kind: string;
  config: Record<string, unknown>;
  seed: number | null;
  artifact_paths: Record<string, string>;
  summary: Record<string, unknown>;
  provenance: Record<string, unknown>;
  created_at: string;
  pillar: string | null;
  status: string;
}

/** Matches ScorecardSummaryModel in platform_routes.py. */
export interface Scorecard {
  run_id: string;
  name: string;
  passed: boolean | null;
  overall_score: number | null;
  metrics: Record<string, unknown>;
  created_at: string;
}

/** Matches ArtifactRecordModel in platform_routes.py. */
export interface Artifact {
  run_id: string;
  name: string;
  path: string;
  content_type: string | null;
  size_bytes: number | null;
  sha256: string | null;
  created_at: string;
}

// ---------------------------------------------------------------------------
// Fetch helpers
// ---------------------------------------------------------------------------

/**
 * Generic fetch wrapper that throws with server detail on non-2xx.
 * Returns parsed JSON of type T.
 */
async function apiFetch<T>(path: string): Promise<T> {
  const url = `${base()}${path}`;
  const res = await fetch(url, {
    headers: { Accept: "application/json" },
    cache: "no-store",
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`Platform API ${res.status}: ${text || res.statusText}`);
  }
  return res.json() as Promise<T>;
}

// ---------------------------------------------------------------------------
// Public API functions
// ---------------------------------------------------------------------------

/**
 * List runs, optionally filtered by kind (e.g. "finance").
 * Returns newest-first by default (server sorts by created_at desc).
 */
export async function fetchRuns(kind?: string): Promise<Run[]> {
  const params = new URLSearchParams();
  if (kind) params.set("kind", kind);
  const qs = params.toString();
  return apiFetch<Run[]>(`/platform/runs${qs ? `?${qs}` : ""}`);
}

/**
 * Fetch a single run by ID. Throws on 404.
 */
export async function fetchRun(id: string): Promise<Run> {
  return apiFetch<Run>(`/platform/runs/${encodeURIComponent(id)}`);
}

/**
 * List all scorecards for a run. Returns empty array if none registered.
 */
export async function fetchScorecards(id: string): Promise<Scorecard[]> {
  return apiFetch<Scorecard[]>(
    `/platform/runs/${encodeURIComponent(id)}/scorecards`
  );
}

/**
 * List all artifact metadata rows for a run. Returns empty array if none.
 */
export async function fetchArtifacts(id: string): Promise<Artifact[]> {
  return apiFetch<Artifact[]>(
    `/platform/runs/${encodeURIComponent(id)}/artifacts`
  );
}
