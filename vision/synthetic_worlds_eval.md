# Synthetic Worlds Eval — Design Note

Scope: `the-similarity-fractal/src/eval/`. Companion to the copies-side eval
defined in `the_similarity/synthetic/` (Python). This note captures the
shape of the MVP and the intent behind each module — implementation lives
in the source files and their module docstrings.

## Why

The worlds runner produces a stream of telemetry per tick. That answers
"what happened." It does not answer the two questions a product user
actually asks:

1. **Did the scenario knobs cover the dynamical regimes we care about?**
2. **Do the knobs actually move the observables — or are they cosmetic?**

World Eval exists to answer those two questions and to emit a
reproducible artifact that downstream reporting can render side-by-side
with the copies-side fidelity / privacy / utility scorecards.

## Pieces

- `sweep.js` — Cartesian product over a knob grid × seed list. Pure
  function; runs each cell against the headless world and returns flat
  JSONL-shaped telemetry rows.
- `regime-coverage.js` — Bins each row into a discrete 9-way regime on
  two axes (population health × mean energy) and reports, per knob
  configuration, the fraction of regimes visited.
- `controllability.js` — For each numeric knob × metric pair, computes
  Pearson r between the knob value and the terminal-window mean of the
  metric, plus a permutation p-value. This is the honest "does this
  knob move this metric?" test.
- `scorecard.js` — JSON artifact in the shape of the Python
  `Scorecard` dataclass (`kind: "worlds"`) so a unified report renderer
  can ingest both sides. Always carries `provenance`.
- `provenance.js` — Seed / generator identity / params / ISO timestamp
  record. Mirrors the Python `Provenance` dataclass field-for-field.

## Artifact layout

```
<out>/sweep-<id>/
  scorecard.json     # ~5 KB — regime coverage + controllability + provenance
  cells.json         # knobs + seed per cell
  telemetry.jsonl    # one row per tick per cell (optional — skip for CI)
```

See `the-similarity-fractal/artifacts/sweep-example/sweep-example/` for a
committed reference from a 2×3 grid × 3 seeds × 120 ticks run.

## Non-goals (MVP)

- No time-series similarity between worlds (that is the Similarity
  engine's job; world-eval only surfaces whether sweeps covered space).
- No multivariate regression — first-order Pearson + permutation is good
  enough to flag cosmetic knobs. Partial-effect / interaction analysis
  can be added later without changing the artifact shape.
- No streaming — sweeps materialize in memory. Fine for grids of a few
  hundred cells. If we sweep larger grids we'll stream cells to disk.
