# Better engine research summary 414

**One breath:** do not turn The Similarity into "just another forecasting model." Make it a **hybrid similarity operating system**: analogue retrieval + latent world model + adaptive uncertainty + multimodal context.

## Core thesis

The repo already has a real moat:
- multi-method analogue retrieval in `the_similarity/core/matcher.py`
- empirical cone construction in `the_similarity/core/projector.py`
- blended uncertainty machinery in `the_similarity/core/ensemble.py`
- a bounded research OS in `research/autoresearch/`

The frontier move is **not** replacing that with one black-box TS foundation model.

The frontier move is:
1. keep [[Self-similarity]] as the primitive,
2. add a **world-model lane** on top of it,
3. add a **foundation-model benchmark / teacher lane** beside it,
4. add **text, event, and exogenous context** as a new modality,
5. upgrade uncertainty from static cones to **regime-aware adaptive conformal**,
6. use [[Karpathy autoresearch]] discipline for every research lane.

## Strongest findings

### 1. Finance moat stays retrieval-first

Use Chronos-2, TimesFM 2.5, Moirai 2 / Moirai-MoE, MOMENT, WaveMoE, and similar models as:
- baselines,
- teachers,
- feature sources,
- and routing experts.

Do **not** let them erase the engine identity. The moat is still "find the past that rhymes with the present, then project honestly."

### 2. JEPA is more promising as a world model than as retrieval

This matches the repo's current direction in [[JEPA]] and [[JEPA integration surface]].

Best next version:
- multi-resolution latent prediction,
- time-frequency predictive alignment,
- regime prototypes / codebooks,
- probabilistic latent rollouts,
- residual-based novelty penalties for confidence control.

### 3. The cone needs a harder uncertainty upgrade

Current cone logic is empirical and clean, but frontier systems are moving toward:
- adaptive conformal under non-stationarity,
- regime-aware widening,
- joint-path generation instead of barwise-only quantiles,
- hybrid uncertainty from analog dispersion + latent dynamics + exogenous shock context.

### 4. Synthetic data should become a first-class product lane

Two sub-products:
- **Synthetic copies:** statistically faithful but privacy-audited market / sensor / behavioral data.
- **Synthetic worlds:** controllable fractal or latent environments for pretraining, stress testing, and agent simulation.

Important guardrail: "99% faithful" without a privacy leakage meter is dangerous.

### 5. 3D Data Space should be an interface over high-D latent state

Do not force the core representation to literally live in 3D.

Instead:
- learn a high-dimensional latent manifold,
- build a state graph / neighborhood graph on top,
- project to 3D for exploration,
- let users move through clusters, transitions, and regime boundaries.

This makes the existing fractal / 3D surface a product advantage rather than a side project.

### 6. World Event Prediction needs three data streams, not one

Build it from:
- event databases / knowledge graphs,
- prediction market prices and order books,
- text reasoning over news, filings, speeches, and narratives.

Prediction markets alone are too gameable and sparse.
Historical event graphs alone are too slow.
The hybrid is the opportunity.

### 7. NL -> Time Series is real if we break it into stages

Do not aim first for "one prompt in, magical chart out."

Aim first for:
1. narrative -> structured latent event sequence,
2. event sequence -> coarse trajectory,
3. coarse trajectory -> calibrated uncertainty band,
4. optional retrieval against similar personal or public histories.

## Best bets

- Hybrid retrieval stack: analogue search + latent retrieval + TS foundation model experts
- JEPA/world-model lane for forward dynamics, not for replacing DTW
- Adaptive conformal cone calibration
- Multimodal context ingestion: macro, text, news, event, prediction market, sensor
- Synthetic-world pretraining for rare regimes and stress scenarios
- 3D latent exploration layer built on top of the same shared state representation

## Bad bets

- Replacing the engine with a generic TSFM
- Re-running JEPA retrieval as if the earlier failure did not happen
- Optimizing cone visuals without scorecard improvement
- Building a literal 3D storage format instead of a high-D latent manifold
- Promising "perfect" synthetic copies without privacy and memorization audits

## Immediate next tasks

1. Create a `foundation-benchmark` lane in `research/autoresearch/` for Chronos-2, TimesFM, Moirai, MOMENT, and one wavelet-aware model.
2. Create a `context-lane` for text / event / prediction-market covariates.
3. Create a `projector-v2` lane for adaptive conformal and joint-path sampling.
4. Continue the JEPA world-model lane, but only on the forward-dynamics question.
5. Add a synthetic-data scorecard: fidelity, calibration, downstream utility, privacy leakage.
6. Design the 3D Data Space as a view over latent state transitions, not as a separate engine.

## Useful links

- `vision/VISION.md`
- `vision/better_engine_research_summary_414.md`
- `the_similarity/core/matcher.py`
- `the_similarity/core/projector.py`
- `the_similarity/core/ensemble.py`
- `research/autoresearch/playbooks/JEPA_WORLD_MODEL_LANE.md`
- `research/autoresearch/benchmarks/projector-calibration-core-v1.yaml`

## Related notes

- [[Self-similarity]]
- [[JEPA]]
- [[JEPA integration surface]]
- [[Karpathy autoresearch]]
