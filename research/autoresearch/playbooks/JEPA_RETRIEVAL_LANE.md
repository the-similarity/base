# JEPA retrieval lane

## Lane identity
- **Lane ID:** `jepa-retrieval-lane-v1`
- **Benchmark ID:** `jepa-retrieval-core-v1`
- **Question:** Does a frozen JEPA-style latent representation improve analog retrieval quality and downstream walk-forward scorecard metrics before production integration?
- **Owner:** research

## Write scope
- **Allowed:**
  - `research/autoresearch/`
  - `progress/autoresearch/`
  - `research/`
  - `the-similarity-playground/`
  - `the_similarity/examples/`
- **Forbidden:**
  - `the_similarity/core/backtester.py`
  - `the_similarity/api.py`
  - `pyproject.toml`
  - benchmark manifest files during a run

## Frozen evaluator
Use `research/autoresearch/benchmarks/jepa-retrieval-core-v1.yaml` exactly as written during a lane run.

The evaluation surface is the existing walk-forward backtest API:

```python
from the_similarity.api import backtest
report = backtest(history, window_size=60, forward_bars=30, n_trials=100, seed=42)
```

Agents may build auxiliary retrieval analysis around this, but they may not mutate the benchmark definition mid-run.

## Budget
- **Max runtime per run:** choose a fixed ceiling before the lane starts and keep it constant for all compared runs.
- **Seeds:** `42`, `314`
- **Trials:** `100` per canonical slice
- **Compute posture:** frozen or lightly-tuned encoder first; avoid full end-to-end production training loops in the initial lane.

## Baseline protocol
1. Record baseline retrieval and walk-forward metrics with no JEPA signal.
2. Save the exact config / artifact identifier used.
3. Log the baseline to the ledger before comparing JEPA variants.

## Candidate experiment types
- frozen embedding cosine similarity rerank
- predictor residual as novelty score
- time-domain latent encoder only
- time + frequency dual-view latent encoder
- multi-resolution objective variants

## Keep / discard rule

Decisions are governed by **strict numeric thresholds** defined in the benchmark file
`research/autoresearch/benchmarks/jepa-retrieval-core-v1.yaml` under the `thresholds:` key.
Two agents reading the same before/after metrics must reach the same verdict.

### Numeric gates (summary — source of truth is the YAML)

| Gate | Value | Meaning |
|------|-------|---------|
| `min_crps_improvement` | 0.005 absolute | CRPS must drop by at least this much to count |
| `max_calibration_regression` | 0.02 absolute | Calibration must not worsen beyond this |
| `max_runtime_multiplier` | 2.0x | Runtime ratio ceiling |
| `min_slices_improved` | 1 | At least one canonical slice must improve |
| `walk_forward_required` | true | Retrieval lift must survive walk-forward |

### KEEP when ALL of
1. At least `min_slices_improved` canonical slices show CRPS improvement >= `min_crps_improvement`.
2. No slice shows calibration regression > `max_calibration_regression`.
3. Runtime ratio <= `max_runtime_multiplier`.
4. Walk-forward backtest confirms the improvement.

### DISCARD when ANY of
- CRPS worsens and calibration does not compensate.
- Retrieval improvements do not survive walk-forward validation.
- The variant depends on evaluator changes rather than model changes.
- Runtime exceeds the `max_runtime_multiplier` ceiling.
- Calibration regresses beyond `max_calibration_regression` on any slice.

### Automated validation
Run the validation script to get a deterministic verdict:

```bash
python research/autoresearch/scripts/validate_decision.py \
  --benchmark research/autoresearch/benchmarks/jepa-retrieval-core-v1.yaml \
  --before '{"crps": 0.339, "calibration_error_p10_p90": 0.50, "runtime_seconds": 3.7}' \
  --after  '{"crps": 0.330, "calibration_error_p10_p90": 0.49, "runtime_seconds": 4.0}'
```

## Suggested ledger summary format
- `baseline`
- `frozen_latent_rerank`
- `latent_rerank_plus_novelty_penalty`
- `time_frequency_dual_view`

## Minimum ledger payload
Every run should capture:
- benchmark id
- run id
- code/artifact version
- slices evaluated
- metrics before
- metrics after
- keep/discard decision
- short rationale

## Notes for future agents
- Start with retrieval-only JEPA. Do not jump straight to replacing the core matcher.
- Treat predictor residual as a possible **confidence control**, not automatically a ranking score.
- If a latent model looks better only on one dramatic anecdote, that is not enough to keep it.
- Prefer simple frozen-encoder ablations before probabilistic or variational JEPA.
