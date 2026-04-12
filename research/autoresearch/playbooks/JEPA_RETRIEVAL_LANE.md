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
Keep a variant only if it improves the primary scorecard on at least one canonical slice **without** creating a severe regression elsewhere.

Discard if any of the following happens:
- CRPS worsens and calibration does not improve,
- observed retrieval improvements do not survive walk-forward validation,
- the variant depends on evaluator changes,
- runtime cost grows beyond the lane budget without commensurate gains.

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
