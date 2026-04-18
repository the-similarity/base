# Trajectory Compiler

Converts a [[narrative_schema|NarrativeSchema]] into a synthetic price trajectory (numpy array). Part of the [[NL-to-time-series]] pipeline.

## v1 Algorithm

Piecewise-linear drift + additive Gaussian noise:

1. **Drift**: `np.linspace(start_price, start_price * (1 + total_return), n)` where `total_return` is looked up from magnitude ("sharp" = 15%, "moderate" = 6%, "mild" = 2%) and sign-flipped for direction="down" or zeroed for "sideways".
2. **Noise**: `cumsum(N(0, daily_vol * start_price))` where `daily_vol` depends on volatility regime ("high" = 2.5%, "normal" = 1.2%, "low" = 0.5%).
3. **Floor**: `max(trajectory, 1.0)` to prevent negative prices.

## Limitations

- No volatility clustering (GARCH effects)
- No fat tails (Gaussian noise only)
- No mean-reversion
- No regime switching within a trajectory
- No multi-phase support
- Single univariate series only

These are intentional for v1 — the value is the end-to-end contract, not realism. The [[block_bootstrap_generator]] and [[gaussian_copula_generator]] already handle realistic generation; v2 will retrieve + blend real historical paths instead of synthesizing from scratch.

## Determinism

Uses `np.random.default_rng(seed)` — no global state touched. Same `(schema, seed, start_price)` produces bit-identical output.

## Code

- Defined in: `examples/nl_to_timeseries_demo.py` (`compile_trajectory()`)
- Tests: `the_similarity/tests/test_nl_ts_e2e.py` (TestCompileTrajectory)

## See also

- [[narrative_schema]] — input to the compiler
- `vision/nl_to_timeseries.md` — v2 plans (retrieval-grounded compilation)
