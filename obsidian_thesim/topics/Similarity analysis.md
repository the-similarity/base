# Similarity analysis (simulation)

The similarity system in the [[3D Society Simulation]] is the bridge between the sim world and the [[Self-similarity]] engine. It observes — it does not control.

## Five analysis modes

### 1. Motif search
Where has this pattern appeared before? Search rolling windows of [[Telemetry and observability]] using Euclidean nearest-neighbor. Returns top-k matches from the current run or across historical runs.

### 2. Regime detection
Classify the current window into coarse states:
- **STABLE** — metrics within normal bounds
- **SCARCITY_RISING** — food pressure increasing, hunger trending up
- **FRAGMENTED_CONFLICT** — conflict count high, factions fragmenting
- **EPIDEMIC** — disease load spiking across regions
- **RECOVERY** — metrics improving after a crisis
- **COLLAPSE_CASCADE** — multiple systems failing simultaneously

### 3. Precursor matching
Given the current window, find historically similar windows and examine what followed N ticks later. Example: "rising hunger + outward migration + local hostility" → matched to prior windows where a casualty spike followed in 10-20 ticks.

### 4. Cross-scale self-similarity
Check if local unrest resembles broader systemic patterns. One valley's conflict wave may mirror a prior world-scale conflict regime. This is the simulation analog of [[Multifractals MFDFA]] — the same structure appearing at different scales.

### 5. Anomaly detection
Score how different the current window is from any known historical pattern. High anomaly = either noise, or a genuinely new emergent regime. This distinguishes "seen before" from "never seen before."

## Design principle

The similarity engine is an **observer, not a puppet master**. Agents produce the world causally. The engine becomes the universe's pattern memory. This mirrors how the financial [[Analog forecasting]] engine observes price series without trading directly.

## Source

- `the-similarity-fractal/src/sim/similarity-system.js`
