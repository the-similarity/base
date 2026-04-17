# Generator Comparison and Promotion

Part of [[synthetic_copies_v2|Copies v2]]. Implemented by Agent 2 in a ComparisonRunner module.

## Problem

Multiple synthetic generators exist (block bootstrap, regime bootstrap, Gaussian copula, future: TimeGAN, diffusion). Each has different strengths. The user should not have to manually compare scorecard outputs — the system should rank generators and recommend (or auto-promote) the best one for a given source dataset.

## How comparison works

1. **Run N generators** on the same source dataset with the same sample size and seed.
2. **Score each** with the three scorecards (fidelity, privacy, utility).
3. **Rank** by primary sort on fidelity_score descending, tiebreak by utility_gap ascending (lower gap = better utility transfer). Error-producing generators are ranked last.
4. **Promote** the winner: register a `DatasetSpec` in the platform registry with `source="synthetic:<run_id>"` and `dataset_id="promoted:<dataset_name>"` for O(1) lookups.

## Design decisions

- **Single composite metric** rather than Pareto front. Simpler to automate, easier to explain. The Pareto front is a future extension for users who want to trade off privacy vs. fidelity explicitly.
- **Seed-matched comparison.** All generators use the same seed so the only variable is the generation algorithm. This is not a perfect control (different generators interpret the seed differently) but it eliminates one source of variance.
- **No statistical significance test.** A single run per generator is compared. For high-stakes decisions, the user should run multiple seeds and compare distributions of scores. The ComparisonRunner supports this but does not enforce it.

## Promotion semantics

- Promotion creates a `DatasetSpec` via `the_similarity/synthetic/promotion.py`.
- `dataset_id` uses a hardcoded `"promoted:<dataset_name>"` prefix convention for O(1) lookups. This is a fragile convention, not a schema contract — see [[batch3 slop audit 2026-04-17]].
- `source` is set to `"synthetic:<run_id>"` linking back to the winning run.
- Only one dataset spec can be promoted per name at a time (upsert semantics).
- Promotion is advisory — the user can override.
- Re-running comparison with new generators or updated scorecards can change the promoted generator.

## Code path

- ComparisonRunner: implemented by Agent 2
- Demo: `examples/synthetic_copies_comparison.py`
- Integration test: `the_similarity/tests/test_synthetic_copies_v2.py`

## What's honest

- The composite metric is a heuristic. Equal weighting of fidelity, privacy, and utility gap is arbitrary.
- A single-seed comparison has high variance. Production use should sweep seeds.
- Promotion does not mean the generator is "good" — just the best of the candidates tested.
