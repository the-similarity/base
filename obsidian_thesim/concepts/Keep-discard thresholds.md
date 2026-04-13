# Keep-discard thresholds

Numeric gates that turn qualitative acceptance rules into **deterministic, reproducible decisions**. Two agents reading the same before/after metrics must reach the same KEEP or DISCARD verdict.

## Why numeric thresholds?

The original benchmark YAML files described acceptance in prose ("improves on at least one canonical slice", "does not worsen by more than a reasonable amount"). This left room for subjective interpretation. Explicit thresholds eliminate that ambiguity.

## Design principles

1. **Fail-closed** -- missing or unparseable metrics produce DISCARD.
2. **Absolute deltas** -- thresholds are expressed as absolute metric changes, not percentages, because percentage changes are unstable near zero.
3. **Per-lane tuning** -- each benchmark YAML carries its own `thresholds:` block. The retrieval lane gates on CRPS improvement; the projector-calibration lane gates on calibration improvement.
4. **Walk-forward mandatory** -- retrieval lift that does not survive walk-forward validation is always DISCARD.

## JEPA retrieval lane thresholds

| Gate | Value | Meaning |
|------|-------|---------|
| `min_crps_improvement` | 0.005 | CRPS must drop by at least this much |
| `max_calibration_regression` | 0.02 | Calibration must not worsen beyond this |
| `max_runtime_multiplier` | 2.0x | Runtime ratio ceiling |
| `min_slices_improved` | 1 | At least one canonical slice must improve |
| `walk_forward_required` | true | Walk-forward confirmation mandatory |

Source: `research/autoresearch/benchmarks/jepa-retrieval-core-v1.yaml`

## Projector calibration lane thresholds

| Gate | Value | Meaning |
|------|-------|---------|
| `min_calibration_improvement` | 0.005 | Calibration must improve by at least this much |
| `max_crps_regression` | 0.01 | CRPS must not regress beyond this |
| `max_runtime_multiplier` | 2.0x | Runtime ratio ceiling |
| `min_slices_improved` | 1 | At least one slice must show calibration improvement |
| `walk_forward_required` | true | Walk-forward confirmation mandatory |

Source: `research/autoresearch/benchmarks/projector-calibration-core-v1.yaml`

## Validation script

`research/autoresearch/scripts/validate_decision.py` automates the decision:

```bash
python validate_decision.py \
  --benchmark benchmarks/jepa-retrieval-core-v1.yaml \
  --before '{"crps": 0.339, "calibration_error_p10_p90": 0.50, "runtime_seconds": 3.7}' \
  --after  '{"crps": 0.330, "calibration_error_p10_p90": 0.49, "runtime_seconds": 4.0}'
```

The script outputs `KEEP` or `DISCARD` with per-gate reasoning. Use `--json` for machine-readable output.

## Related

- [[Nine-method pipeline]] -- the retrieval and scoring system these thresholds protect
- [[Repo research and docs]] -- where benchmark YAMLs and playbooks live
