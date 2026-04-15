# Projector v2 sweep — v1

Generated: 2026-04-15T17:44:30Z

## Aggregate scorecard

| Variant | CRPS | Cal. err P10/P90 | Cal. err over time | Joint CRPS | Hit rate | Runtime (s) | Decision |
|---------|------|------------------|--------------------|-----------|----------|-------------|----------|
| `baseline` | 0.18460 | 0.1067 | 0.0993 | 0.18547 | 54.0% | 1237.5 | baseline |
| `adaptive_conformal` | 0.16220 | 0.0833 | 0.0703 | 0.16328 | 54.0% | 1543.0 | keep |
| `change_aware_conformal` | 0.16220 | 0.0833 | 0.0703 | 0.16328 | 54.0% | 1538.6 | keep |

## Per-slice breakdown

### spy-1d

| Variant | CRPS | Cal. err P10/P90 | Cal. err over time | Joint CRPS | Hit rate | Runtime (s) | Synthetic |
|---------|------|------------------|--------------------|-----------|----------|-------------|-----------|
| `baseline` | 0.19633 | 0.1333 | 0.0783 | 0.17620 | 43.3% | 156.1 | False |
| `adaptive_conformal` | 0.17500 | 0.0833 | 0.0700 | 0.16287 | 43.3% | 157.5 | False |
| `change_aware_conformal` | 0.17500 | 0.0833 | 0.0700 | 0.16287 | 43.3% | 176.6 | False |

### btc-1d

| Variant | CRPS | Cal. err P10/P90 | Cal. err over time | Joint CRPS | Hit rate | Runtime (s) | Synthetic |
|---------|------|------------------|--------------------|-----------|----------|-------------|-----------|
| `baseline` | 0.16500 | 0.0667 | 0.0983 | 0.18980 | 50.0% | 390.9 | False |
| `adaptive_conformal` | 0.14367 | 0.0500 | 0.0517 | 0.15887 | 50.0% | 331.4 | False |
| `change_aware_conformal` | 0.14367 | 0.0500 | 0.0517 | 0.15887 | 50.0% | 449.1 | False |

### nvda-1d

| Variant | CRPS | Cal. err P10/P90 | Cal. err over time | Joint CRPS | Hit rate | Runtime (s) | Synthetic |
|---------|------|------------------|--------------------|-----------|----------|-------------|-----------|
| `baseline` | 0.15433 | 0.0333 | 0.0500 | 0.15743 | 50.0% | 393.0 | False |
| `adaptive_conformal` | 0.13300 | 0.0833 | 0.0675 | 0.14170 | 50.0% | 752.3 | False |
| `change_aware_conformal` | 0.13300 | 0.0833 | 0.0675 | 0.14170 | 50.0% | 512.9 | False |

### spy-covid-entry-2020

| Variant | CRPS | Cal. err P10/P90 | Cal. err over time | Joint CRPS | Hit rate | Runtime (s) | Synthetic |
|---------|------|------------------|--------------------|-----------|----------|-------------|-----------|
| `baseline` | 0.19433 | 0.1833 | 0.1542 | 0.20277 | 63.3% | 160.7 | False |
| `adaptive_conformal` | 0.16767 | 0.1000 | 0.1067 | 0.18063 | 63.3% | 160.8 | False |
| `change_aware_conformal` | 0.16767 | 0.1000 | 0.1067 | 0.18063 | 63.3% | 211.6 | False |

### spy-rate-hike-2022

| Variant | CRPS | Cal. err P10/P90 | Cal. err over time | Joint CRPS | Hit rate | Runtime (s) | Synthetic |
|---------|------|------------------|--------------------|-----------|----------|-------------|-----------|
| `baseline` | 0.21300 | 0.1167 | 0.1158 | 0.20113 | 63.3% | 136.8 | False |
| `adaptive_conformal` | 0.19167 | 0.1000 | 0.0558 | 0.17233 | 63.3% | 140.9 | False |
| `change_aware_conformal` | 0.19167 | 0.1000 | 0.0558 | 0.17233 | 63.3% | 188.4 | False |

## Keep / discard notes

- **`baseline`** — baseline
  - CRPS Δ: 0.00000 (rel +0.0%)
  - Calibration P10/P90 Δ: +0.0000
  - Joint CRPS Δ: +0.00000
  - Over-time calibration Δ: +0.0000
  - Hit rate Δ: +0.0%, runtime ×1.00

- **`adaptive_conformal`** — keep
  - CRPS Δ: -0.02240 (rel -12.1%)
  - Calibration P10/P90 Δ: -0.0233
  - Joint CRPS Δ: -0.02219
  - Over-time calibration Δ: -0.0290
  - Hit rate Δ: +0.0%, runtime ×1.25

- **`change_aware_conformal`** — keep
  - CRPS Δ: -0.02240 (rel -12.1%)
  - Calibration P10/P90 Δ: -0.0233
  - Joint CRPS Δ: -0.02219
  - Over-time calibration Δ: -0.0290
  - Hit rate Δ: +0.0%, runtime ×1.24
