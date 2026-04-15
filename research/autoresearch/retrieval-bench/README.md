# Retrieval benchmark lane (`retrieval-bench/`)

A measurement lane that compares the current 9-method retrieval stack
against a Tier-1-only variant (SAX+MASS → DTW+Pearson) on representative
finance slices, and writes a keep/discard verdict using fixed decision
thresholds.

This lane does NOT change engine defaults. It is an audit that either
confirms Tier 2 is earning its CPU or flags it for further investigation.

## Files

- `slices.yaml` — slice spec + protocol + arms + thresholds.
- `run_bench.py` — harness runner. Evaluates each arm per slice and writes
  per-slice JSON artifacts plus a consolidated scorecard.
- `test_run_bench.py` — unit tests for metric computation and arm
  orchestration; runs without the full engine where possible.

## Outputs

- `progress/autoresearch/reports/retrieval-bench/<slice_id>-<arm_id>.json`
  — raw per-(slice, arm) metrics.
- `progress/autoresearch/reports/retrieval-bench-v1.md` — human-readable
  summary with tables and the keep/discard decision.
- A single append to `progress/autoresearch/experiments.jsonl` per run.

## Running

```bash
# smoke (fast, tiny trial count — use during development)
python research/autoresearch/retrieval-bench/run_bench.py --smoke

# full sweep (respects n_trials from slices.yaml)
python research/autoresearch/retrieval-bench/run_bench.py

# limit to a slice and arm
python research/autoresearch/retrieval-bench/run_bench.py \
    --slice spy-covid-2020 --arm tier1_only
```

## Invariants

1. Walk-forward only — history passed to the matcher is always
   `dataset[:query_start]`.
2. The same random seed produces the same trial positions per slice.
3. Arms share query positions within a seed so the comparison is paired.
4. Parquet paths are resolved from `--data-root` (default
   `the-similarity-data/data`) so the harness can run from any worktree.
