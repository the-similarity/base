/**
 * Provenance records for world-eval sweep artifacts.
 *
 * Mirrors the Python-side `Provenance` dataclass defined in
 * `the_similarity/synthetic/contracts.py` so that scorecards emitted by the
 * JS world-eval layer can be consumed by the same downstream tooling as the
 * copies-side (tabular) scorecards.
 *
 * Fields are intentionally a strict subset of the Python contract: every
 * synthetic artifact must carry seed + generator identity + params + an
 * ISO-8601 UTC timestamp so a run is reproducible bit-for-bit given the same
 * source code.
 *
 * Immutability: returned objects are frozen. If you need a modified copy,
 * spread into a new literal rather than mutating in place.
 */

/** Canonical ISO-8601 UTC timestamp, second precision. */
export function isoNow() {
  // Trim fractional seconds — matches Python `datetime.now(tz=UTC).isoformat(timespec="seconds")`
  // so equality checks across languages succeed in tests.
  return new Date().toISOString().replace(/\.\d{3}Z$/, 'Z');
}

/**
 * Build a Provenance record. `params` must be JSON-serializable — we freeze
 * it together with the wrapper so accidental downstream mutation is loud.
 */
export function makeProvenance({
  sourceId,
  generatorName,
  generatorVersion,
  seed,
  params = {},
  createdAt = null,
}) {
  if (typeof seed !== 'number' || !Number.isInteger(seed)) {
    throw new TypeError(`Provenance.seed must be an integer, got ${seed}`);
  }
  if (!generatorName || !generatorVersion) {
    throw new TypeError('Provenance requires generatorName and generatorVersion');
  }
  return Object.freeze({
    source_id: sourceId ?? generatorName,
    generator_name: generatorName,
    generator_version: generatorVersion,
    seed,
    // Freezing params prevents downstream code from mutating the record the
    // scorecard was built with — provenance must be tamper-evident.
    params: Object.freeze({ ...params }),
    created_at: createdAt ?? isoNow(),
  });
}
