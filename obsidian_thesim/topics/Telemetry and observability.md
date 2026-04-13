# Telemetry and observability

Telemetry exists from day one in the [[3D Society Simulation]] — not as an afterthought. The plan states: "If we skip telemetry discipline, the similarity system will be blind later."

## Three layers of observables

### Layer A: Global signals (1D time series over ticks)

`deaths[t]`, `births[t]`, `conflicts[t]`, `trades[t]`, `migration[t]`, `avg_hunger[t]`, `avg_health[t]`, `inequality[t]`, `disease_load[t]`

17 global metrics total, recorded every tick.

### Layer B: Regional signals (2D tensors — region x time)

`deaths[region, t]`, `conflicts[region, t]`, `food_pressure[region, t]`, `migration_net[region, t]`, `wealth_density[region, t]`

9 regional metrics per region per tick.

### Layer C: Network metrics (per analysis interval)

`average_relationship_valence`, `polarization`, `clustering`, `faction_modularity`, `betrayal_rate`, `centralization`

## What feeds into the [[Self-similarity]] engine

The telemetry system maintains **rolling windows** of configurable size. The [[Similarity analysis]] system consumes these windows to perform:

1. **Motif search** — where have we seen this pattern before?
2. **Regime detection** — classify current state (stable, scarcity, conflict, epidemic, collapse)
3. **Precursor matching** — find historical windows similar to now, examine what followed
4. **Anomaly scoring** — is this a known pattern or something new?

This is the same fundamental approach as the financial [[Analog forecasting]] engine, applied to simulation dynamics instead of price series.

## Source

- `the-similarity-fractal/src/sim/telemetry-system.js`
- `the-similarity-fractal/src/sim/similarity-system.js`
- `the-similarity-fractal/src/data/metric-schema.js`
