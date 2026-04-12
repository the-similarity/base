# Lane playbook template

Use this template when creating a new autoresearch lane.

## Lane identity
- **Lane ID:**
- **Benchmark ID:**
- **Question:**
- **Owner:**

## Write scope
- **Allowed:**
- **Forbidden:**

## Frozen evaluator
Name the benchmark manifest and the exact evaluation surface. During the lane run, do **not** change either.

## Budget
- max runtime per run:
- seed policy:
- trial count:
- compute ceiling:

## Scorecard
- primary metrics:
- secondary metrics:
- hard regressions that force discard:

## Keep / discard rule
Write the plain-language acceptance rule here.

## Run protocol
1. Read the benchmark manifest.
2. Record baseline metrics.
3. Make one bounded change.
4. Run the fixed benchmark.
5. Append a ledger entry.
6. Keep or discard.
7. Do not silently broaden scope.

## Required ledger fields
- `run_id`
- `benchmark_id`
- `lane_id`
- `status`
- `decision`
- `metrics_before`
- `metrics_after`
- `summary`
- `artifacts`

## Notes for future agents
Capture common failure modes, dead ends, and what should be tried next.
