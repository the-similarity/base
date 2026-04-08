# The question we answer

In one sentence:

> **“Has this kind of market pattern happened before — and if so, what tended to happen next?”**

## What that means day-to-day

1. You pick a **window** of recent prices (a subsequence), like “the last 60 trading days.”
2. The engine **searches history** for other windows that are **similar** — not only by eye, but with several math lenses (shape, scaling, dynamics, topology, predictiveness).
3. It builds a **fan of possible futures** from what followed those historical matches — a **forecast cone** — and tracks whether those bands are **honest** (calibrated) when we [[Backtesting and walk-forward|backtest]].

## Important honesty note

Similarity is **not** a guarantee. Markets can regime-shift. That is why we care about **many methods**, **backtesting**, and **calibration** — not a single “magic score.”

## Related

- [[How the matcher works (simple)]]
- [[Why pattern match is hard]]
- [[Product story and competition]]
