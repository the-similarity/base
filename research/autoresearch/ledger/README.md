# Experiment ledger

The ledger is the durable memory for autoresearch runs.

## Canonical writable file

Autonomous runs should append JSON lines to:

- `progress/autoresearch/experiments.jsonl`

That file is intentionally not pre-filled here. A checked-in example lives at:

- `progress/autoresearch/experiments.template.jsonl`

## Validation

Each JSON object should conform to:

- `experiment-ledger.schema.json`

## Rules

1. Append only.
2. Log failures and crashes, not only wins.
3. Never rewrite history to hide discarded ideas.
4. The evaluator and benchmark manifest used for a run must be named explicitly.
5. If a run is retried, create a new `run_id`.
