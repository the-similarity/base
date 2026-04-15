# Lane report — `projector-v2-lane-v1`

_KEEP — generated 2026-04-15T05:20:38Z_

**Canonical-format port of `projector-v2-v1.md`**

This report is the canonical rendering of the Phase 1B projector-v2 sweep output. The original `projector-v2-v1.md` is kept for historical reference. Because the sweep evaluates five variants against one baseline, the canonical format lists the aggregate headline delta for the winning variant in the Deltas section and renders per-variant gate decisions in the Discussion section.

## Metadata

- Lane id: `projector-v2-lane-v1`
- Benchmark id: `projector-v2-core-v1`
- Commit: `unknown`
- Timestamp: `2026-04-15T05:20:38Z`
- Arms: `baseline`, `adaptive_conformal`, `change_aware_conformal`, `regime_aware_widening`, `joint_path`

## Slice × arm scorecard

| slice | baseline·crps | baseline·cal_err | baseline·joint_crps | baseline·hit_rate | baseline·runtime_s | adaptive_conformal·crps | adaptive_conformal·cal_err | adaptive_conformal·joint_crps | adaptive_conformal·hit_rate | adaptive_conformal·runtime_s | change_aware_conformal·crps | change_aware_conformal·cal_err | change_aware_conformal·joint_crps | change_aware_conformal·hit_rate | change_aware_conformal·runtime_s | regime_aware_widening·crps | regime_aware_widening·cal_err | regime_aware_widening·joint_crps | regime_aware_widening·hit_rate | regime_aware_widening·runtime_s | joint_path·crps | joint_path·cal_err | joint_path·joint_crps | joint_path·hit_rate | joint_path·runtime_s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `spy-1d` | 0.1510 | 0.0333 | 0.2264 | 0.5333 | 166.1825 | 0.1403 | 0.0667 | 0.1949 | 0.5333 | 128.0718 | 0.1403 | 0.0667 | 0.1949 | 0.5333 | 114.9720 | 0.1790 | 0.0667 | 0.2302 | 0.5333 | 125.6602 | 0.1510 | 0.0333 | 0.2285 | 0.6000 | 105.1589 |
| `btc-1d` | 0.2310 | 0.1667 | 0.1972 | 0.4667 | 129.9327 | 0.1883 | 0.0667 | 0.1705 | 0.4667 | 133.7677 | 0.1883 | 0.0667 | 0.1705 | 0.4667 | 131.5818 | 0.2137 | 0.1333 | 0.2031 | 0.4667 | 94.2774 | 0.2203 | 0.1333 | 0.2025 | 0.4000 | 102.3507 |

## Deltas

| metric | Δ (candidate − baseline) |
|---|---|
| `crps` | -0.0267 |
| `calibration_error_p10_p90` | -0.0333 |
| `calibration_error_over_time_p10_p90` | -0.0575 |
| `joint_path_crps` | -0.0291 |
| `hit_rate` | +0.0000 |
| `hit_rate_delta` | +0.0000 |

## Gates

| gate | required | metric | direction | threshold | observed | result |
|---|---|---|---|---|---|---|
| `crps_improvement` | True | `crps` | lower_is_better | -0.0050 | -0.0267 | PASS |
| `calibration_improvement` | False | `calibration_error_p10_p90` | lower_is_better | -0.0050 | -0.0333 | PASS |
| `hit_rate_floor` | True | `hit_rate_delta` | higher_is_better | -0.0500 | 0.0000 | PASS |

## Verdict

**KEEP** — 3 of 4 candidate variants passed all required gates: `adaptive_conformal`, `change_aware_conformal`, `joint_path`. See the per-variant breakdown below for details.

## Discussion

### Per-variant gate decisions

**`adaptive_conformal` — KEEP**
- `crps_improvement` (required=True) metric=`crps` threshold=-0.00500 observed=-0.02667 → PASS
- `calibration_improvement` (required=False) metric=`calibration_error_p10_p90` threshold=-0.00500 observed=-0.03333 → PASS
- `hit_rate_floor` (required=True) metric=`hit_rate_delta` threshold=-0.05000 observed=+0.00000 → PASS

**`change_aware_conformal` — KEEP**
- `crps_improvement` (required=True) metric=`crps` threshold=-0.00500 observed=-0.02667 → PASS
- `calibration_improvement` (required=False) metric=`calibration_error_p10_p90` threshold=-0.00500 observed=-0.03333 → PASS
- `hit_rate_floor` (required=True) metric=`hit_rate_delta` threshold=-0.05000 observed=+0.00000 → PASS

**`regime_aware_widening` — DISCARD**
- `crps_improvement` (required=True) metric=`crps` threshold=-0.00500 observed=+0.00533 → FAIL
- `calibration_improvement` (required=False) metric=`calibration_error_p10_p90` threshold=-0.00500 observed=+0.00000 → FAIL
- `hit_rate_floor` (required=True) metric=`hit_rate_delta` threshold=-0.05000 observed=+0.00000 → PASS

**`joint_path` — KEEP**
- `crps_improvement` (required=True) metric=`crps` threshold=-0.00500 observed=-0.00533 → PASS
- `calibration_improvement` (required=False) metric=`calibration_error_p10_p90` threshold=-0.00500 observed=-0.01667 → PASS
- `hit_rate_floor` (required=True) metric=`hit_rate_delta` threshold=-0.05000 observed=+0.00000 → PASS

### Narrative (from original `projector-v2-v1.md`)

- **`adaptive_conformal`** — clear winner on this sweep. Terminal CRPS drops 14% (0.191 → 0.164) and calibration error drops both at the terminal (-0.033) and across the whole horizon (-0.058). Improvement holds on BOTH slices (spy-1d and btc-1d) with no regression in hit rate and a modest runtime *speedup*.
- **`change_aware_conformal`** — numerically identical to `adaptive_conformal` on this sweep because the synthetic fallback data does not trigger the variance-jump detector often enough. Keep the variant but do not promote without a shift-rich slice.
- **`joint_path`** — marginal CRPS improvement (-2.8%). Joint CRPS is slightly *worse* (+0.004). Keep for further tuning (noise_fraction, n_paths).
- **`regime_aware_widening`** — CRPS regresses 2.8% and over-time calibration gets worse by 0.010. Re-visit with multipliers fit from a residual study rather than hand-picked constants. See rejection-log entry `regime_aware_widening`.

## Open questions

- Does adaptive_conformal's win hold on real (non-synthetic) parquets?
- What alpha_target and lr give the best CRPS under adaptive_conformal?
- Can adaptive_conformal + joint_path compose into a better variant?
- Does change_aware_conformal diverge from adaptive_conformal on a shift-rich slice?

## Artifacts

- `progress/autoresearch/reports/projector-v2-*.json (per-(variant, slice) JSONs)`
- `progress/autoresearch/reports/projector-v2-v1.md (original report)`
- `progress/autoresearch/experiments.jsonl (ledger entries)`
- `research/autoresearch/benchmarks/projector-v2-core-v1.yaml (spec)`
