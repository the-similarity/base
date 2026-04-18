/**
 * Telemetry export utilities for headless simulation JSONL files.
 *
 * Provides structured parsing, CSV export, and cross-run comparison for
 * downstream analysis in pandas, R, or custom tooling. All functions operate
 * on the JSONL format documented in `telemetry-schema.md`.
 *
 * Lifecycle:
 *   - parseTelemetry() reads and validates a complete JSONL file.
 *   - toCSV() flattens tick metrics into a header + rows CSV.
 *   - diffRuns() compares two parsed runs at summary and tick level.
 *
 * Immutability: parsed objects are plain JS objects. Callers may mutate them
 * freely without affecting the source file or internal state.
 *
 * @module telemetry-export
 */

import { readFileSync, writeFileSync } from 'node:fs';

// ── parseTelemetry ──────────────────────────────────────────────────────────

/**
 * Parse a headless runner JSONL file into a structured object.
 *
 * Expects the JSONL layout: line 0 = provenance, lines 1..N = tick, last = summary.
 * Lines that fail JSON.parse are silently skipped (crash-recovery partial files).
 *
 * @param {string} jsonlPath - Absolute or relative path to a .jsonl file.
 * @returns {{ provenance: object|null, ticks: object[], summary: object|null }}
 */
export function parseTelemetry(jsonlPath) {
  const content = readFileSync(jsonlPath, 'utf8');
  const lines = content.trim().split('\n');

  let provenance = null;
  const ticks = [];
  let summary = null;

  for (const line of lines) {
    if (!line.trim()) continue;
    let obj;
    try {
      obj = JSON.parse(line);
    } catch {
      // Partial / corrupt line — skip gracefully. This happens when the runner
      // crashes mid-write and the last line is truncated.
      continue;
    }

    switch (obj.type) {
      case 'provenance':
        provenance = obj;
        break;
      case 'tick':
        ticks.push(obj);
        break;
      case 'summary':
        summary = obj;
        break;
      // Unknown types are silently ignored for forward-compatibility.
    }
  }

  return { provenance, ticks, summary };
}

// ── toCSV ───────────────────────────────────────────────────────────────────

/**
 * Export tick data as a CSV file.
 *
 * Flattens each tick's metrics into one row. The header row uses the metric
 * keys from the first tick. If metrics keys vary across ticks (unlikely but
 * possible with schema evolution), missing values become empty strings.
 *
 * @param {object[]} ticks - Array of tick objects from parseTelemetry().
 * @param {string} outputPath - Path to write the CSV file.
 * @returns {string} The CSV content (also written to outputPath).
 */
export function toCSV(ticks, outputPath) {
  if (ticks.length === 0) {
    const empty = 'tick\n';
    writeFileSync(outputPath, empty, 'utf8');
    return empty;
  }

  // Derive column names from the union of all ticks' metrics keys.
  // Using a Set preserves insertion order from the first tick while catching
  // any keys that appear only in later ticks.
  const colSet = new Set(['tick']);
  for (const t of ticks) {
    if (t.metrics) {
      for (const k of Object.keys(t.metrics)) {
        colSet.add(k);
      }
    }
  }
  const columns = [...colSet];

  // Header
  const rows = [columns.join(',')];

  // Data rows
  for (const t of ticks) {
    const vals = columns.map((col) => {
      if (col === 'tick') return t.tick ?? '';
      return t.metrics?.[col] ?? '';
    });
    rows.push(vals.join(','));
  }

  const csv = rows.join('\n') + '\n';
  writeFileSync(outputPath, csv, 'utf8');
  return csv;
}

// ── toParquet ───────────────────────────────────────────────────────────────

/**
 * Export tick data as a Parquet file.
 *
 * FUTURE WORK: Requires `parquetjs` or `parquetjs-lite` as a dependency.
 * Currently not implemented because the fractal package has zero npm deps
 * by design. When a Parquet export is needed, install `parquetjs-lite` and
 * implement this function following the same column schema as toCSV().
 *
 * @param {object[]} _ticks - Tick objects (unused).
 * @param {string} _outputPath - Output path (unused).
 * @throws {Error} Always — not yet implemented.
 */
export function toParquet(_ticks, _outputPath) {
  throw new Error(
    'toParquet is not yet implemented. Install parquetjs-lite and implement. '
    + 'Use toCSV() for now — pandas.read_csv() is fast enough for typical run sizes.'
  );
}

// ── diffRuns ────────────────────────────────────────────────────────────────

/**
 * Compare two parsed runs and produce a structured diff report.
 *
 * Comparison covers:
 * 1. Summary-level deltas: absolute and relative difference for each metric
 *    in the summary's final_metrics and totals.
 * 2. Tick-level divergence: the first tick where alive or dead counts differ
 *    between the two runs, which is useful for identifying where stochastic
 *    paths fork.
 *
 * Both runs must have been parsed via parseTelemetry(). If either run lacks
 * a summary, the summary delta will be null.
 *
 * @param {{ provenance: object, ticks: object[], summary: object }} runA
 * @param {{ provenance: object, ticks: object[], summary: object }} runB
 * @returns {{
 *   seeds: { a: number, b: number },
 *   tick_counts: { a: number, b: number },
 *   metrics_delta: object|null,
 *   tick_divergence_point: number|null,
 *   divergence_details: object|null,
 * }}
 */
export function diffRuns(runA, runB) {
  const result = {
    seeds: {
      a: runA.provenance?.seed ?? null,
      b: runB.provenance?.seed ?? null,
    },
    tick_counts: {
      a: runA.ticks.length,
      b: runB.ticks.length,
    },
    metrics_delta: null,
    tick_divergence_point: null,
    divergence_details: null,
  };

  // ── Summary-level delta ──────────────────────────────────────────
  if (runA.summary && runB.summary) {
    result.metrics_delta = {};

    // Compare final_metrics
    const fmA = runA.summary.final_metrics ?? {};
    const fmB = runB.summary.final_metrics ?? {};
    const allKeys = new Set([...Object.keys(fmA), ...Object.keys(fmB)]);

    for (const key of allKeys) {
      const a = fmA[key] ?? 0;
      const b = fmB[key] ?? 0;
      const abs = b - a;
      // Relative delta: percentage change from A to B. Guard against
      // division by zero — report null when the base value is zero.
      const rel = a !== 0 ? abs / Math.abs(a) : (b !== 0 ? Infinity : 0);
      result.metrics_delta[key] = { a, b, abs_delta: abs, rel_delta: rel };
    }

    // Compare totals
    const tA = runA.summary.totals ?? {};
    const tB = runB.summary.totals ?? {};
    const totalKeys = new Set([...Object.keys(tA), ...Object.keys(tB)]);
    for (const key of totalKeys) {
      const a = tA[key] ?? 0;
      const b = tB[key] ?? 0;
      const abs = b - a;
      const rel = a !== 0 ? abs / Math.abs(a) : (b !== 0 ? Infinity : 0);
      result.metrics_delta[`total_${key}`] = { a, b, abs_delta: abs, rel_delta: rel };
    }

    // Wall time delta
    const wallA = runA.summary.wall_time_ms ?? 0;
    const wallB = runB.summary.wall_time_ms ?? 0;
    result.metrics_delta.wall_time_ms = {
      a: wallA,
      b: wallB,
      abs_delta: wallB - wallA,
      rel_delta: wallA !== 0 ? (wallB - wallA) / Math.abs(wallA) : 0,
    };
  }

  // ── Tick-level divergence ────────────────────────────────────────
  // Walk ticks in parallel and find the first one where alive or dead counts
  // differ. This identifies where the two stochastic trajectories fork.
  const minLen = Math.min(runA.ticks.length, runB.ticks.length);
  for (let i = 0; i < minLen; i++) {
    const mA = runA.ticks[i].metrics ?? {};
    const mB = runB.ticks[i].metrics ?? {};

    if (mA.alive !== mB.alive || mA.dead !== mB.dead) {
      result.tick_divergence_point = runA.ticks[i].tick;
      result.divergence_details = {
        tick: runA.ticks[i].tick,
        a: { alive: mA.alive, dead: mA.dead },
        b: { alive: mB.alive, dead: mB.dead },
      };
      break;
    }
  }

  return result;
}
