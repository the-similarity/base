/**
 * World-eval scorecard — on-disk artifact format.
 *
 * Mirrors the copies-side `Scorecard` dataclass from
 * `the_similarity/synthetic/contracts.py` so that a future unified
 * downstream report renderer can ingest both JS (worlds) and Python (copies)
 * scorecards without branching on source. Copies carry fidelity/privacy/
 * utility reports; worlds carry regime-coverage + controllability in their
 * place. The shared field is `provenance` — every scorecard must be
 * reproducible.
 *
 * Layout on disk (one sweep):
 *   <out>/sweep-<id>/scorecard.json     # everything below in one JSON blob
 *   <out>/sweep-<id>/telemetry.jsonl    # flat JSONL of every tick across cells
 *   <out>/sweep-<id>/cells.json         # cell manifest (knobs + seed + n_rows)
 *
 * The sweep-id is passed by the caller so CI / orchestrator logs can
 * reference it; if omitted we use the provenance timestamp.
 *
 * Invariants:
 * - `scorecard.json` is small (< 100 KB) and safe to commit as a fixture.
 * - `telemetry.jsonl` may be large; callers that don't want it should pass
 *   `writeTelemetry: false`.
 * - All writes go through `node:fs/promises`. We `mkdir -p` the sweep
 *   directory so concurrent sweeps into the same `out` dir don't race
 *   (directory creation is idempotent).
 *
 * @module eval/scorecard
 */

import { mkdir, writeFile } from 'node:fs/promises';
import { join } from 'node:path';

/**
 * Build the scorecard object (no IO). Separated from `writeScorecard` so
 * tests can assert the shape without touching the filesystem.
 */
export function buildScorecard({
  scenario,
  knobGrid,
  seeds,
  ticks,
  regimeCoverage,
  controllability,
  provenance,
  sweepId,
}) {
  return {
    // Mirrors the Python Scorecard.dataset slot conceptually — here we
    // inline the scenario + knob grid + seeds since there is no tabular
    // "dataset" to point at. A downstream renderer keys off `kind` to pick
    // the right view.
    kind: 'worlds',
    sweep_id: sweepId ?? provenance.created_at,
    scenario,
    knob_grid: knobGrid,
    seeds,
    ticks,
    regime_coverage: regimeCoverage,
    controllability,
    provenance,
  };
}

/**
 * Write a sweep artifact to `<out>/sweep-<id>/`. Returns the directory path
 * it wrote to.
 */
export async function writeScorecard({
  outDir,
  scorecard,
  telemetry = null,
  cells = null,
  writeTelemetry = true,
}) {
  const dir = join(outDir, `sweep-${scorecard.sweep_id}`);
  await mkdir(dir, { recursive: true });

  // `writeFile` with a string is safer than streams for small JSON blobs —
  // we accept the memory cost since scorecard.json is tiny by construction.
  await writeFile(join(dir, 'scorecard.json'), JSON.stringify(scorecard, null, 2));

  if (cells) {
    await writeFile(join(dir, 'cells.json'), JSON.stringify(cells, null, 2));
  }

  if (writeTelemetry && Array.isArray(telemetry)) {
    // One JSON row per line — cheap to grep, stream, and load incrementally.
    // We avoid a final trailing newline-only line by joining with '\n'.
    const buf = telemetry.map((r) => JSON.stringify(r)).join('\n') + '\n';
    await writeFile(join(dir, 'telemetry.jsonl'), buf);
  }

  return dir;
}
