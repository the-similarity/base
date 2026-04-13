# JEPA world model lane

## Lane identity
- **Lane ID:** `jepa-world-model-lane-v1`
- **Benchmark ID:** `jepa-retrieval-core-v1` (reused — same datasets, different evaluation)
- **Question:** Can a JEPA encoder learn forward dynamics of financial time series in latent space — predicting how state A evolves into state B — enabling synthetic world generation?
- **Owner:** research

## Why world models, not retrieval

JEPA retrieval was tried and killed. Results:
- SPY: learned shape similarity (discrimination gap 0.177) but zero regime separation (0.023). DTW already does this, better and faster.
- BTC: total representation collapse on 326 windows.
- LeCun's own thesis: JEPA is about **predicting future states in latent space**, not pattern matching.

The actual value proposition: a JEPA world model that can **roll forward plausible market futures from a current state**, generate synthetic scenarios, and eventually power the forecast cone with learned dynamics instead of Koopman eigenvalue extrapolation.

## Write scope
- **Allowed:**
  - `research/autoresearch/`
  - `progress/autoresearch/`
  - `research/`
  - `the-similarity-playground/`
  - `the_similarity/examples/`
- **Forbidden:**
  - `the_similarity/core/` (all production code)
  - `the_similarity/api.py`
  - `pyproject.toml`
  - benchmark manifest files during a run

## Research question hierarchy

### Q1: Can JEPA learn forward dynamics? (do this first)
- Train encoder on window pairs (t, t+Δ) where Δ = forward_bars
- Predictor takes latent(window_t) → predicts latent(window_{t+Δ})
- Loss: cosine distance between predicted and actual future latent
- **Success metric:** prediction error on held-out test windows
- **Baseline:** naive persistence (predict latent stays the same)

### Q2: Does it learn regime-aware dynamics?
- Check: do windows from different volatility regimes cluster separately in latent space?
- Check: does the predictor produce different trajectories for calm vs volatile starting states?
- **Success metric:** regime separation > 0.10 (our retrieval experiment got 0.023)

### Q3: Can it generate plausible synthetic futures?
- Given a current state, roll the predictor forward N steps in latent space
- Decode latent trajectories back to price-space (requires a decoder — new component)
- Compare synthetic trajectories against actual futures: distributional similarity, volatility structure
- **Success metric:** synthetic returns have similar distributional properties to real (KS test p > 0.05)

### Q4: Does it beat Koopman for the forecast cone?
- Compare JEPA-generated cone vs Koopman eigenvalue cone on walk-forward calibration + CRPS
- This is where it could eventually enter production
- **Success metric:** same thresholds as autoresearch framework (CRPS improvement ≥ 0.005, calibration regression ≤ 0.02)

## Architecture (proposed)

```
Window at time t          Window at time t+Δ
      │                          │
  [Encoder]                  [Encoder] (EMA target)
      │                          │
   z_t (latent)              z_{t+Δ} (latent target)
      │                          │
  [Predictor]                    │
      │                          │
   ẑ_{t+Δ} (predicted) ──loss── z_{t+Δ}
```

Key differences from the retrieval prototype:
- **Temporal pairs, not masked reconstruction.** The predictor learns t→t+Δ dynamics, not "fill in the blank."
- **Variable Δ.** Train with multiple forward horizons (5, 10, 20, 30 bars) to learn multi-scale dynamics.
- **Decoder** (for Q3): latent → price-space. Simple MLP or 1D transposed CNN.
- **Regime conditioning** (for Q2): optionally condition the predictor on a regime indicator (volatility quantile).

## Budget
- **Seeds:** `42`, `314`
- **Minimum data:** ≥ 2000 windows per dataset (BTC collapsed at 326 — require 6x minimum)
- **Training:** start with frozen encoder approach; if dynamics learning requires it, allow fine-tuning
- **Max runtime per experiment:** 30 minutes on CPU

## Keep / discard rule

Same numeric threshold machinery as the autoresearch framework. Thresholds defined in
`research/autoresearch/benchmarks/jepa-retrieval-core-v1.yaml`.

**Additional world-model-specific gates:**
- Dynamics prediction error must beat naive persistence baseline
- Regime separation must exceed 0.10 (retrieval got 0.023 — that's the bar to clear)
- Generated synthetic trajectories must pass basic distributional sanity checks

## Candidate experiments (ordered)
1. `temporal_predictor_baseline` — simple t→t+30 prediction, single Δ
2. `multi_horizon_predictor` — multi-scale Δ ∈ {5, 10, 20, 30}
3. `regime_conditioned_predictor` — condition on volatility regime
4. `decoder_rollout` — add decoder, generate synthetic futures
5. `koopman_comparison` — compare forecast cone against Koopman

## Suggested ledger names
- `world_model_temporal_baseline`
- `world_model_multi_horizon`
- `world_model_regime_conditioned`
- `world_model_synthetic_rollout`
- `world_model_vs_koopman`

## Minimum ledger payload
Every run: benchmark id, run id, code version, slices evaluated, metrics before/after,
dynamics prediction error, regime separation score, keep/discard decision, rationale.

## Notes for future agents
- **Do NOT revisit retrieval.** It was tested and killed. See the deletion commit for rationale.
- Start with Q1 (can it learn dynamics at all?) before anything else.
- If temporal prediction error doesn't beat persistence, STOP. The architecture doesn't fit.
- The fractal terrain engine (`the-similarity-fractal/`) is a parallel world-model effort in a different domain — look for shared abstractions.
- Minimum 2000 windows per dataset. If a dataset is too small, skip it.
