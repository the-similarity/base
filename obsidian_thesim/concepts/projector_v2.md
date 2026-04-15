# Projector v2 — calibration-upgrade lane

Research lane for testing calibration improvements against the existing
bar-wise weighted-quantile cone in [[projector|the baseline projector]].
The lane is **additive only**: `the_similarity/core/projector.py` is
frozen and untouched so historical experiments remain reproducible.

## TL;DR (2026-04-15)

Five variants evaluated, three kept, one discarded, baseline is the
reference. Terminal CRPS and calibration both improve materially with
adaptive / change-aware conformal; joint-path and regime-aware widening
are more nuanced.

### Real-parquet confirmation (2026-04-15, v2 sweep)

`adaptive_conformal` **confirmed on real data** across 5 slices
(spy-1d, btc-1d, nvda-1d, spy-covid-entry-2020, spy-rate-hike-2022):

| Metric | Baseline | Adaptive | Δ |
|--------|----------|----------|---|
| CRPS (terminal) | 0.1846 | 0.1622 | **−12.1%** |
| Calibration error P10/P90 | 0.1067 | 0.0833 | −0.023 |
| Over-time calibration | 0.0993 | 0.0703 | −0.029 |
| Joint CRPS | 0.1855 | 0.1633 | −0.022 |
| Hit rate | 54.0% | 54.0% | flat (expected) |
| Runtime | 1538s | 1191s | **0.77×** (faster) |

Every slice improved on CRPS and calibration. Runtime is lower because
the adaptive recalibration cuts wasted width and the cone shortens;
this was not predicted but held across all 5 slices.

`change_aware_conformal` is **byte-identical** to `adaptive_conformal`
on these 5 slices (same CRPS to 5 decimals, same calibration, same
joint CRPS). The shift detector did not fire on any real slice tested,
so change-aware collapses to adaptive. Treat as "untested on real data"
not "confirmed"; revisit on slices with forced regime breaks.

Report: `progress/autoresearch/reports/projector-v2-v2.md`.
Benchmark id in ledger: `projector-v2-core-v2`.

**Promotion status:** adaptive_conformal is confirmed but still
lane-scoped. Promotion behind `Config.projector` flag deferred until a
caller (decision layer, design-partner pilot) needs it.

| Variant | Decision | Why |
|---------|----------|-----|
| `adaptive_conformal`       | **KEEP**    | -14% terminal CRPS, -0.033 calibration error on both slices |
| `change_aware_conformal`   | KEEP (duplicate) | Identical to adaptive on synthetic; needs shift-rich slice to diverge |
| `joint_path`               | KEEP (marginal) | -2.8% CRPS but joint-CRPS regresses slightly; tune noise fraction |
| `regime_aware_widening`    | **DISCARD** | Default multipliers mis-fit to residuals, +2.8% CRPS |
| `baseline_barwise_quantiles` | reference | —   |

Report: `progress/autoresearch/reports/projector-v2-v1.md`.
Ledger entries: last 5 rows of `progress/autoresearch/experiments.jsonl`
(benchmark_id = `projector-v2-core-v1`).

## Modules

All variants expose a `project(matches, history, forward_bars,
percentiles, config, **extras) -> Forecast` signature matching
`the_similarity.core.projector.project`, so they can be swapped in-place
by the backtester without touching `backtester.py` or `api.py`.

- [[projector_adaptive_conformal]] — `the_similarity/core/projector_adaptive_conformal.py`
  - Gibbs-Candès adaptive conformal recalibration around the baseline
    P50/P10/P90 cone.
  - Optional **change-aware mode** down-weights older residuals when a
    rolling-variance jump is detected (shift detector).
- [[projector_regime_aware]] — `the_similarity/core/projector_regime_aware.py`
  - Detects the query's regime via [[regime|tag_regime]] and multiplies
    the P10/P25/P75/P90 distance from P50 by a regime-specific factor.
- [[projector_joint_path]] — `the_similarity/core/projector_joint_path.py`
  - Importance-resamples WHOLE match forward paths from the empirical
    copula; per-path scalar noise preserves joint coherence across bars.

## Metric extensions

Two new scoring rules in `the_similarity/core/metrics.py`:

- `calibration_error_over_time(trials, percentiles)` — per-horizon
  coverage error averaged across bars. Catches variants that improve
  terminal-only calibration at the cost of mid-horizon coverage drift.
- `joint_path_crps(trials)` — CRPS integrated along the full forecast
  horizon, not just the terminal bar. Reduces to standard CRPS when
  `forward_bars == 1`.

## Lane artifacts

- Playbook: `research/autoresearch/playbooks/PROJECTOR_V2_LANE.md`
- Benchmark: `research/autoresearch/benchmarks/projector-v2-core-v1.yaml`
- Runner:   `research/autoresearch/scripts/run_projector_v2_sweep.py`
- Tests:    `the_similarity/tests/test_projector_adaptive_conformal.py`,
  `test_projector_regime_aware.py`, `test_projector_joint_path.py`,
  `test_metrics_projector_v2.py`
- Runner test: `research/autoresearch/scripts/test_run_projector_v2_sweep.py`

## Walk-forward guarantee (MANDATORY)

Every variant consumes only the lookback that the backtester hands to
`project(...)`. Adaptive conformal calibrates off **match forward
windows** (which live inside the lookback), not trial actuals. Regime
detection consumes only the explicit query or the lookback tail. Joint
sampling consumes only the matched paths. No variant peeks past the
trial boundary.

## Keep / discard rule (from playbook)

Keep a variant only if CRPS **or** `calibration_error_p10_p90` strictly
improves on **all** canonical slices without triggering any hard
regression:
- CRPS up by > 10%  → discard
- hit_rate < 0.45   → discard
- runtime doubles without commensurate gain → discard

## Notes for future agents

- Do NOT modify `the_similarity/core/projector.py`; the baseline is
  frozen to keep projector-calibration-core-v1 reproducible.
- The sweep runner has a deterministic synthetic fallback (seed per
  slice) so it runs in a clean worktree without the data submodule.
  Results on real parquets may shift the decision boundaries.
- `change_aware_conformal` duplicates `adaptive_conformal` on smooth
  GBM data. Run it on a shift-rich slice (e.g. 2020-03 COVID crash) to
  see its true behaviour.
- Decision: re-run against real parquets before promoting any variant
  to default in `projector.py`. The variants below are lane-scoped
  until a real-data sweep confirms the keep decisions.
