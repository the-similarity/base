# 3D Society Simulation

The simulation layer transforms `the-similarity-fractal` from a terrain viewer into a living world. Agents inhabit the terrain, survive, trade, fight, migrate, and die — while the [[Self-similarity]] engine observes emergent patterns as multiscale signals.

## Architecture — five layers

| Layer | Owns | Key modules |
|-------|------|-------------|
| **World** | Terrain, walkability, biome, resources, POIs, climate | `terrain-sampler.js`, `nav-grid.js`, `region-map.js`, `resource-field.js`, `poi-generator.js`, `climate.js` |
| **Agent Simulation** | Identity, needs, health, inventory, relationships, goals | `agent-state.js`, `lifecycle-system.js`, `movement-system.js`, `perception-system.js`, `decision-system.js` |
| **Event & Economy** | Trade, conflict, alliances, disease, migration | `interaction-system.js`, `economy-system.js`, `disease-system.js`, `faction-system.js` |
| **Telemetry & Similarity** | Time series, regime detection, motif search, anomaly scoring | `telemetry-system.js`, `similarity-system.js` |
| **Presentation** | 3D scene, agent meshes, overlays, heatmaps | `scene-bridges.js`, `agent-renderer.js`, `debug-overlays.js`, `heatmap-renderer.js` |

## Core principle: simulation is authoritative

The renderer is **not** the world. The simulation owns truth — terrain state, agents, events, telemetry. The 3D scene is a projection of simulation state. This allows [[Headless simulation mode]] for batch pattern mining.

## Spatial model

The sim is 2.5D: agents move in x/z, height comes from terrain sampling. Movement cost depends on slope and biome. No per-agent rigid-body physics — embodied world logic without the expense.

## Time model

Fixed-step simulation ticks (4–10/sec), decoupled from render FPS. Telemetry aggregates every tick. [[Similarity analysis]] runs on rolling windows every N ticks.

## Related

- [[Agent decision model]] — utility-based action scoring
- [[Navigation grid]] — A* pathfinding on terrain-derived walkability
- [[Telemetry and observability]] — what the sim emits for pattern analysis
- [[Disease and casualty dynamics]] — SIR model + cause-specific death channels
- [[Faction emergence]] — dynamic social structures from relationship clusters
- [[Sim LOD system]] — three-tier agent update fidelity
- [[Sim data contracts]] — World Snapshot, Agent Snapshot, Telemetry Slice

## Source files

- Plan: `the-similarity-fractal/3d_sim_plan.md`
- All modules: `the-similarity-fractal/src/sim/`, `src/world/`, `src/render/`, `src/data/`
