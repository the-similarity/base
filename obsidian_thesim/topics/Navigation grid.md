# Navigation grid

The nav grid is the simulation's spatial backbone in the [[3D Society Simulation]]. Instead of expensive per-agent mesh raycasts, agents plan movement on a precomputed 2D grid derived from terrain.

## Derivation

From the raw terrain heightmap, the grid computes per-cell:
- **Height** — sampled from heightmap
- **Slope** — gradient magnitude between neighboring cells
- **Walkability** — binary passable/impassable (water and cliffs blocked)
- **Movement cost** — based on slope, biome, and [[Climate]] modifiers

## Pathfinding

A* search over the grid with movement-cost-weighted edges. Each cell connects to its 8 neighbors (cardinal + diagonal). Diagonal moves cost sqrt(2) times the base cost.

Key operations:
- `findPath(startGx, startGz, endGx, endGz)` — full A* path
- `neighbors(gx, gz)` — adjacent passable cells with costs
- `worldToGrid(wx, wz)` / `gridToWorld(gx, gz)` — coordinate conversion

## Why this matters

The plan emphasizes: "Do not move agents with raw scene raycasts every frame." The nav grid turns O(n * raycast) per tick into O(n * grid-lookup) — essential for scaling to 100+ agents.

## Region map

Connected walkable areas are flood-filled into labeled regions (`RegionMap`). Regions drive:
- Agent spawn distribution
- Migration decisions (agents move to better regions)
- Regional telemetry aggregation
- Faction territory boundaries

## Source

- `the-similarity-fractal/src/world/nav-grid.js`
- `the-similarity-fractal/src/world/region-map.js`
- `the-similarity-fractal/src/world/terrain-sampler.js`
