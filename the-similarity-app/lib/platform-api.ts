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

/**
 * Generic POST wrapper. Sends JSON body and returns parsed JSON of type T.
 * Throws on non-2xx with server detail message.
 */
async function apiPost<T>(path: string, body: unknown): Promise<T> {
  const url = `${base()}${path}`;
  const res = await fetch(url, {
    method: "POST",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
    },
    body: JSON.stringify(body),
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

// ---------------------------------------------------------------------------
// State Map — projection, nearest-neighbor, cluster endpoints
// ---------------------------------------------------------------------------

/**
 * A single point in the 3D state-map projection.
 * Each run is projected into a low-dimensional space for visualization.
 * The API returns x/y/z coordinates plus metadata for coloring and sizing.
 */
export interface ProjectionPoint {
  run_id: string;
  kind: string;
  x: number;
  y: number;
  z: number;
  label: string;
  metadata: Record<string, unknown>;
}

/**
 * A nearest-neighbor result — the neighbor's projection point plus distance.
 */
export interface Neighbor {
  run_id: string;
  distance: number;
  point: ProjectionPoint;
}

/**
 * A cluster assignment grouping multiple runs under a single cluster_id.
 */
export interface Cluster {
  cluster_id: number;
  run_ids: string[];
  centroid: { x: number; y: number; z: number };
}

/**
 * Fetch the full state-map projection. Returns one ProjectionPoint per
 * registered run. Empty array if no runs exist yet.
 */
export async function fetchProjection(): Promise<ProjectionPoint[]> {
  return apiFetch<ProjectionPoint[]>("/platform/state/projection");
}

/**
 * Fetch the k nearest neighbors for a given run.
 * Defaults to k=5 if not specified.
 */
export async function fetchNearest(
  runId: string,
  k: number = 5
): Promise<Neighbor[]> {
  const params = new URLSearchParams();
  params.set("k", String(k));
  return apiFetch<Neighbor[]>(
    `/platform/state/nearest/${encodeURIComponent(runId)}?${params.toString()}`
  );
}

/**
 * Fetch cluster assignments for all projected runs.
 * Returns an array of clusters, each containing member run_ids and a centroid.
 */
export async function fetchClusters(): Promise<Cluster[]> {
  return apiFetch<Cluster[]>("/platform/state/clusters");
}

// ---------------------------------------------------------------------------
// Backtest trigger — POST /platform/backtests
// ---------------------------------------------------------------------------

/** Request body for triggering a backtest via the API. */
export interface BacktestParams {
  symbol: string;
  window_size: number;
  forward_bars: number;
  seed?: number;
  k_analogs?: number;
  n_trials?: number;
}

/** Response from the backtest trigger endpoint. */
export interface BacktestResult {
  run_id: string;
  status: "succeeded" | "failed";
  error?: string | null;
  summary?: Record<string, unknown> | null;
}

/**
 * Trigger a walk-forward backtest for the given symbol.
 * Runs synchronously on the server and registers the result in the registry.
 *
 * @param params - Backtest parameters (symbol, window_size, forward_bars, etc.)
 * @returns The run_id and status, plus headline metrics on success.
 */
export async function triggerBacktest(
  params: BacktestParams
): Promise<BacktestResult> {
  return apiPost<BacktestResult>("/platform/backtests", params);
}
