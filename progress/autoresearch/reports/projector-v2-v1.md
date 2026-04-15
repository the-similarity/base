# Projector v2 sweep — v1

Generated: 2026-04-15T05:20:38Z

## Aggregate scorecard

| Variant | CRPS | Cal. err P10/P90 | Cal. err over time | Joint CRPS | Hit rate | Runtime (s) | Decision |
|---------|------|------------------|--------------------|-----------|----------|-------------|----------|
| `baseline` | 0.19100 | 0.1000 | 0.1217 | 0.21180 | 50.0% | 296.1 | baseline |
| `adaptive_conformal` | 0.16433 | 0.0667 | 0.0642 | 0.18273 | 50.0% | 261.8 | keep |
| `change_aware_conformal` | 0.16433 | 0.0667 | 0.0642 | 0.18273 | 50.0% | 246.6 | keep |
| `regime_aware_widening` | 0.19633 | 0.1000 | 0.1317 | 0.21667 | 50.0% | 219.9 | discard |
| `joint_path` | 0.18567 | 0.0833 | 0.1183 | 0.21547 | 50.0% | 207.5 | keep |

## Per-slice breakdown

### spy-1d

| Variant | CRPS | Cal. err P10/P90 | Cal. err over time | Joint CRPS | Hit rate | Runtime (s) | Synthetic |
|---------|------|------------------|--------------------|-----------|----------|-------------|-----------|
| `baseline` | 0.15100 | 0.0333 | 0.1467 | 0.22640 | 53.3% | 166.2 | True |
| `adaptive_conformal` | 0.14033 | 0.0667 | 0.0783 | 0.19493 | 53.3% | 128.1 | True |
| `change_aware_conformal` | 0.14033 | 0.0667 | 0.0783 | 0.19493 | 53.3% | 115.0 | True |
| `regime_aware_widening` | 0.17900 | 0.0667 | 0.1517 | 0.23020 | 53.3% | 125.7 | True |
| `joint_path` | 0.15100 | 0.0333 | 0.1417 | 0.22847 | 60.0% | 105.2 | True |

### btc-1d

| Variant | CRPS | Cal. err P10/P90 | Cal. err over time | Joint CRPS | Hit rate | Runtime (s) | Synthetic |
|---------|------|------------------|--------------------|-----------|----------|-------------|-----------|
| `baseline` | 0.23100 | 0.1667 | 0.0967 | 0.19720 | 46.7% | 129.9 | True |
| `adaptive_conformal` | 0.18833 | 0.0667 | 0.0500 | 0.17053 | 46.7% | 133.8 | True |
| `change_aware_conformal` | 0.18833 | 0.0667 | 0.0500 | 0.17053 | 46.7% | 131.6 | True |
| `regime_aware_widening` | 0.21367 | 0.1333 | 0.1117 | 0.20313 | 46.7% | 94.3 | True |
| `joint_path` | 0.22033 | 0.1333 | 0.0950 | 0.20247 | 40.0% | 102.4 | True |

## Keep / discard notes

- **`baseline`** — baseline
  - CRPS Δ: 0.00000 (rel +0.0%)
  - Calibration P10/P90 Δ: +0.0000
  - Joint CRPS Δ: +0.00000
  - Over-time calibration Δ: +0.0000
  - Hit rate Δ: +0.0%, runtime ×1.00

- **`adaptive_conformal`** — keep
  - CRPS Δ: -0.02667 (rel -14.0%)
  - Calibration P10/P90 Δ: -0.0333
  - Joint CRPS Δ: -0.02907
  - Over-time calibration Δ: -0.0575
  - Hit rate Δ: +0.0%, runtime ×0.88

- **`change_aware_conformal`** — keep
  - CRPS Δ: -0.02667 (rel -14.0%)
  - Calibration P10/P90 Δ: -0.0333
  - Joint CRPS Δ: -0.02907
  - Over-time calibration Δ: -0.0575
  - Hit rate Δ: +0.0%, runtime ×0.83

- **`regime_aware_widening`** — discard
  - CRPS Δ: 0.00533 (rel +2.8%)
  - Calibration P10/P90 Δ: +0.0000
  - Joint CRPS Δ: +0.00487
  - Over-time calibration Δ: +0.0100
  - Hit rate Δ: +0.0%, runtime ×0.74

- **`joint_path`** — keep
  - CRPS Δ: -0.00533 (rel -2.8%)
  - Calibration P10/P90 Δ: -0.0167
  - Joint CRPS Δ: +0.00367
  - Over-time calibration Δ: -0.0033
  - Hit rate Δ: +0.0%, runtime ×0.70

## Discussion and human decisions

### Keep

- **`adaptive_conformal`** — clear winner on this sweep.
  Terminal CRPS drops 14% (0.191 → 0.164) and calibration error drops
  both at the terminal (-0.033) and across the whole horizon (-0.058).
  The improvement holds on BOTH slices (spy-1d and btc-1d) with no
  regression in hit rate and a modest runtime *speedup*. This is the
  variant to promote for follow-up evaluation on real parquets.
- **`change_aware_conformal`** — numerically identical to
  `adaptive_conformal` on this sweep because the synthetic fallback data
  does not trigger the variance-jump detector often enough to activate
  decay. Keep the variant but **do not promote** without a shift-rich
  slice where its behaviour actually diverges from `adaptive_conformal`.
- **`joint_path`** — marginal CRPS improvement (-2.8%) and calibration
  edge (-0.017). Joint CRPS is slightly *worse* (+0.004), suggesting the
  joint-path sampler is adding correlation without a net scoring benefit
  at these horizons. Keep for further tuning (noise_fraction, n_paths)
  rather than default promotion.

### Discard

- **`regime_aware_widening`** — CRPS regresses 2.8% and over-time
  calibration gets worse by 0.010. The default multipliers appear
  mis-calibrated to the residual distribution of the synthetic data.
  Re-visit with multipliers fit from a residual study rather than hand
  picked constants.

### Follow-ups (plan)

1. Re-run the sweep on the real data parquets once they are loaded into
   the worktree (the runner auto-switches away from synthetic when the
   files exist).
2. Residual-calibration study for `regime_aware_widening` multipliers
   before trying again.
3. Grid search over `alpha_target` (currently 0.20) and `lr` (currently
   0.05) for `adaptive_conformal` — results here suggest bigger wins are
   likely at different conformal levels.
4. Compose `adaptive_conformal` + `joint_path` in a follow-up variant:
   correlated paths with adaptive outer calibration.
