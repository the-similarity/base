# Synthetic demos

Two canonical commands that exercise the synthetic-copies and synthetic-worlds
pipelines end-to-end. Both are deterministic given their seed and are designed
to run on a fresh clone with no manual setup.

## Copies demo

```bash
python -m the_similarity.synthetic.cli \
  --input the_similarity/synthetic/demos/sample.csv \
  --n 500 --seed 42 \
  --out artifacts/demo-copies
```

Loads the shipped `sample.csv` fixture (500 rows, `price` + `volume`, generated
with `numpy.random.default_rng(42)`), fits the default generator, samples 500
synthetic rows, and scores fidelity/privacy/utility. Outputs land under
`artifacts/demo-copies/<generator>-<seed>-<YYYYMMDD-HHMMSS>/`:

- `real.parquet` — source data replayed verbatim
- `synth.parquet` — generated synthetic series
- `scorecard.json` — machine-readable fidelity/privacy/utility report
- `report.md` — human-readable summary
- `provenance.json` — standalone reproducibility record (source, seed, version)

## Worlds demo

```bash
cd the-similarity-fractal && \
  npm run sim:headless -- \
    --scenario scenarios/small_village.json \
    --seed 42 --steps 500 \
    --out artifacts/demo-worlds.jsonl
```

Runs the headless synthetic-worlds simulator for 500 ticks of the bundled
`small_village` scenario. Output is a single JSONL stream at
`artifacts/demo-worlds.jsonl` containing a `provenance` header line, one
`tick` record per step, and a final `summary` line — sufficient to replay or
audit the run without the full 3D engine.
