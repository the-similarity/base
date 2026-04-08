# Why pattern match is hard

**Markets forget slowly and change suddenly.** A pattern that “worked” in one decade may mean nothing next year.

## Common pitfalls

- **Overfitting:** tuning on past until it looks perfect — fails on new data. Mitigation: [[Backtesting and walk-forward]].
- **Overconfident bands:** claiming 90% coverage when reality hits 70%. Mitigation: [[Calibration and coverage]].
- **Single-metric illusions:** two series can look alike for the wrong reason. Mitigation: [[Why nine lenses]].

## What serious systems do

Use **multiple independent views**, **honest uncertainty**, and **out-of-sample testing**. That is the spirit of this project — not “one magic pattern line.”

## Related

- [[Survey forecasting backtesting]]
- [[The question we answer]]
