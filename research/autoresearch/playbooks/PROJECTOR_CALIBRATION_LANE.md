# Projector calibration lane

## Lane identity
- **Lane ID:** `projector-calibration-lane-v1`
- **Benchmark ID:** `projector-calibration-core-v1`
- **Question:** Can we improve forecast cone calibration and CRPS through projector tuning (confidence decay, Koopman blending, quantile interpolation, cone width scaling) without altering the retrieval pipeline?
- **Owner:** research

## Write scope
- **Allowed:**
  - `research/autoresearch/`
  - `progress/autoresearch/`
  - `the_similarity/core/projector.py`
  - `the_similarity/tests/`
- **Forbidden:**
  - `the_similarity/core/backtester.py`
  - `the_similarity/core/matcher.py`
  - `pyproject.toml`
  - benchmark manifest files during a run

## Frozen evaluator
Use `research/autoresearch/benchmarks/projector-calibration-core-v1.yaml` exactly as written during a lane run.

The evaluation surface is the existing walk-forward backtest API:

```python
from the_similarity.api import backtest
report = backtest(history, window_size=60, forward_bars=30, n_trials=100, seed=42)
```

Agents may build auxiliary calibration analysis around this, but they may not mutate the benchmark definition mid-run.

## Budget
- **Max runtime per run:** record wall-clock time; keep runs under 30 minutes per dataset slice.
- **Seeds:** `42` (primary), `314` (confirmation)
- **Trials:** `100` per canonical slice
- **Compute posture:** single-worker backtest to keep runtime deterministic and comparable across experiments.

## Scorecard
- **Primary metrics:**
  - `crps` (lower is better) -- gold-standard probabilistic forecast score
  - `calibration_error_p10_p90` (lower is better) -- mean absolute deviation of P10/P90 containment from nominal
- **Secondary metrics:**
  - `hit_rate` (higher is better) -- fraction of trials where P50 predicts the correct direction
  - `runtime_seconds` (lower is better) -- wall-clock time for the full backtest run
- **Hard regressions that force discard:**
  - CRPS increases by more than 10% relative to baseline
  - Hit rate drops below 45% (below chance after noise)

## Candidate experiment types

### EXP-1: confidence_decay_rate tuning
The projector fans out non-median percentile curves by `1 + decay_rate * bar`. The default is `0.0` (no decay). Grid search over `[0.01, 0.02, 0.03, 0.05, 0.08]` to find a value that widens the cone appropriately for long horizons without blowing it open at short horizons.

### EXP-2: Koopman blend weight tuning
The API blends Koopman operator evolution into P50 via `(1 - w) * P50 + w * koopman`. Default is `0.0`. Grid search over `[0.05, 0.10, 0.15, 0.20, 0.30]`. Hypothesis: small Koopman blending sharpens P50 for assets with dynamical structure, improving directional hit rate and CRPS.

### EXP-3: quantile interpolation method
`_weighted_quantile` currently uses piecewise-linear CDF center interpolation. Alternatives: midpoint interpolation, linear interpolation at edges, or Harrell-Davis kernel. Compare calibration and CRPS to see if a different quantile estimator improves cone coverage.

### EXP-4: cone width scaling
Instead of (or in addition to) linear confidence decay, apply a multiplicative scaling factor to the P10/P90 distance from median. A factor < 1.0 tightens an overwide cone; > 1.0 opens an overtight cone. This is orthogonal to decay_rate and can be combined as a second-pass correction.

## Keep / discard rule
Keep a variant only if it improves at least one primary metric on all canonical slices without creating a hard regression on either primary metric.

Discard if:
- CRPS worsens and calibration does not improve,
- cone looks visually "nicer" but scorecard metrics do not improve,
- variant depends on evaluator or retrieval changes (scope violation),
- runtime exceeds lane budget without commensurate metric gains.

## Run protocol
1. Read the benchmark manifest (`projector-calibration-core-v1.yaml`).
2. Record baseline metrics with default Config (decay=0.0, koopman_blend=0.0).
3. Make one bounded change to Config or `projector.py`.
4. Run the fixed benchmark via `run_projector_experiment.py`.
5. Append a ledger entry to `progress/autoresearch/experiments.jsonl`.
6. Keep or discard based on the rules above.
7. Do not silently broaden scope.

## Required ledger fields
- `run_id`
- `benchmark_id` (= `projector-calibration-core-v1`)
- `lane_id` (= `projector-calibration-lane-v1`)
- `status`
- `decision`
- `metrics_before`
- `metrics_after`
- `summary`
- `artifacts`

## Notes for future agents
- Start with EXP-1 (confidence_decay_rate) and EXP-2 (koopman_blend_weight) as they are simple Config overrides with no code changes.
- EXP-3 (quantile interpolation) modifies `projector.py` and needs a separate baseline comparison to isolate its effect.
- EXP-4 (cone width scaling) is a second-pass correction that can be combined with the best-performing decay rate.
- If calibration is already good at baseline, focus on CRPS improvement (sharpness).
- If calibration is poor (P90 containment far from 0.90), focus on cone width first.
- Always run both seeds before declaring a variant "kept".
