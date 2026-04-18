/**
 * Public entry point for the world-eval module.
 *
 * Re-exports the stable surface: sweep runner, regime coverage, controllability,
 * scorecard builder/writer, and provenance helpers. Everything a caller
 * (CLI, test, orchestrator) needs to run a sweep and emit an artifact.
 */

export { runSweep, runCell, enumerateGrid, applyKnobs } from './sweep.js';
export {
  summarizeRegimeCoverage,
  classifyRow,
  knobKey,
  REGIME_LABELS,
} from './regime-coverage.js';
export {
  controllability,
  aggregateCells,
  permutationPValue,
} from './controllability.js';
export { buildScorecard, writeScorecard } from './scorecard.js';
export { makeProvenance, isoNow } from './provenance.js';
export { runEvaluation } from './harness.js';
