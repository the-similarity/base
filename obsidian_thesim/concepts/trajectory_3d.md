# 3D Trajectory Self-Similarity

A research-grade MVP testing whether the project's self-similarity
primitive (analogue retrieval -> weighted forecast cone) generalizes
from 1D timeseries (price) and 2D heightmaps (terrain) to **3D
paths** — the trajectory of something moving through space.

Code:
- `the_similarity/methods/trajectory_3d.py` — Frenet descriptors + bivariate DTW
- `the_similarity/core/trajectory_matcher.py` — corpus + retrieval + cone
- `the_similarity/tests/test_trajectory_3d_descriptors.py` — analytical-reference unit tests
- `the_similarity/tests/test_trajectory_3d_matcher.py` — shape-class retrieval tests
- `the_similarity/tests/test_trajectory_3d.py` — end-to-end backtest (slow)
- `the_similarity/platform/adapters/trajectories.py` — registry adapter
- `the-similarity-fractal/scripts/generate_heightmap.py` — heightmap export
- `the-similarity-fractal/src/sim/headless/world.js` — agents lifted to 3D
- `the-similarity-fractal/src/sim/headless/runner.js` — `--track-agents` + `--heightmap`

## Hypothesis

> The same primitive that works on 1D price and 2D terrain works on
> 3D paths.

If yes, the spark is genuinely *general* and we earn the right to
test it on real-world paths (storm tracks, animal GPS, sports). If
no, we learn what richer descriptors are needed (Procrustes,
elastic shape distance, persistence-diagram TDA over the trajectory
point cloud).

## Why Frenet (kappa, tau) descriptors?

For a smooth space curve gamma(s) parameterized by arc length:

- **kappa(s)** = ||gamma''(s)||      — curvature (magnitude)
- **tau(s)**   = -<B'(s), N(s)>       — torsion (signed)

These two scalar fields **uniquely determine the curve up to rigid
motion** (translation + rotation) — they are the right shape
invariants. Critically, *torsion requires 3D*: a planar curve has
tau == 0 identically, so torsion is the signal that earns the third
dimension. See [[bempedelis_2d]] for the 2D analogue.

Discrete formulas, after arc-length resampling so spacing is uniform:

```
T_i  = (P_{i+1} - P_i) / ||P_{i+1} - P_i||
dT_i = T_{i+1} - T_i
kappa_i ~ ||dT_i|| / Delta_s
N_i  = dT_i / ||dT_i||
B_i  = T_i x T_{i+1}, normalized
dB_i = B_{i+1} - B_i
tau_i ~ -<dB_i, N_i> / Delta_s
```

Verified against analytical references (line, circle, helix) to
within ~1e-4 in the curve interior — see
`test_trajectory_3d_descriptors.py`.

## Pipeline

```
raw 3D points (x,y,z)
   |
   v
arc-length resample           (chord-length parameterization)
   |
   v
position smoothing            (Gaussian, sigma_pos=2.0 default)
   |
   v
Frenet (kappa, tau)           (with sigma=1.5 smoothing on the
                               descriptors themselves)
   |
   v
SAX prefilter signature       ([[sax]] -- 8 segments x 4 symbols)
   |
   v
top-N candidates -> bivariate DTW on (kappa, tau)  ([[dtw]])
   |
   v
weighted forecast cone        (per-axis P10/P50/P90 quantiles,
                               anchored at query endpoint)
```

## What surprised us

### Discrete-derivative noise amplification on lines

A naive implementation produced a pathological result: noisy lines
end up with kappa values *larger* than clean helices. The discrete
second derivative amplifies tiny Cartesian jitters into huge spurious
curvatures (random direction changes look like sharp turns at a
2-point stencil).

Two fixes were necessary:
1. **Pre-smooth the positions** before computing descriptors
   (`sigma_pos = 2.0` default in `TrajectoryCorpus`). This is the
   single most-important hyperparameter — set it to 0 and matcher
   accuracy collapses on noisy data.
2. **Numerical guard on torsion**: when the local tangent
   cross-product magnitude is < 0.02 (turning angle ~1 degree per
   step), zero tau out. The principal normal is ill-defined for
   near-straight segments and the discrete formula produces
   wildly-varying values.

### Smoothing scale is itself a research insight

`sigma_pos = 2.0` and descriptor `sigma = 1.5` work well for
biased random walks on a sin/cos terrain. The "right" sigma is the
natural motif scale of the data — for animal GPS the sigma might
be hours; for storm tracks it might be 6-hour synoptic intervals.
`multiscale_descriptors` returns a stack at sigma in {1, 4, 16}
so the matcher can mix scales when one is uncertain.

### Backtest results — first run

50 synthetic agents biased-random-walking on
`z = 0.5 sin(0.15 x) cos(0.12 y) + 0.3 sin(0.07 (x+y))`,
500 ticks each, K=50 window, J=20 horizon, 750 trials per predictor:

| predictor          |     MAE | hit_rate |  CRPS |
|--------------------|--------:|---------:|------:|
| **model**          |  2.7212 |   0.4027 | 0.1619 |
| persistence        |  6.5732 |   0.0000 | 0.2319 |
| linear extrap      |  4.2145 |   0.3693 | 0.1690 |
| random analogue    |  2.8711 |   0.1733 | 0.2125 |

**The model beats every baseline on MAE and CRPS.** It even beats
the random-analogue baseline by ~6% on MAE — a signal that the
shape-DTW retrieval is doing real work, not just exploiting the
corpus's marginal continuation distribution.

Hit-rate 0.40 is below the aspirational 0.5 target but is **2.3x
the random-analogue baseline (0.17)** and infinitely better than
persistence (0.00). The cone width is essentially calibrated by
the analogue spread — a tighter cone would lift hit_rate at the
cost of coverage.

## What we learned

1. **The primitive does generalize.** Same retrieval-+-cone
   structure that works on price and terrain works on 3D paths
   without algorithmic changes — only the descriptor (kappa, tau)
   was new.
2. **Position smoothing is mandatory** for any noisy real-world
   3D data. The discrete second-derivative amplification is severe.
3. **Per-axis quantile cones are good enough** for v1. A true 3D
   covariance ellipsoid would be more expressive but small-N
   sensitive; the bounding-box approach falls out of the existing
   1D `_weighted_quantile` infrastructure for free.
4. **Hit-rate is the soft metric.** MAE and CRPS already show
   strong wins; hit_rate could be improved with a non-axis-aligned
   cone (Mahalanobis distance against the analogue covariance
   matrix). Out of MVP scope.

## Follow-ups (not in this MVP)

- **Procrustes / elastic shape distance** (Srivastava et al.) —
  alternatives to Frenet-DTW that handle reparameterization
  natively. Worth comparing on the same backtest.
- **Persistence-diagram TDA** over the trajectory point cloud —
  may capture global topology that local kappa/tau misses.
- **Real-world data** — storm tracks (NHC HURDAT2), animal GPS
  (Movebank), sports trajectories (Statsbomb 360). The MVP earned
  this.
- **Mahalanobis cone** for higher hit_rate at horizon J without
  cone-widening hacks.

## Related notes

- [[dtw]] — the 1D dynamic time warping primitive we extend
- [[sax]] — symbolic prefilter we reuse for the trajectory matcher
- [[bempedelis_2d]] — the 2D analogue this experiment generalizes
- [[platform_thesis]] — where this fits in the synthetic environment
  layer (worlds pillar, eval pillar)
