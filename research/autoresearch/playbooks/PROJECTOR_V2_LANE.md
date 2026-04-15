# Projector v2 lane — adaptive conformal, regime-aware, joint-path

## Lane identity
- **Lane ID:** `projector-v2-lane-v1`
- **Benchmark ID:** `projector-v2-core-v1`
- **Question:** Can targeted calibration upgrades (adaptive / change-aware
  conformal, regime-aware widening, joint-path sampling) beat the existing
  bar-wise weighted-quantile cone on CRPS and calibration error without
  regressing hit rate or runtime?
- **Owner:** research

## Write scope
- **Allowed:**
  - `research/autoresearch/`
  - `progress/autoresearch/`
  - `the_similarity/core/projector_adaptive_conformal.py` (new)
  - `the_similarity/core/projector_regime_aware.py` (new)
  - `the_similarity/core/projector_joint_path.py` (new)
  - `the_similarity/core/metrics.py` (add-only extensions)
  - `the_similarity/tests/`
  - `obsidian_thesim/concepts/`
- **Forbidden:**
  - `the_similarity/core/projector.py` — baseline is frozen; do NOT modify
  - `the_similarity/core/backtester.py`
  - `the_similarity/core/matcher.py`
  - `pyproject.toml`
  - benchmark manifest files during a run

## Baseline
The baseline for every variant is the current
`the_similarity.core.projector.project(...)` function exposed through
`the_similarity.api.project`. Its behavior must remain byte-stable across
this lane.

## Variants under test

| Variant id                   | Module                                                 | Idea |
|------------------------------|--------------------------------------------------------|------|
| `baseline_barwise_quantiles` | `the_similarity.core.projector`                        | Reference |
| `adaptive_conformal`         | `the_similarity.core.projector_adaptive_conformal`     | Online conformal α-adjustment via recent coverage error |
| `change_aware_conformal`     | same module, `change_aware=True`                        | Down-weight old calibration residuals when regime shift detected |
| `regime_aware_widening`      | `the_similarity.core.projector_regime_aware`           | Per-regime multiplicative cone widening |
| `joint_path`                 | `the_similarity.core.projector_joint_path`             | Sample correlated forward paths instead of independent bar quantiles |

All variants expose a `project(matches, history, forward_bars, percentiles, config, **extras) -> Forecast` signature compatible with the baseline so they can be swapped in-place.

## Scorecard

Primary (lower is better):
- `crps`
- `calibration_error_p10_p90`

Secondary:
- `hit_rate` (higher is better)
- `runtime_seconds` (lower is better)
- `calibration_error_over_time` (lower is better) — per-horizon calibration
- `joint_path_crps` (lower is better) — path-level CRPS using rank histograms

Hard regressions that force discard:
- CRPS worsens > 10 % on any slice
- hit_rate drops below 0.45 on any slice
- runtime doubles without commensurate gain

## Keep / discard rule
Keep a variant only if CRPS **or** `calibration_error_p10_p90` strictly
improves on **all** canonical slices without triggering a hard regression.
If a variant only wins on one slice it is *marked* (not promoted) and flagged
for follow-up investigation before default promotion.

## Run protocol
1. Read benchmark manifest `projector-v2-core-v1.yaml`.
2. Run the baseline — this produces the reference CRPS / calibration / hit
   rate / runtime for each slice.
3. Run every candidate variant on the SAME slices and seeds.
4. Append a ledger entry per variant to
   `progress/autoresearch/experiments.jsonl`.
5. Synthesise the sweep into `progress/autoresearch/reports/projector-v2-v1.md`
   with a keep/discard decision per variant.
6. Promote to default only if criteria in “Keep / discard rule” are satisfied.

## Notes for future agents
- No variant gets promoted into default projector behaviour without a green
  decision on real benchmark data.
- Walk-forward is mandatory. Adaptive conformal variants must not peek at
  the trial's own actual returns when calibrating — only past lookback data
  is legal.
- Joint-path sampler should preserve marginal calibration: if P10 coverage
  was 0.10 under independent sampling, it should stay near 0.10 under joint
  sampling. Use `calibration_error_over_time` to confirm.
