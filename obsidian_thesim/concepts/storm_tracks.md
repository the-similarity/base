# Storm Tracks Self-Similarity (HURDAT2)

Second experiment in the "abstracting the spark" research arc. The
first experiment ([[trajectory_3d]] / PR #301) showed the
self-similarity primitive — DTW on Frenet (κ, τ) descriptors with
weighted analogue cone forecast — beats persistence, linear
extrapolation, and random-analogue baselines on **synthetic** 3D
agent trajectories. This one tests the same primitive on
**real-world** 3D paths: NOAA HURDAT2 Atlantic-basin hurricane
tracks (1851–2023, public domain).

## Code

- `the-similarity-data/scripts/fetch_hurdat2.py` — download + parse + write parquet
- `the-similarity-data/fixtures/hurdat2-tiny.txt` — 10-storm fixture for CI parser tests
- `the_similarity/datasets/storm_tracks.py` — parquet → 3D `Storm` objects
- `the_similarity/tests/test_hurdat2_parser.py` — parser unit tests (18 cases)
- `the_similarity/tests/test_storm_tracks_dataset.py` — dataset / projection unit tests
- `the_similarity/tests/test_trajectory_3d_storms.py` — headline backtest (slow)
- `the_similarity/tests/test_trajectory_3d_storms_ablation.py` — z-scale ablation (slow)
- `the_similarity/platform/adapters/storms.py` — registry adapter (kind=EVENTS)
- `the_similarity/tests/test_storm_adapter.py` — adapter smoke tests

## Hypothesis

> The same primitive (Frenet (κ, τ) + DTW + weighted cone) that
> worked on synthetic agents in PR #301 generalizes to real
> hurricane tracks.

## Data

- **Source:** NOAA NHC HURDAT2 (`https://www.nhc.noaa.gov/data/hurdat/hurdat2-atl-1851-2023-042624.txt`)
- **Format spec:** `https://www.nhc.noaa.gov/data/hurdat/hurdat2-format-atl.pdf`
- **Volume after `min_fixes=8` filter:** 1,851 storms / 54,180 fixes
- **Train / test split:** chronological, year ≤ 2010 train (1,629 storms) / year > 2010 test (222 storms, subsampled to 100 with seeded RNG)
- **Cadence:** 6-hourly fixes (some intermediate fixes at landfall)

## 3D embedding

Per-storm equirectangular projection at the storm's centroid:

```
centroid_lat = mean(lats)
x_km = (lon - centroid_lon) * 111.32 * cos(centroid_lat * π/180)
y_km = (lat - centroid_lat) * 111.32
z    = max_wind_kt * Z_SCALE
```

Why **per-storm centroid:** keeps projection distortion < 0.5%
within the storm's footprint without entangling cross-storm
similarity with absolute geographic position. The Frenet (κ, τ)
descriptors are translation- and rotation-invariant, so the
centroid choice does not affect shape rankings.

Why **`max_wind` (not pressure)** for z: max_wind is the canonical
storm-strength metric AND has denser missing-value patterns in the
historical record (older storms often lack pressure but always
report wind). The third axis must be defined on most fixes for it
to carry useful signal.

## Normalization is load-bearing

Frenet (κ, τ) is rotation/translation/uniform-scale invariant but
**NOT per-axis-scale invariant**. Z_SCALE choice changes the
geometry. We ablated four values (`0.0`, `1.0`, `5.0`, `25.0`).

## Headline numbers (K=4, J=4, 641 trials per cell)

```
                    z=0.0   z=1.0   z=5.0   z=25.0
persistence MAE     320.8   320.8   320.8   320.8     km
linear MAE          177.3   177.3   177.3   177.3     km
random_analogue MAE 314.2   313.9   313.9   313.9     km
model MAE           297.5   303.5   322.0   325.6     km

persistence hit     0.017   0.017   0.017   0.017
linear hit          0.016   0.016   0.016   0.016
random_analogue hit 0.435   0.438   0.438   0.438
model hit           0.413   0.448   0.393   0.363

persistence CRPS    0.295   0.295   0.295   0.295
linear CRPS         0.331   0.331   0.331   0.331
random_analogue CRPS 0.183  0.183   0.183   0.193
model CRPS          0.187   0.179   0.184   0.193
```

(MAE in km; persistence and linear are deterministic in z so values
are constant; random_analogue is unweighted by shape so its z-dep is
near-zero too. Only `model` is materially affected by Z_SCALE.)

**Best z-scale for model: 0.0** (model_MAE = 297.5 km; persistence_MAE = 320.8 km).

## What we learned

### 1. The spark generalizes — but barely, and only in 2D

At **z = 0.0** the model beats persistence by ~7% on spatial MAE
(297.5 vs 320.8 km). This is the headline answer: yes, the
self-similarity primitive does extract real signal from real
hurricane tracks. The world-events pillar gets its first concrete
data type registered in the platform spine (`RunKind.EVENTS`,
dataset `hurdat2-atlantic-v1`).

### 2. Torsion HURTS on storm tracks

The most important *negative* finding: as Z_SCALE goes up, model
MAE goes up too (297.5 → 303.5 → 322.0 → 325.6 km). Torsion adds
**no signal** for storm tracks; in fact, the noisier wind axis
contaminates the κ retrieval. Hurricanes are nearly-planar paths
on the sphere; their "twist" comes from intensity changes that are
weakly correlated with track shape. So the bend-pattern in (lat,
lon) is the entire usable signal — the third dimension is just
noise.

This is a meaningful null result for the "torsion matters"
hypothesis on this specific data type. Future weather-pillar
experiments need different descriptors when 3D is added back in
(see Next, below).

### 3. Linear extrapolation crushes everything at short horizons

Linear MAE = 177.3 km — **42% better than persistence, 40% better
than the model**. Why: storms move along nearly straight tracks
over 24-hour windows, with ridge-of-high-pressure-driven steering
that doesn't change much over 24h. Operational forecasters know
this; CLIPER (the linear-regression baseline NHC has used since the
1970s) is genuinely hard to beat at 24h. The model doesn't
out-perform linear because the K=4 window doesn't carry enough
shape information — at 6-hourly cadence, four points is barely
enough to compute a single Frenet sample.

This is consistent with the literature: official NHC track
forecasts only beat CLIPER at horizons ≥ 48h (or with multi-model
ensembles). A K=4 / J=4 setup is the wrong test for "track shape
matters."

### 4. The model captures uncertainty even when it loses on MAE

`hit_rate` for the model is 0.39–0.45; for persistence, 0.02; for
linear, 0.02. Persistence and linear have point-forecast cones
that are so narrow the actual storm misses them on every trial.
The model — by aggregating the spread of analogue continuations —
produces calibrated cones. CRPS confirms this: model CRPS (0.18)
beats both persistence (0.295) and linear (0.331) at every z-scale.
**The model is the better probabilistic forecaster even when it
loses on point MAE.**

### 5. Random_analogue is nearly tied with model on MAE

random_analogue (no shape match) ≈ 314 km MAE vs model 297 km at
z=0.0. The shape-DTW retrieval is doing only 5% of the work; most
of the gain over persistence is just from "draw next-N-step
displacements from the marginal corpus distribution" rather than
from κ-similarity. This is consistent with the high-noise / low-K
regime: at K=4 the bivariate DTW has very little to discriminate
on, so the prefilter shortlist is almost random anyway.

## Next experiments

If we want to make the primitive *competitive* on storm tracks (not
just generalizing), the gaps suggest:

1. **Bigger windows.** K=8 (48h) or K=12 (72h) gives Frenet 2–3 more
   sample points, much more shape signal. Requires longer storms
   only — already filtered to ≥ 8 fixes; bumping to ≥ 16 keeps ~30%
   of the corpus, still ~500 storms. **Most promising next step.**
2. **Persistence-aware descriptors.** TDA on the trajectory point
   cloud (persistence diagrams of the track's geometric features)
   might capture loop-back / re-curvature patterns that κ doesn't.
3. **Procrustes / elastic shape distance.** Replace bivariate DTW on
   (κ, τ) with elastic shape distance directly on the (x, y) curves.
   Skips the descriptor-then-DTW indirection.
4. **Learned descriptors.** Vec2Vec or a tiny TCN trained on the
   train corpus could extract richer shape features than the
   hand-coded Frenet pipeline.

Dynamic spatial graphs (the originally-planned third experiment)
are still on the menu — but the second experiment's lesson is
that the *descriptor* is the right next axis to vary, not the
*data modality*. Storms are a clean enough laboratory; we should
make the primitive work better here before adding more data
complexity.

## Tradeoffs and open questions

- **K=4 might be too small.** The synthetic agents experiment used
  K=50 (uniform-Δt sim). HURDAT2's 6-hourly cadence forces shorter
  windows for any realistic forecast horizon. The "did the
  primitive generalize?" answer might be "yes for K big enough;
  unknown for HURDAT2-cadence storms with usable forecast horizons."
- **Spatial MAE in km is the user-facing number.** We project z
  back out of the metric (only (x, y) used for distance). The model
  is still TRAINED on 3D; only REPORTING is 2D. This means a
  z=5.0 model with worse 3D-MAE can still report 2D-MAE — but
  empirically, optimizing z just makes the (x, y) part worse too.

## Cross-links

- [[trajectory_3d]] — the synthetic-agents experiment (Phase 1)
- [[dtw]] — bivariate DTW used for the κ retrieval
- [[platform-spine]] — the RunKind.EVENTS slot used here
- [[bempedelis_2d]] — the 2D analogue-of-this for terrain heightmaps

## Code-path index

- Backtest entry: `the_similarity/tests/test_trajectory_3d_storms.py::test_storm_tracks_backtest_vs_baselines`
- Ablation entry: `the_similarity/tests/test_trajectory_3d_storms_ablation.py::test_storm_tracks_z_scale_ablation`
- Dataset loader: `the_similarity/datasets/storm_tracks.py::load_storms`
- Adapter: `the_similarity/platform/adapters/storms.py::register_storm_backtest_run`
