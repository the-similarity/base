/**
 * Telemetry writer for the headless runner.
 *
 * Emits newline-delimited JSON (JSONL) so downstream tooling (World Eval,
 * notebooks, ad-hoc jq queries) can stream-process runs of any length without
 * loading the whole file into memory.
 *
 * File layout:
 *   line 0:  {"type":"provenance", seed, generator_name, version, params,
 *             created_at, scenario, duration_steps}
 *   line i:  {"type":"tick", tick, metrics, state?}
 *   last:    {"type":"summary", final_metrics, totals, wall_time_ms}
 *
 * The provenance line loosely mirrors `the_similarity/synthetic/contracts.py`
 * Provenance fields so World Eval can ingest runs from this generator with the
 * same contract it uses for the Python copies generator.
 *
 * Invariants:
 * - One JSON object per line, terminated by a single \n. No trailing comma,
 *   no surrounding array brackets. Each line is independently parseable.
 * - The writer buffers through the Node write stream; if the process crashes
 *   mid-run the file will contain whatever ticks were flushed, which is still
 *   useful for post-mortem debugging.
 * - close() must be awaited before the process exits, otherwise the last
 *   batch of ticks may be lost. The runner handles this in a finally block.
 */

import { createWriteStream, mkdirSync } from 'node:fs';
import { dirname } from 'node:path';

const GENERATOR_NAME = 'the-similarity-fractal-headless';
const GENERATOR_VERSION = '0.1.0';

export class TelemetryWriter {
  constructor(outPath) {
    this.outPath = outPath;
    // Make sure the parent dir exists — users will often pass `runs/foo.jsonl`
    // without pre-creating `runs/`, and a missing-dir error here would be a
    // frustrating cliff.
    mkdirSync(dirname(outPath), { recursive: true });
    this.stream = createWriteStream(outPath, { flags: 'w', encoding: 'utf8' });
    this.lineCount = 0;
  }

  _write(obj) {
    this.stream.write(JSON.stringify(obj) + '\n');
    this.lineCount += 1;
  }

  writeProvenance({ seed, scenario, params, durationSteps }) {
    this._write({
      type: 'provenance',
      seed,
      generator_name: GENERATOR_NAME,
      version: GENERATOR_VERSION,
      scenario_name: scenario.name,
      scenario,           // include the full scenario for exact replay
      params,             // resolved params (after defaults applied)
      duration_steps: durationSteps,
      created_at: new Date().toISOString(),
    });
  }

  writeTick(tick, metrics, state) {
    const rec = { type: 'tick', tick, metrics };
    if (state !== undefined) rec.state = state;
    this._write(rec);
  }

  writeSummary(finalMetrics, totals, wallTimeMs) {
    this._write({
      type: 'summary',
      final_metrics: finalMetrics,
      totals,
      wall_time_ms: wallTimeMs,
    });
  }

  async close() {
    // Wrap stream.end in a promise so callers can await flushing. Node's
    // writable.end takes a callback; we use it to resolve once the OS write
    // has been queued (not necessarily fsync'd, but good enough for tests).
    await new Promise((resolveEnd, reject) => {
      this.stream.end((err) => (err ? reject(err) : resolveEnd()));
    });
  }
}
