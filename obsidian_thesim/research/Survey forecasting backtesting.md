# Survey forecasting backtesting

**Repo source:** `research/methods/05-pattern-forecasting-backtesting.md`  
**Full write-up in vault:** [[05-pattern-forecasting-backtesting]]

## Friendly summary

**Analogs** give **ensemble futures** (fan). **Walk-forward** checks if those fans **lie** or **help**. **Calibration** asks: did our 90% bracket really catch ~90%?

## What we extracted

- **Analog ensembles:** top matches → **percentile cones**.
- **Calibration trap:** most prediction intervals are **too narrow** in the wild.
- **Walk-forward** = roll the pretend-today window; catch **overfitting**.
- **Metrics:** hit rate, MAE/RMSE, **[[CRPS score|CRPS]]**, coverage, reliability diagrams.
- **Landscape:** chart platforms vs **arbitrary subsequence + multi-lens** stance (see [[Product story and competition]]).
- **Foundation-model reality check:** general time-series LLM-style models often **weak** in finance zero-shot; domain structure still matters.

## Topic nodes

- [[Analog forecasting]]
- [[Fan charts and forecast cones]]
- [[Confidence decay]]
- [[Backtesting and walk-forward]]
- [[Calibration and coverage]]
- [[CRPS score]]
- [[Why pattern match is hard]]

## Related

- [[Research hub]]
- [[Forecast cone in plain English]]
