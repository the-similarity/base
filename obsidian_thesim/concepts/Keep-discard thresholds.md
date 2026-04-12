# Keep-discard thresholds

Numeric gates that turn qualitative autoresearch acceptance rules into **deterministic decisions**. Two agents seeing the same before/after metrics must reach the same KEEP or DISCARD outcome.

## Why numeric thresholds?

The original autoresearch benchmarks used prose rules like "improves on at least one slice with no severe regression". This left room for interpretation — one agent might call a 0.001 CRPS drop "improvement" while another calls it noise. Numeric thresholds eliminate that ambiguity.

## Gate design

Every benchmark YAML under `research/autoresearch/benchmarks/` contains a `thresholds:` section with these gate types:

| Gate | Example value | What it checks |
|------|---------------|----------------|
| `min_crps_improvement` | 0.005 abs | Candidate CRPS must be at least this much lower than baseline |
| `max_calibration_regression` | 0.02 abs | No single slice may worsen calibration by more than this |
| `max_crps_regression` | 0.01 abs | No single slice may worsen CRPS by more than this (calibration lanes) |
| `min_calibration_improvement` | 0.005 abs | Calibration must improve by at least this (calibration lanes) |
| `max_runtime_multiplier` | 2.0x | Candidate runtime must stay within N times baseline |
| `min_slices_improved` | 1 | At least N canonical slices must show strict primary metric improvement |
| `min_hit_rate` | 0.40 | Absolute hit-rate floor on any slice |
| `walk_forward_required` | true | Gains must survive walk-forward backtest |

The decision rule is simple: **KEEP if and only if every defined gate passes**. A single failed gate means DISCARD.

## Baseline reference

From the full production backtest (seed 42, 100 trials, window 60, forward 30):

- CRPS: 0.1769
- calibration_error_p10_p90: 0.0475
- hit_rate: 0.49
- runtime: 1792 s

These values anchor the absolute thresholds. For example, `min_crps_improvement` of 0.005 means the candidate must bring CRPS below ~0.1719 to be considered a real improvement rather than noise.

## Automation

The script `research/autoresearch/scripts/validate_decision.py` operationalizes these gates:

```bash
python validate_decision.py \
    --benchmark ../benchmarks/jepa-retrieval-core-v1.yaml \
    --before '{"crps": 0.1769, "calibration_error_p10_p90": 0.0475, ...}' \
    --after  '{"crps": 0.1700, "calibration_error_p10_p90": 0.0460, ...}'
```

It exits 0 for KEEP, 1 for DISCARD, and prints per-gate pass/fail details. The `--json` flag produces machine-readable output for ledger integration.

## Active benchmarks

- [[Nine-method pipeline]] retrieval lane: `jepa-retrieval-core-v1.yaml`
- Projector calibration lane: `projector-calibration-core-v1.yaml`

## Links

- Benchmark YAMLs: `research/autoresearch/benchmarks/`
- Playbook: `research/autoresearch/playbooks/JEPA_RETRIEVAL_LANE.md`
- Validation script: `research/autoresearch/scripts/validate_decision.py`
- Baseline runner: `research/autoresearch/scripts/run_baseline_backtest.py`
