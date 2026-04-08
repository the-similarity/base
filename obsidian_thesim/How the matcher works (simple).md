# How the matcher works (simple)

**Plain idea:** cheap screens first, expensive math only on the best candidates — like a funnel.

## Two tiers

### Tier 1 — fast filters

Tools such as [[SAX symbolic approximation|SAX]] (symbolic summaries) and [[Matrix Profile|matrix profile]] / MASS-style search help **throw away** most of history quickly while **keeping** the promising windows. Think: “don’t run a hundred expensive tests on every single day.”

### Tier 2 — deep scoring (nine lenses)

On the survivors, we score similarity with **nine different methods** (each captures something different: shape, correlation after alignment, scaling laws, frequency fingerprints, dynamical “engine” match, topology, information flow, etc.). See [[topics/Methods index]].

**In the current codebase**, all nine are implemented and wired into the tiered pipeline (see [[Engine map]] for file paths).

## After matching

[[Forecast cone in plain English]] turns the **forward paths** of the best matches into **percentile bands** (a cone). Optional **[[Confidence decay|confidence decay]]** and [[Koopman operator|Koopman]]-informed blending refine how uncertainty grows with time.

## Related

- [[Nine-method pipeline]]
- [[topics/Code — matcher tiers and modules]] — implementation detail
- [[Survey forecasting backtesting]]
- [[The question we answer]]
