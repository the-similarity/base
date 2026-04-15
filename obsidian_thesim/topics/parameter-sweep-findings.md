---
title: Parameter sweep findings
type: topic
created: 2026-04-14
---

# Parameter-sweep findings

Durable record of what we've learned from automated parameter sweeps of the self-similarity engine. Each section pins a single sweep run with its best config and the key takeaway. The append-only ledger lives at `progress/autoresearch/experiments.jsonl`; per-run reports at `progress/autoresearch/reports/sweep-*.json`; the benchmark spec at `research/autoresearch/benchmarks/parameter-sweep-core-v1.yaml`.

## How sweeps are run

- **Driver:** `research/autoresearch/scripts/run_parameter_sweep.py` (see [[run_parameter_sweep]] if documented separately).
- **Phases:** baseline → one-at-a-time (OAT) per axis → combined best-per-axis → ±1 neighbourhood fine-tune. Avoids the 720-run full grid.
- **Primary target:** CRPS (strictly proper scoring rule). Constraint: `hit_rate ≥ 0.55` preferred, DISCARD if `< 0.45` or CRPS +10%.
- **Axes swept:** `window_size`, `forward_bars`, `top_k`, `confidence_decay_rate`, `koopman_blend_weight`.

## Findings

### 2026-04-14 — SPY daily, sweep-id `spy-initial-v1`

**Best config:** `window_size=100` (everything else at default).

| | CRPS | hit_rate | cal_err (P10/P90) |
|---|---|---|---|
| Baseline (defaults) | 0.18500 | 70.0% | 0.0667 |
| **Best: `window_size=100`** | **0.14433** | 60.0% | 0.0333 |

**CRPS improvement: +22.0% vs baseline.**

#### Parameter sensitivity (CRPS range across OAT values)

| Axis | CRPS range | Verdict |
|---|---|---|
| `window_size` | 0.048 | **dominant** — by far the biggest lever |
| `forward_bars` | 0.028 | meaningful — shorter is better (20 beat 100) |
| `top_k` | 0.017 | small but real |
| `confidence_decay_rate` | 0.000 | no observable effect on this slice |
| `koopman_blend_weight` | 0.000 | no observable effect on this slice |

#### Key observations

1. **Window size dominates.** The pattern length is by far the most important knob; the other four axes collectively moved CRPS less than `window_size` alone.
2. **Axes are NOT additive.** The combined best-per-axis config (`window_size=100 + forward_bars=20 + top_k=20`) scored CRPS 0.163 — worse than `window_size=100` alone at 0.144. Stacking "best per axis" fought itself.
3. **Hit rate dropped with better CRPS.** 70% → 60%. The cone is tighter and better-calibrated but directional picks are slightly less reliable. This is a real tradeoff, not a bug — CRPS penalises cone width AND miscalibration; tighter cones with fewer "lucky" directional hits can still score better.
4. **Confidence decay and Koopman blend made no difference** at tested levels. Either the tested range is too narrow (0–0.05 for decay, 0–0.3 for Koopman) or the effects are dominated by window length. Worth revisiting once the dominant axis is locked in.

#### Caveats

- Tested on SPY daily only, 30 trials per config, single seed (42). Generalisation to BTC/other slices not yet verified.
- 30 trials gives noticeable variance in CRPS — differences under ~0.01 shouldn't be trusted.

#### Next steps

- Validate `window_size=100` on BTC daily before promoting as default.
- Re-run with `n_trials=100` to tighten the estimate.
- Re-sweep `confidence_decay_rate` / `koopman_blend_weight` with `window_size=100` locked in, to see if they matter in that regime.

**Artifacts:** `progress/autoresearch/reports/sweep-summary-spy-initial-v1.json` · ledger entries in `progress/autoresearch/experiments.jsonl` tagged `sweep-id=spy-initial-v1`.
