# Better engine research summary 414

## Executive summary

The Similarity should not evolve into a generic "forecast anything" model.

It should evolve into a **hybrid similarity operating system** with four layers:

1. **Analogue layer**  
   The current moat. Multi-method retrieval over history to find "what rhymes."

2. **Latent dynamics layer**  
   A world model that learns how states evolve, not just what they look like.

3. **Context layer**  
   Text, macro, event, prediction-market, and multivariate exogenous signals.

4. **Uncertainty / decision layer**  
   Adaptive conformal calibration, strategy logic, and scenario generation.

That architecture fits the five pillars in `vision/VISION.md` much better than trying to swap the engine for one foundation model.

The short version:

- **Keep** the current retrieval engine as the core primitive.
- **Add** foundation models as baselines, teachers, and auxiliary experts.
- **Push** JEPA and related methods toward world modeling, not retrieval.
- **Upgrade** the projector into a regime-aware, adaptive, multimodal uncertainty engine.
- **Treat** synthetic data and 3D data space as first-class products built on the same latent state representation.
- **Make** the public-good version a benchmark and tooling layer for honest, calibrated pattern-based forecasting across finance, health, climate, events, and personal narrative.

---

## What the repo already has

The current codebase is stronger than many "research idea" projects:

- `the_similarity/core/matcher.py` already implements a real tiered search pipeline.
- `the_similarity/core/projector.py` already turns retrieved futures into forecast cones.
- `the_similarity/core/ensemble.py` already has Monte Carlo, regime-conditional, and conformal ingredients.
- `the_similarity/config.py` already has feature-flag space for JEPA experiments.
- `research/autoresearch/` already gives the project a bounded keep/discard research OS.
- `research/autoresearch/playbooks/JEPA_WORLD_MODEL_LANE.md` already correctly reframes JEPA as a forward-dynamics problem, not a retrieval problem.

That means the goal is not "start modern ML."
The goal is to **stack new capabilities on top of a credible analogue engine**.

---

## Main research findings

## 1. Frontier time-series systems are becoming hybrid, not monolithic

The strongest current time-series foundation models are broad, flexible, and increasingly multimodal:

- **TimesFM 2.5** extends context to 16k, adds covariates, and supports both forecasting and embeddings through a unified decoder-only stack.
- **Chronos-2** moves beyond univariate forecasting toward multivariate and covariate-aware universal forecasting.
- **Moirai 2 / Moirai-MoE** push universal probabilistic forecasting and sparse mixture-of-experts routing.
- **MOMENT** emphasizes reusable time-series representations across tasks.
- **WaveMoE** and related wavelet-aware models show that explicit frequency structure is still valuable even in foundation-model form.

Implication for The Similarity:

- these models are **mandatory benchmarks**,
- likely useful as **teachers or side experts**,
- but they should not replace the analogue core by default.

The moat is still the self-similarity engine.

---

## 2. The world-model direction is correct, but retrieval is not the place to force it

The repo's current JEPA thesis is directionally right:

- retrieval JEPA was tried and killed,
- the remaining high-upside direction is **forward dynamics in latent space**.

Recent work supports exactly that shift:

- **TF-JEPA** moves toward predictive alignment between time and frequency views.
- **MTS-JEPA** emphasizes multi-resolution predictive learning and latent regime structure.
- **Var-JEPA / VJEPA** point toward probabilistic latent forecasting.
- **DynaMix** and related dynamical-systems work show that models built around system evolution, not just sequence fitting, can outperform standard TSFMs on dynamical tasks.

Implication:

JEPA should enter the engine, if it earns its place, as:

- a **world-model residual**,
- a **novelty / regime-break detector**,
- a **latent rollout generator**,
- or a **projector expert**.

It should **not** be reintroduced first as a 10th similarity score in the matcher just because that is easier to wire in.

---

## 3. The cone is the next major leverage point

Right now the engine mostly does this:

- retrieve analogues,
- weight them by confidence,
- compute per-bar weighted quantiles,
- optionally widen with simple confidence decay.

That is clean and interpretable, but the frontier has moved toward:

- **adaptive conformal prediction** under non-stationarity,
- **change-point-aware calibration**,
- **joint distribution modeling** instead of barwise-only quantiles,
- and **multi-source uncertainty composition**.

For this project, the next projector should blend at least three uncertainty sources:

1. analogue dispersion,
2. latent world-model uncertainty,
3. exogenous-context uncertainty.

That is a much stronger engine for both Finance and Synthetic Data.

---

## 4. Synthetic data is not a side quest; it is a training engine and product line

Pillar 2 is stronger than it may look.

Synthetic data can do three jobs:

1. **product**  
   Sell or expose faithful, privacy-audited synthetic datasets.

2. **research infrastructure**  
   Stress-test the engine on rare or extreme regimes.

3. **pretraining substrate**  
   Train world models and TS experts on synthetic worlds before grounding them on real data.

Recent work on synthetic-only or synthetic-heavy pretraining for time-series and dynamical systems suggests this is viable.

The key distinction:

- **Synthetic copies** should target statistical fidelity + privacy + downstream utility.
- **Synthetic worlds** should target controllability, scenario coverage, and causal diversity.

The current fractal / terrain subsystem is actually a clue here: the project already knows how to think in terms of procedural worlds.

---

## 5. 3D Data Space should be a product layer on top of latent state, not the core math

The right way to build Pillar 3 is:

- learn a high-dimensional latent state for windows / assets / domains,
- build a transition graph and nearest-neighbor graph in that space,
- project into 3D for navigation and explanation.

Do **not** make 3D the actual modeling space if higher-dimensional structure matters.

Why this matters:

- literal 3D is good for exploration,
- high-D latent structure is better for retrieval and forecasting,
- the combination gives both machine performance and human intuition.

This means `the-similarity-fractal/` can become a serious surface:

- state clusters become terrain regions,
- regime boundaries become ridges,
- transition probabilities become paths or flows,
- cross-domain correspondences become portals rather than just scatter points.

That is distinctive.

---

## 6. World Event Prediction is a multimodal forecasting problem, not only a market problem

If Pillar 4 is going to work, it needs three kinds of data:

1. **structured event streams**  
   GDELT-style event databases, knowledge graphs, geocoded narratives.

2. **crowd probabilities**  
   Prediction market prices, liquidity, order books, question histories.

3. **reasoned text context**  
   news, speeches, filings, public statements, policy documents.

The event-prediction engine should then do:

- analog retrieval over past event configurations,
- graph matching over causal / temporal event structures,
- and language-conditioned scenario ranking.

Prediction markets alone are not enough:

- many markets are sparse,
- some are illiquid,
- some are vulnerable to short-term manipulation,
- many important world events are never cleanly listed.

Historical event graphs alone are not enough:

- they lag,
- they miss crowd belief,
- they do not expose live market pricing.

The hybrid is the opportunity.

---

## 7. NL -> Time Series becomes real when you split it into stages

Pillar 5 becomes practical if you treat it as a pipeline:

1. **Narrative parsing**
   - extract events, sentiment shifts, intensities, durations, transitions

2. **Latent trajectory construction**
   - turn those events into a coarse state path

3. **Time-series rendering**
   - decode or retrieve likely trajectories from that latent path

4. **Calibration / editing**
   - let users tighten, smooth, anchor, or compare the rendered path

This matters because "one prompt -> one chart" is too ambiguous.
But "one prompt -> editable latent trajectory -> chart family" is usable.

The same stack can power:

- personal journaling time series,
- symptom and health narratives,
- macro / company narrative-to-scenario tools,
- and non-technical onboarding to the engine.

---

## Recommended architecture

## Layer 1: Analogue Retrieval Core

Keep and strengthen:

- `the_similarity/core/matcher.py`
- current 9-method stack
- feature-store caching
- explainable per-method confidence

Add:

- latent retrieval expert
- TS foundation-model expert
- context-aware retrieval routing

But keep analogue retrieval as the authoritative retrieval primitive.

## Layer 2: Latent Dynamics Core

Build a world-model lane with:

- JEPA-style predictive latent modeling
- time-frequency dual-view objectives
- regime prototypes / codebooks
- stochastic rollouts
- novelty residuals

This should primarily plug into projection and confidence, not replace matching first.

## Layer 3: Context Core

Add exogenous and multimodal inputs:

- macro series
- calendar events
- text/news embeddings
- prediction market states
- order flow / volume / liquidity
- medical or wearable streams for non-finance pillars

This layer should be optional and modular.

## Layer 4: Uncertainty Core

Upgrade the cone with:

- adaptive conformal calibration,
- change-point awareness,
- regime-conditional width control,
- copula or joint-path sampling,
- shock-conditioned scenarios.

This is where the system becomes "gift to the world" instead of just "interesting pattern matcher."

---

## Pillar-by-pillar recommendations

## Pillar 1: Finance

### What to build

- benchmark the engine against TimesFM, Chronos-2, Moirai 2 / Moirai-MoE, MOMENT, WaveMoE, and one finance-specific TSFM
- add a latent world-model residual to the projector
- add adaptive conformal and change-point-aware calibration
- add exogenous / text / event covariates to the projection stage
- add hybrid strategy logic that reacts to confidence collapse and novelty spikes

### What not to do

- do not replace the engine with a generic foundation model
- do not optimize for backtest aesthetics over calibration
- do not revive JEPA retrieval until the world-model lane proves itself

### Best product framing

"Analogue intelligence with honest uncertainty."

That is more defensible than "AI stock predictor."

## Pillar 2: Synthetic Data

### What to build

- synthetic copy lane:
  - conditional generative model trained on real series
  - fidelity scorecard
  - privacy leakage scorecard
  - downstream utility scorecard

- synthetic world lane:
  - procedural / latent market simulators
  - controllable regime knobs
  - rare-event curriculum generation
  - synthetic pretraining for world models and TS experts

### What not to do

- do not measure quality only with visual similarity
- do not claim "99% faithful" without privacy, memorization, and leakage testing
- do not collapse synthetic copies and synthetic worlds into one product

### Best product framing

"Generate useful futures, not just fake charts."

## Pillar 3: 3D Data Space

### What to build

- a shared latent state for windows, assets, domains, and modalities
- a state-transition graph
- 3D projection for exploration
- cross-domain nearest-neighbor search
- anomaly / boundary / transition visual layers

### Key design rule

The model space should stay high-dimensional.
The 3D view is a navigation and explanation surface.

### Best product framing

"A map of states, not a dashboard of indicators."

## Pillar 4: World Event Prediction

### What to build

- event ingestion from structured global event feeds
- prediction-market ingestion from market APIs and histories
- graph retrieval over event configurations
- text-conditioned scenario ranking
- live calibration against forecast-question outcomes

### What not to do

- do not trust only market prices
- do not trust only text reasoning
- do not skip graph structure

### Best product framing

"Find when the world has looked like this before, and what followed."

## Pillar 5: NL -> Time Series

### What to build

- narrative parser -> latent event sequence
- latent event sequence -> trajectory family
- editable chart rendering
- retrieval against similar narratives / histories
- private journaling / health / self-tracking modes

### Best product framing

"Turn human experience into analyzable time."

---

## What not to do

1. **Do not replace the moat.**  
   The current engine is differentiated because it is retrieval-first, multi-method, and explainable.

2. **Do not confuse 3D with representation.**  
   Use 3D as UI, not as the primary mathematical bottleneck.

3. **Do not ship synthetic data without privacy controls.**  
   Faithful copies can become memorization systems if unmanaged.

4. **Do not benchmark against only your own history.**  
   Use open external baselines and contamination-aware evaluation.

5. **Do not let context become spaghetti.**  
   Add text/event/prediction-market context as a modular layer with clear gating.

6. **Do not optimize cones by eye.**  
   Any projector change must win on calibration and CRPS.

---

## Suggested 90-day research program

## Month 1: benchmark and infrastructure

1. Add a `foundation-benchmark` research lane:
   - TimesFM 2.5
   - Chronos-2
   - Moirai 2 / Moirai-MoE
   - MOMENT
   - one wavelet-aware model

2. Add a `context-lane`:
   - macro features
   - text embeddings
   - event / market covariates

3. Add a `projector-v2` benchmark:
   - adaptive conformal
   - regime-aware width
   - joint-path sampling

## Month 2: world model and synthetic data

4. Continue the JEPA world-model lane:
   - multi-resolution
   - time-frequency
   - novelty residual

5. Add a `synthetic-copies` lane:
   - fidelity + privacy + downstream utility

6. Add a `synthetic-worlds` lane:
   - procedural market regimes
   - rare-event curriculum

## Month 3: product surfaces

7. Prototype 3D latent state exploration in `the-similarity-fractal/`
8. Prototype event-graph + prediction-market fusion
9. Prototype narrative -> trajectory editor
10. Publish a public benchmark / demo surface

---

## If the goal is a gift to the world

The highest-leverage public-good version of this project is not "best trading bot."

It is:

- an open benchmark for honest pattern-based forecasting,
- a privacy-aware synthetic time-series toolkit,
- a calibrated event forecasting surface,
- a narrative-to-time utility for people tracking health, mood, or life events,
- and an explainable state-space explorer across domains.

That means the public contribution could be:

1. an open evaluation harness,
2. open dataset cards and benchmark manifests,
3. calibration and explainability tooling,
4. privacy tests for synthetic time series,
5. and a clean research protocol for keep/discard experimentation.

That is genuinely useful even outside finance.

---

## Strongest recommendations in one list

1. Keep the current analogue engine as the core moat.
2. Add TS foundation models as baselines, teachers, and auxiliary experts.
3. Push JEPA into world-modeling, not matcher replacement.
4. Make adaptive conformal + regime-aware uncertainty the next projector upgrade.
5. Build synthetic copies and synthetic worlds as separate but connected lanes.
6. Turn the 3D surface into a latent-state explorer.
7. Build World Event Prediction as event graph + market + text fusion.
8. Build NL -> Time Series as a staged pipeline, not a one-shot gimmick.
9. Open-source the benchmarking, calibration, and privacy layers.

---

## Sources consulted

### Repo-local

- `vision/VISION.md`
- `the_similarity/config.py`
- `the_similarity/core/matcher.py`
- `the_similarity/core/projector.py`
- `the_similarity/core/ensemble.py`
- `research/autoresearch/playbooks/JEPA_WORLD_MODEL_LANE.md`
- `research/methods/06-jepa-joint-embedding-predictive-architecture.md`
- `docs/planning/JEPA_AUTORESEARCH_ENHANCEMENTS.md`

### External research and official docs

- [TimesFM repository](https://github.com/google-research/timesfm)
- [Chronos forecasting repository](https://github.com/amazon-science/chronos-forecasting)
- [uni2ts / Moirai repository](https://github.com/SalesforceAIResearch/uni2ts)
- [MOMENT repository](https://github.com/moment-timeseries-foundation-model/moment)
- [DynaMix / true zero-shot inference of dynamical systems](https://arxiv.org/abs/2505.13192)
- [WaveMoE](https://arxiv.org/abs/2604.10544)
- [MTS-JEPA](https://arxiv.org/abs/2602.04643)
- [TimeMaster](https://arxiv.org/abs/2603.13018)
- [TS-Haystack](https://arxiv.org/abs/2602.14200)
- [ForecastPFN / synthetic pretraining for zero-shot forecasting](https://arxiv.org/abs/2311.01933)
- [T2S / text-to-time-series](https://arxiv.org/abs/2505.02417)
- [VerbalTS](https://arxiv.org/abs/2503.10883)
- [Prediction Arena](https://arxiv.org/abs/2604.07355)
- [MIRAI](https://arxiv.org/abs/2407.01231)
- [Event-CausNet](https://arxiv.org/abs/2511.12769)
- [GDELT search and API surfaces](https://search.gdeltproject.org/index.html)
- [Polymarket developer docs](https://docs.polymarket.com/)
- [Kalshi developer docs](https://docs.kalshi.com/)
