# The Similarity — Plan April 14

This is the current roadmap from the April 14 research synthesis.

It is not a replacement for the historical implementation notes in
`docs/planning/plan.md`. It is the **forward execution plan** from the current
engine and vision state.

The core thesis remains:

- keep the analogue engine as the moat,
- make finance the proving ground,
- use rigorous benchmarking and calibration as the truth source,
- expand into other pillars only through reusable engine primitives.

---

## Planning rules

These rules govern the roadmap:

1. **Finance first**
   - The first commercial proof should come from the finance wedge.

2. **Engine first**
   - New work should strengthen the core engine before creating new product surfaces.

3. **Calibration over aesthetics**
   - Any projector or forecasting change must improve scorecard metrics, not just look better.

4. **Benchmark before belief**
   - Foundation models, world models, synthetic methods, and multimodal context must earn their place through controlled benchmarks.

5. **One primitive, many products**
   - Pillars 2–5 should reuse the same latent-state / similarity engine, not become unrelated systems.

---

## Strategic priorities

In order:

1. Improve the core finance engine
2. Build a real benchmarking and research loop
3. Upgrade the projector and uncertainty stack
4. Build world-model capability on top of the current engine
5. Stand up synthetic data as both product and research infrastructure
6. Extend into multimodal context, event prediction, and NL -> time-series
7. Build the 3D data-space surface once the latent representation is strong enough

---

## What not to do now

- Do not replace the analogue engine with a generic time-series foundation model
- Do not revive JEPA retrieval as the main direction
- Do not optimize chart visuals before calibration and CRPS improve
- Do not treat the five pillars as five equal execution tracks right now
- Do not build literal "3D-first" modeling before the high-dimensional latent state exists
- Do not promise synthetic fidelity without privacy and leakage checks

---

## Phase 0 — Immediate focus

Goal: create a disciplined execution base so the next technical bets are measurable.

### Tasks

- [ ] Create and maintain this plan as the canonical short-term roadmap
- [ ] Keep `vision/better_engine_research_summary_414.md` as the high-level strategy memo
- [ ] Keep `research/autoresearch/` as the bounded experimentation OS
- [ ] Track every serious experiment in `progress/autoresearch/experiments.jsonl`
- [ ] Refuse engine claims that are not backed by benchmark artifacts

### Done when

- the team can point to one roadmap,
- one benchmark source of truth,
- one experiment ledger,
- and one clear next task per track.

---

## Phase 1 — Strengthen the finance wedge

Goal: prove the engine is commercially and technically credible in finance.

### Track 1A — Retrieval and ranking

- [ ] Benchmark current matcher quality on representative finance slices
- [ ] Measure whether Tier 1 or Tier 2 is the true bottleneck
- [ ] Add side-by-side retrieval comparisons for current engine vs candidate methods
- [ ] Improve retrieval only if it survives walk-forward validation
- [ ] Keep the current multi-method analogue stack as the default retrieval primitive

### Track 1B — Projection and uncertainty

- [ ] Create `projector-v2` benchmark slices if needed
- [ ] Add adaptive conformal or change-aware conformal calibration experiments
- [ ] Test regime-aware cone widening
- [ ] Test joint-path generation instead of purely barwise quantiles
- [ ] Measure CRPS, calibration error, hit rate, and runtime for every variant

### Track 1C — Strategy and product proof

- [ ] Tighten strategy evaluation around calibration-aware decision rules
- [ ] Add "when not to trust the cone" logic
- [ ] Define what a usable finance pilot looks like
- [ ] Package one finance user workflow end to end: search -> projection -> decision -> review

### Done when

- the finance engine has a reproducible benchmark story,
- the projector is improving on real metrics,
- and at least one user workflow is strong enough to show a design partner.

---

## Phase 2 — Build the benchmark stack

Goal: make model and method comparisons cheap, honest, and repeatable.

### Track 2A — Foundation-model benchmark lane

- [ ] Create a benchmark lane for TimesFM, Chronos, Moirai, MOMENT, and one wavelet-aware model
- [ ] Compare them against the current engine on:
  - CRPS
  - calibration
  - directional accuracy
  - runtime
  - explainability value
- [ ] Use these models as baselines, not assumptions

### Track 2B — Report and decision discipline

- [ ] Standardize experiment reports
- [ ] Standardize baseline vs candidate deltas
- [ ] Add explicit keep / discard thresholds per lane
- [ ] Record rejected directions so they are not rediscovered later

### Track 2C — Slice quality

- [ ] Lock exact benchmark membership and date ranges
- [ ] Add regime-specific slices:
  - calm
  - crisis
  - trend
  - mean-reverting
- [ ] Add at least one cross-asset comparison slice

### Done when

- every major model or method question can be answered by running a named benchmark lane,
- and two different agents would reach the same keep/discard decision.

---

## Phase 3 — World-model lane

Goal: add forward-dynamics intelligence without breaking the analogue moat.

### Track 3A — JEPA / latent world model

- [ ] Continue the JEPA world-model lane only on forward-dynamics questions
- [ ] Test multi-horizon latent prediction
- [ ] Test time-frequency predictive alignment
- [ ] Test regime-conditioned latent transitions
- [ ] Test residual-based novelty or unfamiliarity scoring

### Track 3B — Integration path

- [ ] Keep world-model work outside the core matcher until it wins
- [ ] Prefer projector-side or confidence-side integration first
- [ ] Define integration seams for:
  - novelty penalty
  - projector expert
  - latent rollout uncertainty

### Track 3C — Decision rule

- [ ] Promote a world-model component only if it improves:
  - calibration,
  - CRPS,
  - or useful confidence behavior
- [ ] Do not promote it just because embeddings look interesting

### Done when

- a latent world-model component has a clear measured use in projection or confidence,
- without displacing the analogue engine prematurely.

---

## Phase 4 — Synthetic data

Goal: turn pillar 2 into both infrastructure and product.

### Track 4A — Synthetic copies

- [ ] Define a fidelity scorecard
- [ ] Define a privacy / memorization / leakage scorecard
- [ ] Define downstream-utility tests
- [ ] Generate first benchmarked synthetic-copy datasets

### Track 4B — Synthetic worlds

- [ ] Build controllable regime simulators
- [ ] Use them for rare-event curriculum generation
- [ ] Use them to stress-test projector and world-model behavior
- [ ] Explore synthetic pretraining for engine-side models

### Track 4C — Productization

- [ ] Decide first buyer and first use case for synthetic data
- [ ] Separate "sellable copies" from "internal research worlds"
- [ ] Avoid mixing their validation standards

### Done when

- synthetic data is no longer just a vision statement,
- and the project has both a research-internal synthetic pipeline and a product hypothesis.

---

## Phase 5 — Multimodal context

Goal: give the engine richer state awareness without losing the primitive.

### Track 5A — Context ingestion

- [ ] Add macro covariates
- [ ] Add volatility / volume / liquidity context
- [ ] Add text embeddings where useful
- [ ] Add event and market-state context for specific experiments

### Track 5B — Context-aware projection

- [ ] Test whether context improves projector behavior
- [ ] Test context-conditioned uncertainty widening
- [ ] Test whether context improves "when not to trust the analog" decisions

### Track 5C — Guardrails

- [ ] Keep context modular and optional
- [ ] Avoid entangling every pipeline path with every context source
- [ ] Require scorecard wins before making context default

### Done when

- exogenous context improves a measurable forecasting or confidence metric,
- and it integrates cleanly rather than turning the engine into spaghetti.

---

## Phase 6 — Pillar-specific expansion

Goal: expand beyond finance only after the engine layer is strong enough.

### Pillar 3 — 3D Data Space

- [ ] Learn or define a high-dimensional latent state representation
- [ ] Build nearest-neighbor and transition graphs in that space
- [ ] Project to 3D for exploration only after the latent manifold is credible
- [ ] Connect the 3D surface to real engine outputs rather than decorative visualization

### Pillar 4 — World Event Prediction

- [ ] Stand up event data ingestion
- [ ] Stand up prediction-market ingestion
- [ ] Define event-graph retrieval and matching tasks
- [ ] Add language-conditioned scenario ranking
- [ ] Validate against resolved forecasting questions

### Pillar 5 — Natural Language -> Time Series

- [ ] Build narrative parsing into structured event sequences
- [ ] Build latent trajectory generation from those sequences
- [ ] Render editable chart families, not fake precision
- [ ] Test on journaling, health, and personal analytics workflows

### Done when

- each expansion pillar uses the same shared engine concepts,
- rather than requiring a separate thesis and separate architecture.

---

## Phase 7 — Product and company milestones

Goal: convert technical differentiation into startup proof.

### Product milestones

- [ ] Pick the first narrow finance workflow to win
- [ ] Define the first design-partner profile
- [ ] Define the minimal paid offer
- [ ] Build demo flows that show:
  - search,
  - structural match reasoning,
  - projection,
  - uncertainty,
  - and decision relevance

### Company milestones

- [ ] Turn current pitch materials into a version with real metrics and design-partner proof
- [ ] Replace placeholders in fundraising docs with real evidence
- [ ] Keep the investor story tightly aligned to:
  - finance first,
  - engine as moat,
  - platform later

### Done when

- the company can show both technical proof and a believable commercial wedge,
- without depending on speculative claims.

---

## Recommended sequence of execution

This is the preferred order from here:

1. Improve finance evaluation and projector rigor
2. Stand up the foundation-model benchmark lane
3. Continue the JEPA world-model lane
4. Build synthetic-data scorecards and first pipelines
5. Add modular multimodal context
6. Expand into event prediction and NL -> time-series
7. Build the 3D latent exploration surface

---

## Immediate next tasks

These are the next tasks I would actually execute:

### Next 5

- [ ] Create a `foundation-benchmark` lane in `research/autoresearch/`
- [ ] Create a `context-lane` for macro, text, event, and prediction-market covariates
- [ ] Create a `projector-v2` lane for adaptive conformal and joint-path sampling
- [ ] Continue the JEPA world-model lane only on forward-dynamics benchmarks
- [ ] Add a synthetic-data scorecard covering fidelity, privacy, and downstream utility

### After that

- [ ] Define the first design-partner finance workflow
- [ ] Specify the latent-state interface needed for Pillar 3
- [ ] Specify the event-ingestion and event-resolution framework needed for Pillar 4
- [ ] Build the first staged narrative -> trajectory prototype for Pillar 5

---

## Decision checkpoints

Before moving to the next phase, answer these:

### Checkpoint A — finance proof

- Are forecast quality and calibration improving on real benchmarks?
- Is there a workflow users would actually pay for?

### Checkpoint B — world-model proof

- Does the latent model improve projection or confidence behavior?
- Or is it still just interesting research?

### Checkpoint C — synthetic-data proof

- Do synthetic outputs help training, stress testing, or customer use cases?
- Are privacy and leakage risks under control?

### Checkpoint D — platform proof

- Are new pillars reusing the same engine?
- Or are they drifting into separate startups?

---

## Success definition for the next stage

From here, success is not:

- more ideas,
- more pillars,
- or prettier visualizations.

Success is:

- one stronger finance engine,
- one benchmark discipline,
- one winning uncertainty upgrade,
- one credible world-model lane,
- and one roadmap where every expansion still compounds the same primitive.
