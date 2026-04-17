/**
 * Platform registry HTTP client — worlds adapter side.
 *
 * The headless runner (src/sim/headless/runner.js) emits a JSONL telemetry
 * file with provenance on line 0, per-tick metrics in the middle, and a
 * summary record as the last line. This module reads that file, builds a
 * RunArtifact-shaped payload, and POSTs it to the Platform REST API so the
 * run becomes indexable from the registry CLI and the UI.
 *
 * Why an HTTP client, not a direct SQLite writer?
 * ------------------------------------------------
 * - Language boundary: the registry is SQLite accessed via Python's stdlib.
 *   Reaching into it from Node would require a C addon (better-sqlite3) and
 *   a duplicate schema definition. An HTTP hop keeps the fractal package
 *   dependency-free (Node stdlib only).
 * - Single source of truth: the FastAPI layer (the_similarity.platform.api)
 *   already handles WAL concurrency, run_dir resolution, and run_id minting.
 *   We delegate to it.
 * - Best-effort: if the API is not running, the world still runs fine. The
 *   client warns and exits 0 so registration never blocks simulation.
 *
 * Endpoint contract (mirrors the Python routes.py)
 * ------------------------------------------------
 * - POST /platform/runs         — not yet implemented server-side as of this
 *   writing; we POST and tolerate 404. When the worlds POST endpoint lands,
 *   this client will work unchanged.
 * - Fallback: POST /runs/worlds — existing route that takes the same
 *   scenario/seed/steps inputs but re-runs the simulation server-side. We
 *   do NOT fall back to this by default — re-running would double-bill
 *   compute. Instead we post to a pre-existing-run endpoint and expect it
 *   to accept a pre-built RunArtifact.
 *
 * Environment variables
 * ---------------------
 * - THE_SIMILARITY_API_URL — base URL of the Platform API. Default
 *   http://localhost:8787 (matches the Python server's DEFAULT_PORT).
 *
 * File lifecycle invariant
 * ------------------------
 * The JSONL file passed in MUST already be closed (fully flushed to disk).
 * The runner guarantees this by awaiting writer.close() before invoking
 * this adapter. Reading a still-open file would risk a truncated summary
 * record.
 */

import { readFileSync } from 'node:fs';
import { request as httpRequest } from 'node:http';
import { request as httpsRequest } from 'node:https';
import { URL } from 'node:url';
import { randomUUID } from 'node:crypto';

/**
 * Default API base URL. Aligns with the Python FastAPI's DEFAULT_PORT
 * (the_similarity/platform/api/main.py) so a developer running the API
 * with no flags and running the worlds runner with no env override will
 * naturally connect. Exported so callers / tests can reference the same
 * value.
 */
export const DEFAULT_API_URL = 'http://localhost:8787';

/**
 * Mint a fresh run_id matching the Python platform's convention: UUID4
 * hex without dashes. randomUUID() returns the dashed canonical form;
 * we strip to match the regex ``^[0-9a-f]{32}$`` the schema enforces.
 *
 * Exported so callers can pre-allocate an id (e.g. to put in log lines
 * before the POST completes).
 */
export function newRunId() {
  return randomUUID().replace(/-/g, '');
}

/**
 * Parse a worlds JSONL file into { provenance, summary, lineCount }.
 *
 * Linear scan: the provenance record is always line 0 and the summary
 * record is always the last type=summary line. We remember the first
 * provenance we see (ignoring any duplicates) and the last summary, which
 * mirrors the Python-side _parse_worlds_jsonl in routes.py.
 *
 * Malformed lines are skipped rather than raising — a truncated file is
 * still partially informative (and the runner already exited 0/2, so
 * we're post-mortem here).
 */
export function parseWorldsJsonl(path) {
  const raw = readFileSync(path, 'utf8');
  const lines = raw.split('\n');
  let provenance = {};
  let summary = {};
  let lineCount = 0;
  for (const line of lines) {
    if (!line.trim()) continue;
    lineCount += 1;
    let record;
    try {
      record = JSON.parse(line);
    } catch {
      // Skip malformed lines — we don't want a single bad line to drop the
      // whole registration.
      continue;
    }
    if (record.type === 'provenance' && Object.keys(provenance).length === 0) {
      provenance = record;
    } else if (record.type === 'summary') {
      summary = record;
    }
  }
  return { provenance, summary, lineCount };
}

/**
 * Build a RunArtifact-shaped payload from worlds-runner outputs.
 *
 * Field layout matches the_similarity/platform/artifacts.py: run_id, kind,
 * config, seed, artifact_paths, summary, provenance, created_at. We keep
 * this pure (no I/O beyond the JSONL read upstream) so tests can stub
 * parseWorldsJsonl and exercise the request shape in isolation.
 */
export function buildWorldsArtifact({
  runDir,
  jsonlPath,
  scenario,
  seed,
  steps,
  parsed,
  runId,
}) {
  // artifact_paths keys the telemetry file by its basename so the path is
  // portable when the run_dir is copied / rehosted. The routes.py
  // _resolve_artifact_file helper joins run_dir + this relative path.
  const jsonlBasename = jsonlPath.split('/').pop();
  const providedSummary = parsed.summary || {};
  const summary = {
    pillar: 'worlds',
  };
  if (providedSummary.final_metrics) {
    summary.final_metrics = providedSummary.final_metrics;
  }
  if (providedSummary.totals) {
    summary.totals = providedSummary.totals;
  }
  if (providedSummary.wall_time_ms !== undefined) {
    summary.wall_time_ms = providedSummary.wall_time_ms;
  }

  const provenance = { ...(parsed.provenance || {}) };
  provenance.run_dir = runDir;
  // The schema's ``created_at`` is UTC ISO-8601 seconds-precision. We
  // match the Python iso_now() style (no fractional seconds) for
  // byte-comparability when the same run flows through both surfaces.
  const createdAt = new Date().toISOString().replace(/\.\d+Z$/, 'Z');

  return {
    run_id: runId || newRunId(),
    kind: 'worlds',
    config: {
      scenario_path: scenario || null,
      seed,
      steps,
    },
    seed: seed,
    artifact_paths: {
      telemetry: jsonlBasename,
    },
    summary,
    provenance,
    created_at: createdAt,
  };
}

/**
 * POST a JSON payload to <baseUrl><path>, returning { status, body }.
 *
 * A thin Promise wrapper over Node's http/https request. We avoid fetch
 * (available in Node 18+) only because some CI images still pin to Node
 * 16 — the http module works universally and costs ~20 lines.
 *
 * ``timeoutMs`` guards against a hung server: registration is best-effort
 * and we'd rather the runner exit than block indefinitely on a dead API.
 */
function postJson(baseUrl, path, payload, timeoutMs = 10000) {
  return new Promise((resolve, reject) => {
    const url = new URL(path, baseUrl);
    const body = JSON.stringify(payload);
    const options = {
      method: 'POST',
      hostname: url.hostname,
      port: url.port || (url.protocol === 'https:' ? 443 : 80),
      path: url.pathname + (url.search || ''),
      headers: {
        'Content-Type': 'application/json',
        'Content-Length': Buffer.byteLength(body),
      },
      timeout: timeoutMs,
    };
    const transport = url.protocol === 'https:' ? httpsRequest : httpRequest;
    const req = transport(options, (res) => {
      const chunks = [];
      res.on('data', (c) => chunks.push(c));
      res.on('end', () => {
        resolve({
          status: res.statusCode,
          body: Buffer.concat(chunks).toString('utf8'),
        });
      });
    });
    req.on('error', (err) => reject(err));
    req.on('timeout', () => {
      req.destroy(new Error(`registry POST timed out after ${timeoutMs}ms`));
    });
    req.write(body);
    req.end();
  });
}

/**
 * Register a finished worlds run with the Platform API.
 *
 * Best-effort: any network or server error is caught and logged to
 * stderr. The function RESOLVES (never rejects) so a caller's Promise
 * chain is not derailed by a missing server.
 *
 * Returns the run_id on success, null on best-effort failure so callers
 * can log "registered run X" vs "registration skipped".
 *
 * @param {object} opts
 * @param {string} opts.runDir - Absolute path to the run directory.
 * @param {string} opts.jsonlPath - Absolute path to the JSONL telemetry file.
 * @param {string} [opts.scenario] - Path / name of the scenario file.
 * @param {number} opts.seed - Seed used for the run.
 * @param {number} [opts.steps] - Number of ticks run.
 * @param {object} [opts.summary] - Pre-parsed summary override (optional).
 * @param {string} [opts.apiUrl] - API base URL override.
 * @param {string} [opts.runId] - Pre-allocated run_id (optional).
 * @param {(msg: string) => void} [opts.log] - Log sink (default console.warn).
 * @returns {Promise<string|null>}
 */
export async function registerWorldRun(opts) {
  const {
    runDir,
    jsonlPath,
    scenario,
    seed,
    steps,
    summary: summaryOverride,
    apiUrl = process.env.THE_SIMILARITY_API_URL || DEFAULT_API_URL,
    runId,
    log = (msg) => process.stderr.write(`${msg}\n`),
  } = opts;

  let parsed;
  try {
    parsed = parseWorldsJsonl(jsonlPath);
  } catch (err) {
    log(`[registry-client] skip: could not read JSONL ${jsonlPath}: ${err.message}`);
    return null;
  }

  // Caller can inject a summary (e.g. from a live summarize call) if they
  // already have it; saves re-parsing the file but is strictly optional.
  if (summaryOverride) {
    parsed.summary = summaryOverride;
  }

  const artifact = buildWorldsArtifact({
    runDir,
    jsonlPath,
    scenario,
    seed,
    steps,
    parsed,
    runId,
  });

  try {
    // The primary endpoint is /platform/runs. The existing Python route
    // set (/runs/worlds) re-runs the simulation server-side which is not
    // what we want from a client that already has the output on disk.
    // If /platform/runs is absent we log and return null — the run still
    // succeeded locally.
    const res = await postJson(apiUrl, '/platform/runs', artifact);
    if (res.status >= 200 && res.status < 300) {
      return artifact.run_id;
    }
    log(
      `[registry-client] skip: POST /platform/runs -> ${res.status} ${res.body}`
    );
    return null;
  } catch (err) {
    // Most common: ECONNREFUSED when the API is not running. Warn and
    // move on — registration is opt-in from the runner's perspective.
    log(`[registry-client] skip: POST failed: ${err.message}`);
    return null;
  }
}

export default {
  DEFAULT_API_URL,
  newRunId,
  parseWorldsJsonl,
  buildWorldsArtifact,
  registerWorldRun,
};
