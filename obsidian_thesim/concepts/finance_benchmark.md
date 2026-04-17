# Finance Benchmark

## What it is

The **benchmark CLI** (Agent 4) runs standardized backtests across one or more symbols and registers every result in the platform registry. It answers: "how does the similarity engine perform on SPY vs QQQ vs IWM under controlled conditions?"

## How to run

### Single symbol

```bash
python -m the_similarity.finance.benchmark run \
  --symbol SPY \
  --n-trials 50 \
  --seed 42 \
  --window-size 60 \
  --forward-bars 20
```

This runs a backtest on SPY, registers the result, and prints the run_id + headline metrics.

### Multi-symbol sweep

```bash
python -m the_similarity.finance.benchmark sweep \
  --symbols SPY,QQQ,IWM \
  --n-trials 50 \
  --seeds 42,314
```

Sweeps run one backtest per (symbol, seed) pair. Each result is independently registered. The CLI prints a summary table at the end.

### Query results

```bash
# List all finance runs
python -m the_similarity.platform list --kind finance

# Show details of a specific run
python -m the_similarity.platform show <run_id>

# Compare two runs
python -m the_similarity.platform compare <run_id_a> <run_id_b>
```

## What the sweep does

1. For each symbol in the list, load the historical daily CSV.
2. For each seed, run `api.backtest(register=True)` with the specified parameters.
3. Collect all run_ids and fetch their summaries from the registry.
4. Print a comparison table: symbol, seed, hit_rate, crps, coverage, trust_score.
5. Optionally compute cross-symbol aggregates (mean hit_rate, worst calibration).

## How results register

Each benchmark run creates one `RunArtifact(kind=FINANCE)` in the registry with:

- `config`: `{symbol, window_size, forward_bars, n_trials, top_k}`
- `summary`: `{hit_rate, crps, coverage, calibration, trust_score, calibration_grade, pillar: "finance"}`
- `provenance`: `{generator_name: "the_similarity.finance.benchmark", source_id: <symbol>}`
- `seed`: the RNG seed used

Sweep runs are independent rows, not grouped under a parent `SWEEP` kind. This keeps the registry flat and queryable without parent-child joins.

## Code paths

- Benchmark CLI: `the_similarity/finance/benchmark.py` (Agent 4)
- Finance adapter: `the_similarity/platform/adapters/finance.py`
- Registry: `the_similarity/platform/registry.py`

## Related

- [[trust_artifact]] — trust_score computed per benchmark run
- [[calibration_artifact]] — calibration quality tracked per symbol
- [[finance_review]] — benchmark results can be reviewed before acting
- [[finance_pilot]] — earlier concept note on the finance pilot scope
