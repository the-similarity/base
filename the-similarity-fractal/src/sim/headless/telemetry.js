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

/**
 * Sibling writer for per-agent (x, y, z) trajectory records.
 *
 * Why a sibling JSONL file (not a new line type in the main file)?
 * - Backward-compat: existing consumers stream the main JSONL by `type`
 *   field; injecting a third type would force every consumer to update.
 * - Stream-friendly: trajectory records are O(N_agents) per tick which
 *   can dominate the byte budget of a long run. Keeping them in their
 *   own file means standard analytics tooling can ignore them.
 * - Pairing convention: the tracks file path is `<output>.tracks.jsonl`
 *   so the relationship to the parent run is obvious from `ls`.
 *
 * Lifecycle:
 * - Open in TelemetryWriter constructor when tracksPath is supplied.
 * - One JSON line per (agent, tick) recorded via writeTrack().
 * - Closed alongside the main writer in close().
 */
class AgentTracksWriter {
  constructor(path) {
    this.path = path;
    mkdirSync(dirname(path), { recursive: true });
    this.stream = createWriteStream(path, { flags: 'w', encoding: 'utf8' });
    this.lineCount = 0;
  }
  writeRecord(rec) {
    this.stream.write(JSON.stringify(rec) + '\n');
    this.lineCount += 1;
  }
  async close() {
    await new Promise((resolveEnd, reject) => {
      this.stream.end((err) => (err ? reject(err) : resolveEnd()));
    });
  }
}

const GENERATOR_NAME = 'the-similarity-fractal-headless';
const GENERATOR_VERSION = '0.1.0';

/**
 * Telemetry format version. Bumped when the JSONL schema changes in a
 * backward-incompatible way (new required fields, renamed keys, etc.).
 * Downstream consumers should check this field and bail if > their supported
 * version, or adapt gracefully for minor bumps.
 *
 * 2.0: Added population_density, food_per_agent, energy_variance to tick
 *      metrics. Added telemetry_version field to provenance line.
 */
const TELEMETRY_VERSION = '2.0';

export class TelemetryWriter {
  /**
   * @param {string} outPath - Main JSONL path.
   * @param {object} [opts]
   * @param {string} [opts.tracksPath] - When set, per-agent (x,y,z) records
   *     are written to this sibling JSONL file. Each record has shape
   *     `{agent_id, tick, x, y, z?}`; z is omitted in 2D mode.
   */
  constructor(outPath, opts = {}) {
    this.outPath = outPath;
    // Make sure the parent dir exists — users will often pass `runs/foo.jsonl`
    // without pre-creating `runs/`, and a missing-dir error here would be a
    // frustrating cliff.
    mkdirSync(dirname(outPath), { recursive: true });
    this.stream = createWriteStream(outPath, { flags: 'w', encoding: 'utf8' });
    this.lineCount = 0;

    // Optional per-agent track sibling. Stays null when not requested so
    // the no-flag path is byte-identical to the legacy behavior.
    this.tracksWriter = opts.tracksPath
      ? new AgentTracksWriter(opts.tracksPath)
      : null;
  }

  /**
   * Emit one (agent_id, tick, x, y, z?) record per alive agent. Caller is
   * responsible for invoking this each tick when tracking is enabled —
   * the writer cannot infer the right cadence on its own. No-op when
   * tracksWriter is null (i.e. --track-agents was not passed).
   */
  writeAgentTracks(tick, agents) {
    if (!this.tracksWriter) return;
    for (const a of agents) {
      if (!a.alive) continue;
      const rec = { agent_id: a.id, tick, x: a.x, y: a.y };
      // Only include z when defined — keeps 2D-mode tracks compact and
      // matches the world's 2D agent shape.
      if (a.z !== undefined) rec.z = a.z;
      this.tracksWriter.writeRecord(rec);
    }
  }

  _write(obj) {
    this.stream.write(JSON.stringify(obj) + '\n');
    this.lineCount += 1;
  }

  writeProvenance({ seed, scenario, params, durationSteps }) {
    this._write({
      type: 'provenance',
      telemetry_version: TELEMETRY_VERSION,
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
    // Close the tracks sibling alongside the main file so callers only need
    // to await one close() — the runner's finally block already does this.
    if (this.tracksWriter) {
      await this.tracksWriter.close();
    }
  }
}
