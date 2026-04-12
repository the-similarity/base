# JEPA baseline runbook

Use this runbook to create the first baseline before any JEPA signal is added.

## Purpose

Record a reproducible walk-forward baseline using the current public engine surface.
This baseline is the comparison point for future JEPA retrieval experiments.

## Official baseline command

Run from repo root:

```bash
MPLCONFIGDIR=/tmp/mpl-autoresearch \
python research/autoresearch/scripts/run_baseline_backtest.py \
  --datasets \
    the-similarity-data/data/stocks/spy/1d.parquet \
    the-similarity-data/data/crypto/btc_usdt/1d.parquet \
  --window-size 60 \
  --forward-bars 30 \
  --n-trials 100 \
  --seed 42 \
  --report-name baseline-jepa-report.json \
  --append-ledger
```

Artifacts produced:
- `progress/autoresearch/reports/baseline-jepa-report.json`
- `progress/autoresearch/experiments.jsonl`

## Smoke-test command

Use this only to verify the pipeline and script wiring quickly:

```bash
MPLCONFIGDIR=/tmp/mpl-autoresearch \
python research/autoresearch/scripts/run_baseline_backtest.py \
  --datasets progress/autoresearch/fixtures/spy-mini-400.parquet \
  --window-size 30 \
  --forward-bars 10 \
  --n-trials 1 \
  --report-name smoke-baseline-jepa-report.json
```

## Rules

- Do not change the benchmark manifest during the run.
- Do not mutate the evaluator while establishing the baseline.
- Log the baseline before any JEPA rerank or novelty experiment.
- Treat smoke-test results as wiring evidence only, not as the canonical baseline.
