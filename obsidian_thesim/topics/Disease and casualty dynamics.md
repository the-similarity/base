# Disease and casualty dynamics

Disease and death mechanics in the [[3D Society Simulation]] exist early because they produce the **signals the similarity engine needs**. The plan states: "We need cause-specific death channels so the similarity engine can distinguish 'similar curves, different mechanisms.'"

## Disease model (SIR-style)

States: HEALTHY → INFECTED → RECOVERING → IMMUNE (or DEAD)

| Parameter | Description |
|-----------|-------------|
| Transmission radius | How close agents must be for spread |
| Transmission probability | Per-tick chance when in radius of infected agent |
| Severity rate | How fast infection worsens (0→1 scale) |
| Recovery probability | Per-tick chance of clearing infection |
| Death threshold | Severity level that risks death |

Modifiers: region density, [[Climate]] disease pressure, proximity to water (sanitation).

## Cause-specific death channels

Four distinct pathways, each trackable in telemetry:

1. **Starvation** — hunger reaches 1.0
2. **Violence** — hp drops to 0 from combat damage
3. **Disease** — severity reaches threshold with failed recovery check
4. **Environmental hazard** — terrain-based (cliffs, exposure)

## Why this matters for [[Self-similarity]]

Different death channels produce different signal shapes. A famine-driven casualty spike looks different from a war-driven one or an epidemic. The similarity engine can:
- Match "rising hunger + outward migration + local hostility" to historical windows
- Predict "casualty spike in 10-20 ticks" from precursor patterns
- Distinguish mechanism even when aggregate curves look similar

## Source

- `the-similarity-fractal/src/sim/disease-system.js`
- `the-similarity-fractal/src/sim/lifecycle-system.js`
