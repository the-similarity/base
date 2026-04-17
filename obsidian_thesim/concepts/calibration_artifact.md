> [!warning] Status: placeholder
> Duplicates data from BacktestReport.calibration(). Exists for registry convenience.

# Calibration Artifact

## What it is

The **calibration artifact** captures per-percentile calibration quality for a backtest run. It answers: "when we say P10, does the actual outcome fall below that level ~10% of the time?"

## Per-percentile calibration

The backtester computes calibration as a dict mapping percentile -> observed frequency:

```
{10: 0.12, 25: 0.28, 50: 0.49, 75: 0.73, 90: 0.88}
```

A perfectly calibrated model has `observed == expected` at every percentile. The calibration dict is stored in `summary["calibration"]` with string keys (JSON safety).

## What good vs bad looks like

### Good calibration
```
P10: 0.10  P25: 0.24  P50: 0.51  P75: 0.76  P90: 0.89
```
All observed frequencies are within ~2 percentage points of their nominal percentile. Grade: **A**.

### Moderate calibration
```
P10: 0.15  P25: 0.30  P50: 0.55  P75: 0.70  P90: 0.85
```
Systematic 5-point drift — the cone is slightly too narrow (upper percentiles undershoot, lower overshoot). Grade: **B** or **C**.

### Bad calibration
```
P10: 0.25  P25: 0.40  P50: 0.60  P75: 0.65  P90: 0.75
```
The P10/P90 interval only covers 50% of outcomes instead of 80%. The cone is dangerously narrow. Grade: **D** or **F**.

## Calibration grade

The enriched adapter maps average absolute calibration error to a letter grade:

| Grade | Avg abs error | Interpretation |
|-------|--------------|---------------|
| A | < 0.03 | Excellent — cone widths match reality |
| B | 0.03 - 0.06 | Good — minor drift, usable |
| C | 0.06 - 0.10 | Fair — cone may be too narrow or wide |
| D | 0.10 - 0.15 | Poor — review before acting |
| F | > 0.15 | Unreliable — do not use |

## How to interpret

1. Check the grade first. A or B = proceed. C = inspect per-percentile. D/F = flag.
2. Look for asymmetry: if lower percentiles are accurate but upper ones are off, the cone is asymmetrically miscalibrated (common in trending markets).
3. Compare across seeds: a model that grades A with seed=42 but D with seed=314 has high calibration variance — the [[trust_artifact|trust score]] should reflect this.

## Code paths

- Backtester: `the_similarity/core/backtester.py` — `BacktestReport.calibration` property
- Metrics: `the_similarity/core/metrics.py` — `calibration()` function
- Adapter: `the_similarity/platform/adapters/finance.py` — stamps `calibration` and `calibration_grade` into summary
- Related test: `the_similarity/tests/test_finance_operating.py`

## Related

- [[trust_artifact]] — trust score incorporates calibration error
- [[finance_review]] — review workflow checks calibration_grade
- [[Calibration and coverage]] — deeper topic on calibration theory
