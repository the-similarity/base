/**
 * Regime coverage summary for sweep telemetry.
 *
 * Bins each telemetry row into a discrete `regime` label, then reports the
 * fraction of regime labels each scenario configuration visited at least
 * once over its run. "Configuration" = a distinct knob combination (aggregated
 * across seeds) since a run that only visits regimes under one seed is still
 * covering that regime for the knob setting.
 *
 * Why this exists:
 *   The sweep tells us what ticks happened; regime coverage tells us whether
 *   the knobs actually explored the dynamical space we care about. Without
 *   this a well-run grid can still leave large swaths of behavior unseen.
 *
 * Binning rule (MVP):
 *   We classify each tick on two axes derived from `summarizeWorld` output:
 *     - population regime: collapsed | thin | healthy   (by `alive` count)
 *     - energy regime:     starving  | lean | fed        (by `mean_energy`)
 *   Label = "<population>:<energy>" → 9 possible regimes.
 *
 *   The thresholds are expressed as fractions of the scenario's initial
 *   population so they scale when someone sweeps `world.initial_population`.
 *   Energy thresholds are absolute (mean_energy lives in [0, 1]).
 *
 * Immutability: this module does not mutate its inputs. The returned
 * summary is a plain JSON-safe object built fresh on every call.
 *
 * @module eval/regime-coverage
 */

/** All 9 regime labels, enumerated. Freezing guards against accidental edits. */
export const REGIME_LABELS = Object.freeze([
  'collapsed:starving', 'collapsed:lean', 'collapsed:fed',
  'thin:starving',      'thin:lean',      'thin:fed',
  'healthy:starving',   'healthy:lean',   'healthy:fed',
]);

/**
 * Classify a single telemetry row.
 * `initialPop` is used to normalize the population axis so thresholds are
 * scenario-relative rather than absolute.
 */
export function classifyRow(row, initialPop) {
  // Population axis — fraction of starting population still alive. A world
  // that has fewer than 25% alive is considered collapsed; > 75% is healthy.
  const popFrac = initialPop > 0 ? row.alive / initialPop : 0;
  const pop = popFrac < 0.25 ? 'collapsed' : popFrac < 0.75 ? 'thin' : 'healthy';

  // Energy axis — mean energy of alive agents. Below 0.25 agents are dying
  // off; above 0.6 the population is well-fed.
  const e = row.mean_energy ?? 0;
  const en = e < 0.25 ? 'starving' : e < 0.6 ? 'lean' : 'fed';

  return `${pop}:${en}`;
}

/**
 * Stable key for a knob combination — sorted keys, JSON-encoded values, so
 * two rows with identical knobs in different insertion order hash the same.
 * Exported for tests and for downstream consumers that want to re-bucket
 * telemetry by configuration on their own.
 */
export function knobKey(knobs) {
  const keys = Object.keys(knobs).sort();
  return keys.map((k) => `${k}=${JSON.stringify(knobs[k])}`).join('|') || '<base>';
}

/**
 * Build a regime-coverage summary.
 *
 * @param {Array} telemetry - Flat rows from `runSweep`.
 * @param {object} opts
 * @param {number} opts.initialPop - Starting population of the base scenario.
 * @param {string[]} [opts.knobNames] - Subset of row keys that identify the
 *   knob combination. If omitted, we infer from the keys present on rows
 *   (excluding the telemetry schema keys).
 */
export function summarizeRegimeCoverage(telemetry, { initialPop, knobNames } = {}) {
  if (!Array.isArray(telemetry)) {
    throw new TypeError('summarizeRegimeCoverage: telemetry must be an array');
  }
  // Keys emitted by summarizeWorld + sweep identity columns we must exclude
  // when auto-detecting knob names.
  const TELEMETRY_KEYS = new Set([
    'tick', 'seed',
    'alive', 'dead', 'food_count', 'mean_energy', 'mean_age',
    'cumulative_deaths', 'cumulative_food_eaten',
  ]);

  let knobs = knobNames;
  if (!knobs) {
    const seen = new Set();
    for (const r of telemetry) {
      for (const k of Object.keys(r)) if (!TELEMETRY_KEYS.has(k)) seen.add(k);
    }
    knobs = [...seen].sort();
  }

  // perConfig: configKey → Set<regime>
  const perConfig = new Map();
  // global: regime → count of rows classified there (for a fleet-level view)
  const globalCounts = new Map();
  const ipop = initialPop ?? 1;

  for (const row of telemetry) {
    const regime = classifyRow(row, ipop);
    globalCounts.set(regime, (globalCounts.get(regime) ?? 0) + 1);

    const cfg = {};
    for (const k of knobs) if (k in row) cfg[k] = row[k];
    const key = knobKey(cfg);
    if (!perConfig.has(key)) perConfig.set(key, { knobs: cfg, regimes: new Set() });
    perConfig.get(key).regimes.add(regime);
  }

  const totalRegimes = REGIME_LABELS.length;
  const perConfigOut = [];
  for (const { knobs: cfg, regimes } of perConfig.values()) {
    perConfigOut.push({
      knobs: cfg,
      regimes_visited: [...regimes].sort(),
      coverage: regimes.size / totalRegimes,
    });
  }
  // Sort by coverage descending for readability — ties broken by key so the
  // output is deterministic in tests.
  perConfigOut.sort((a, b) =>
    b.coverage - a.coverage || knobKey(a.knobs).localeCompare(knobKey(b.knobs)),
  );

  const globalVisited = [...globalCounts.keys()].sort();
  return {
    regime_labels: [...REGIME_LABELS],
    global: {
      regimes_visited: globalVisited,
      coverage: globalVisited.length / totalRegimes,
      counts: Object.fromEntries(globalCounts),
    },
    per_config: perConfigOut,
  };
}
