# Phase 1 findings — 2026-04-14

First pass of executing the [[Pitch deck 414|April 14 plan]], Phase 1 (Finance wedge).
Three parallel worktree agents landed three PRs. This note is the compiled
research record: **what was asked, what was built, what the numbers said, what
we actually learned, and what is still open.**

Compiled from PRs #111 (1C), #113 (1A), #114 (1B). Related concept notes:
[[retrieval_bench]], [[projector_v2]], [[trust_filter]], [[finance_pilot]].

---

## Finding 1 — Tier 2 methods are a runtime sink without a measurable CRPS win (Track 1A)

### Setup

Lane: `retrieval_bench`, source `research/autoresearch/retrieval_bench/`.
Two arms, six slices planned, three run in the first (budget-capped) sweep:

| Arm | Methods | Role |
|-----|---------|------|
| `tier1_only` | SAX + MASS (prefilter) → DTW + Pearson | baseline |
| `tier1_plus_full` | Tier 1 + wavelet leaders + Koopman + EMD + TDA + transfer entropy | current default |

Slices exercised in the budget sweep:
- `spy-bull-2016-2019`
- `spy-covid-2020`
- `spy-rate-hike-2022`

Seed=42, 8 trials per slice. Walk-forward; no look-ahead. Engine defaults not
altered during measurement.

### Metrics

Per-slice metric set (engine-agnostic helpers in
`research/autoresearch/retrieval_bench/metrics.py`):

- **Forward-return correlation** — correlation between the query's realized
  next-forward-bars return and the weighted-match predicted return.
  Retrieval-quality proxy; rewards picking analogues whose forward paths
  actually resemble the query's.
- **CRPS with tails** — continuous ranked probability score on the projected
  quantile fan. Evaluates the *distribution*, not just the median.
- **Calibration error at P10/P90** — |empirical coverage − nominal|. Measures
  whether the cone actually contains what it claims to contain.
- **Hit rate** — directional accuracy of P50 vs realized.
- **Runtime p50 / p95** — wall-clock cost per query. Captured so quality gains
  can be priced against compute cost.

### Results

| Slice | ΔCRPS (t1+2 − t1) | Corr Δ | Runtime ×t1 |
|-------|-------------------|--------|-------------|
| `spy-bull-2016-2019` | ≈0 | −0.06 | 10.6× |
| `spy-covid-2020` | ≈0 | −0.18 | 46.0× |
| `spy-rate-hike-2022` | ≈0 | −0.12 | 54.3× |
| **mean** | **+0.00004** | **−0.12** | **37×** |

Ledger entry: `retrieval-bench-tiers-v1-2026-04-15T05:37:08Z`.

### Decision

Lane's keep/discard gates (4 gates, see [[Keep-discard thresholds]]):
- **Runtime** — fails: 37× mean > 3.0× budget.
- **CRPS majority** — fails: 1/3 slices improved, need ≥3.
- **Correlation** — fails: −0.12 mean drop.
- **Calibration** — flat.

**Verdict: `discard`** (preliminary). See
`progress/autoresearch/reports/retrieval-bench-v1.md`.

### What this actually tells us

- The claim "our 9-method tiered stack produces richer matches" is not visible
  in forecast quality *on SPY bar-level analogues*. The extra methods are
  spending compute without moving the downstream distribution.
- Correlation *dropped* with Tier 2 — i.e. Tier 2 can be **actively pulling
  rank order away** from the forward-return-useful matches that Tier 1 finds.
  That is worse than "Tier 2 is noise"; it is "Tier 2 is adversarial to our
  current retrieval target on this slice set."
- On COVID and rate-hike slices, Tier 2 runtime explodes (46-54×) because the
  Tier 2 methods are dense-per-window calculations; the slower they get, the
  *worse* they perform on the quality axis.

### What this does NOT tell us (yet)

- Non-equity behavior. BTC, ETH, FX not yet measured.
- Cross-asset retrieval quality. Tier 2 might be what saves us when the query
  symbol is thin and we need to borrow shape from another instrument.
- Regime-transition retrieval. The current slices are long-window regimes;
  Tier 2 (wavelets, TDA) may live or die on *transitions*, not inside them.
- Wider seed set. Seed=42 only. Seed=314 rerun is queued.
- Tier 2 weight tuning. The scorer uses fixed weights; a weight sweep is not
  what was measured. The bench measures "Tier 2 on vs off," not "Tier 2 with
  its weights right."

### Open questions for the follow-up lane

1. Does Tier 2 pull its weight on regime-transition slices (COVID-entry vs
   COVID-interior, Volmageddon, 2020-03 flash crash)?
2. Does Tier 2 pull its weight on cross-asset retrieval, where it is supposed
   to provide structure-aware shape borrowing?
3. Is it salvageable by reweighting, or should it be demoted from the default
   path to an opt-in enrichment layer?

### Action for the engine

**Do not change defaults yet.** This is one bench on one asset. But:

- Phase 2 (foundation-model bench lane) will re-test Tier 2's value against
  external baselines, making the "what is Tier 2 worth?" question even harder
  for Tier 2 to dodge.
- Budget-expanded rerun (NVDA, TSLA, BTC, seed=314, regime-transition cuts) is
  the next lane before we consider removing Tier 2 from the default path.
- If that second bench also fails Tier 2, we demote Tier 2 to opt-in (via
  `Config.enable_tier2` gate), and ship a ~37× faster default.

---

## Finding 2 — Adaptive conformal calibration is a real projector win (Track 1B)

### Setup

Lane: `projector_v2`, source `research/autoresearch/playbooks/PROJECTOR_V2_LANE.md`.
Benchmark manifest `research/autoresearch/benchmarks/projector-v2-core-v1.yaml`.

Five variants swept against `baseline` (the current
`the_similarity/core/projector.py` weighted-quantile cone):

| Variant | Module | Mechanism |
|---------|--------|-----------|
| `baseline` | `core/projector.py` | Fixed weighted-quantile cone. Reference. |
| `adaptive_conformal` | `core/projector_adaptive_conformal.py` | Gibbs-Candès online conformal update on recent coverage error. Widens when under-covered, narrows when over-covered. |
| `change_aware_conformal` | `core/projector_adaptive_conformal.py` | Same, with CUSUM-style change-point detection that resets the running coverage state on regime break. |
| `regime_aware_widening` | `core/projector_regime_aware.py` | Multiplicative cone widening per regime state from `core/regime.py`. |
| `joint_path` | `core/projector_joint_path.py` | Correlated path sampler; respects bar-to-bar path dependence instead of per-bar independent quantiles. |

Walk-forward, n_trials=15, window=50, forward_bars=20, top_k=5, on SPY-1d and
BTC-1d. The runner monkey-patches `api.project` per variant and restores it
afterward so the variant is tested via the exact same backtester path as
baseline. **This is a fairness invariant — if you add a variant later, do not
give it its own backtester wrapper.**

### Metrics

- **CRPS** — per-bar CRPS on the fan.
- **Calibration error P10/P90** — deviation from nominal coverage.
- **Joint-path CRPS** — path-level CRPS that respects bar-to-bar coherence.
  Penalizes "wiggling cones" that hit the right marginal quantiles but
  mis-shape the trajectory. Implemented in
  `the_similarity/core/metrics.py::joint_path_crps`.
- **Calibration error over time** — same as calibration error, but binned
  across the horizon. Penalizes variants that are well-calibrated terminally
  but miscalibrated mid-horizon. Implemented in the same module.
- **Hit rate, runtime** — standard.

### Results (synthetic-fallback v1 sweep)

Means across both slices. Negative CRPS Δ is good.

| Variant | ΔCRPS (vs baseline) | ΔCalib error P10/P90 | ΔJoint-CRPS | Runtime |
|---------|---------------------|----------------------|-------------|---------|
| `adaptive_conformal` | **−14%** | **−0.033** | ≈0 | ≈ baseline |
| `change_aware_conformal` | **−14%** | **−0.033** | ≈0 | ≈ baseline |
| `regime_aware_widening` | **+2.8%** | ≈0 | slightly worse | ≈ baseline |
| `joint_path` | **−2.8%** | **−0.017** | slightly worse | higher (MC) |

Ledger entries: `projector-v2-*-2026-04-15T05:20:38Z`. Full report at
`progress/autoresearch/reports/projector-v2-v1.md`.

### Decisions

- **`adaptive_conformal` → KEEP.** Large CRPS win, large calibration win, no
  joint-CRPS regression, no runtime penalty.
- **`change_aware_conformal` → KEEP, but duplicate of adaptive on smooth data.**
  Needs a shift-rich slice (COVID, rate-hike, flash events) to prove it
  diverges from the plain adaptive variant. Keep the code, bench-test it
  elsewhere before preferring it over plain adaptive.
- **`joint_path` → KEEP MARGINAL.** Small CRPS win but joint-CRPS actually
  regresses. The correlated sampler is shaping paths in a way that penalizes
  the joint metric — almost certainly a noise-calibration issue in the path
  generator. Tune the per-bar innovation variance next.
- **`regime_aware_widening` → DISCARD.** Default multiplicative factors are
  mis-fit to residuals and make the cone worse, not better. Don't promote
  unless someone redoes the factor fitting.

Baseline projector remains the default.

### Why we can't promote adaptive conformal to default yet

- Synthetic-fallback sweep, not real parquets. The synthetic generator is
  deterministic-Gaussian-ish; real market return distributions have fatter
  tails, regime shifts, and non-stationarity. A variant that wins on synthetic
  can fail on real. We need the real-data confirmation before flipping the
  default.
- Only two slices (SPY-1d, BTC-1d). We want to see it hold on crisis slices
  before promoting.
- Per-regime and per-asset calibration window sizes are still at defaults.
  Tuning window length (how much history adaptive conformal looks back) is
  its own bench.

### Why this is the most important finding of Phase 1

Calibration is the projector's job. If adaptive conformal cuts 14% of CRPS and
3.3 points of calibration error *before* tuning, this is the single largest
product-measurable lever we have touched. It is also the most portable — it
works on top of any underlying projector, so if we ever swap the quantile
cone for something else (joint path, learned), adaptive conformal still
applies on top.

### Open questions

1. How does adaptive conformal behave across regime breaks? (Exactly what the
   change-aware variant is for — we need the slice to prove divergence.)
2. What is the right window length for the online coverage update? Fixed at
   50 trials today.
3. Does adaptive conformal still win when the base projector is itself
   updated (e.g. joint_path or a learned backbone)?

---

## Finding 3 — Calibration-aware decision layer + trust filter (Track 1C)

### What was built

Three production-path modules added, **all opt-in, none change default
engine behavior**:

- `the_similarity/core/trust_filter.py` — the `TrustFilter.evaluate(...)`
  gate. Takes (match pool, projection, regime state). Emits
  `TrustDecision(trust: bool, reasons: list[str], score: float, signals: dict)`.
  Four signals:
    - **calibration MAE** — hard gate; too-recent miscoverage blocks trust.
    - **match-pool agreement** — dispersion signal; spread-out matches
      soft-penalize trust.
    - **regime novelty** — residual / distance to nearest training regime;
      high novelty soft-penalizes trust.
    - **sample size per bucket** — hard gate; too few analogues blocks trust.
- `the_similarity/core/decision_rules.py` — `CalibrationAwareStrategy` adapter
  that wraps any existing `Strategy`. Adds:
    - **Trust veto** — if `TrustFilter` says don't trust, flatten the signal
      or size it to zero.
    - **Tail-percentile entry threshold** — require P{k} > threshold for
      longs (default P25), P{k} < threshold for shorts (default P75),
      preventing entries at ambiguous points of the distribution.
    - **Size ∝ trust.score × confidence** — sizing is multiplicative in both.
      Low trust or low confidence shrinks position naturally.
    - `ReviewSummary` — plaintext audit artifact for the review step, one
      entry per decision, capturing signals → decision → outcome.
- `examples/finance_workflow_v1.py` — a runnable reference that chains
  `api.load` → `api.backtest` → `api.search` → `api.project` →
  `CalibrationAwareStrategy` → `summarise_review`. Runs end-to-end on sample
  data.

Pilot spec at `docs/planning/finance_pilot_v1.md` defines:
- Target user profile (small fund / prop trader, $5M-$500M AUM, daily
  equities, 2-10 day hold).
- Input/output surface of the pilot.
- **Four sign-a-pilot success gates**: coverage within 5pp of stated, hit
  rate ≥ 55%, veto rate 20-40%, Sharpe lift ≥ 0.3.
- Explicit non-goals.

### What this is and what it isn't

- **It is**: a runnable technical prototype of the search →
  project → trust-gate → decide → review loop. 28 new tests. Engine defaults
  untouched. Opt-in.
- **It is NOT**: a polished UI, an identified design partner, a tested
  pricing model, or a signed pilot. The spec defines *what a pilot would
  look like*; we have not put it in front of anyone.

### Why it matters

Before 1C the engine could produce a fan chart. That is not a decision.
Going from "here is a projection" to "here is a projection, here is whether
we trust it, here is what to do, here is the review artifact" turns the
output from a research object into the shape of a product. It is a necessary
precondition to design-partner conversations, but not sufficient for them.

### Open questions

1. The four trust signals are plausibly motivated but the weights and
   thresholds have not been bench-tuned. When we run pilots, we need to
   sweep trust thresholds on pilot P&L.
2. `veto rate 20-40%` is a guess for "sensible" — needs calibration against
   real strategy P&L, not toy data.
3. The review artifact is plaintext. For a pilot surface this needs to be
   structured (JSON) and diffable.

---

## Cross-cutting — what these three PRs together tell us about Phase 1

### Good signals

- The plan's rule #4 ("benchmark before belief") is already doing its job:
  1A is a real finding, not a vibe. Without the bench we would have kept
  paying 37× compute for nothing.
- The projector has a measurable upgrade path. Adaptive conformal is the
  most visible single-variable win we have seen.
- We now have a runnable shape of the decision surface, not just a cone.

### Warning signals

- The bench infrastructure itself is new code. Its honesty is only as good
  as the slice spec, metric code, and walk-forward invariants. All three
  lanes have tests, but bench-tooling bugs are the kind of bug that
  silently corrupts every decision that uses them. Peer-review of bench
  code is worth more here than peer-review of feature code.
- "Tier 2 is a runtime sink" is a strong claim on thin evidence. We must
  not act on it before the budget-expanded rerun, otherwise we'll have
  broken the same discipline we just created.
- Synthetic-fallback data for 1B is a real asterisk on the 14% CRPS win.
  The real-parquet confirmation sweep is **required** before promoting
  adaptive conformal to default.

### What Phase 2 needs to do

Phase 2 is the foundation-model benchmark lane (TimesFM, Chronos, Moirai,
MOMENT + one wavelet-aware). It should:

1. Reuse the 1A slice spec exactly — same slices, same seed set, same
   walk-forward protocol — so foundation-model numbers are directly
   comparable to our `tier1_only` and `tier1_plus_full` numbers already on
   the board.
2. Add the adaptive-conformal variant as the projector for the
   foundation-model retrieval arms, so if Tier 1 wins we know it is
   winning *with our best projector*, not against a hobbled one.
3. Record keep/discard decisions per (model × slice) cell into
   `progress/autoresearch/experiments.jsonl` using the same schema the
   1A/1B lanes already use.

## Code pointers

- Retrieval bench: `research/autoresearch/retrieval_bench/`
- Projector v2 lane: `research/autoresearch/scripts/run_projector_v2_sweep.py`,
  `research/autoresearch/benchmarks/projector-v2-core-v1.yaml`
- Projector variants:
  - `the_similarity/core/projector_adaptive_conformal.py`
  - `the_similarity/core/projector_regime_aware.py`
  - `the_similarity/core/projector_joint_path.py`
- Decision layer:
  - `the_similarity/core/trust_filter.py`
  - `the_similarity/core/decision_rules.py`
- End-to-end reference: `examples/finance_workflow_v1.py`
- Pilot spec: `docs/planning/finance_pilot_v1.md`
- Reports:
  - `progress/autoresearch/reports/retrieval-bench-v1.md`
  - `progress/autoresearch/reports/projector-v2-v1.md`

## Ledger query

All Phase 1 experiment rows:

```bash
grep -E '"run_id": "(retrieval-bench-tiers-v1|projector-v2-)' \
  progress/autoresearch/experiments.jsonl
```
