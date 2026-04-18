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

/**
 * Matches ScorecardSummaryModel in platform_routes.py.
 *
 * Field names track the registry-truth ``scorecards`` table:
 *   - ``kind`` (enum string: fidelity | privacy | utility |
 *     controllability | calibration | backtest) replaces the earlier
 *     free-form ``name`` field.
 *   - ``thresholds`` + ``details`` replace the single ``metrics`` blob.
 *   - ``created_at`` is not part of the wire shape — the parent run's
 *     timestamp is authoritative.
 */
export interface Scorecard {
  run_id: string;
  kind: string;
  overall_score: number | null;
  passed: boolean | null;
  thresholds: Record<string, unknown>;
  details: Record<string, unknown>;
}

/**
 * Matches ArtifactRecordModel in platform_routes.py.
 *
 * ``checksum`` (SHA-256 hex) replaces the earlier ``sha256`` alias so
 * the wire contract tracks the registry column name.
 */
export interface Artifact {
  run_id: string;
  name: string;
  path: string;
  content_type: string | null;
  size_bytes: number | null;
  checksum: string | null;
  created_at: string;
}

/**
 * Matches ScenarioSpecModel in platform_routes.py — registry-truth
 * ``scenarios`` row shape.
 */
export interface Scenario {
  scenario_id: string;
  name: string;
  version: string;
  engine: string;
  params: Record<string, unknown>;
  metadata: Record<string, unknown>;
}

/**
 * Matches DatasetSpecModel in platform_routes.py — registry-truth
 * ``datasets`` row shape.
 */
export interface Dataset {
  dataset_id: string;
  name: string;
  version: string;
  source: string;
  schema_uri: string | null;
  n_rows: number | null;
  n_columns: number | null;
  checksum: string | null;
  metadata: Record<string, unknown>;
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
