# NarrativeSchema

The intermediate representation between natural-language text and a compiled trajectory in the [[NL-to-time-series]] pipeline.

## Fields

| Field | Type | Values | Notes |
|-------|------|--------|-------|
| `direction` | str | "up", "down", "sideways" | Overall price direction |
| `magnitude` | str | "sharp", "moderate", "mild" | Strength modifier (>10%, 3-10%, <3%) |
| `duration_days` | int | positive int | Trading days the scenario spans |
| `volatility` | str | "high", "normal", "low" | Volatility regime |
| `catalyst_keywords` | list[str] | any | Keywords that triggered parse decisions |
| `raw_text` | str | any | Original narrative, preserved for provenance |

## v1 Parser

Keyword-based. Scans hardcoded word lists in priority order:
- **Direction**: down-words ("crash", "plunge") checked first, then up-words ("rally", "surge"), then sideways-words ("range-bound", "flat"). First match wins.
- **Magnitude**: sharp-words checked first, then mild-words. Default: "moderate".
- **Duration**: regex for "N days/weeks/months" with trading-day conversion (1 week = 5d, 1 month = 21d). Default: 60 days.
- **Volatility**: high-vol words checked first, then low-vol. Default: "normal".

Limitations: no context understanding, no negation handling ("not a crash" still parses as crash), no multi-phase support.

## Code

- Defined in: `examples/nl_to_timeseries_demo.py` (NarrativeSchema dataclass)
- Parser: `parse_narrative()` in same file
- Tests: `the_similarity/tests/test_nl_ts_e2e.py`

## See also

- [[trajectory_compiler]] — consumes NarrativeSchema to produce trajectories
- `vision/nl_to_timeseries.md` — full roadmap
