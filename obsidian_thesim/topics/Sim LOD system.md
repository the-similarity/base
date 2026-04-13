# Sim LOD system

Level-of-Detail for agents in the [[3D Society Simulation]]. Keeps the sim efficient by reducing computation for distant or unimportant agents.

## Three tiers

| Tier | Update frequency | What runs |
|------|-----------------|-----------|
| **Spotlight** | Every tick | Full perception + social reasoning + all decision actions |
| **Active** | Every tick | Full survival/movement/events, reduced social detail |
| **Background** | Every N ticks | Coarse updates using region summaries |

## Classification

Agents are classified by distance from a configurable focus point (e.g., camera position or a named agent). Config parameters:
- `spotlightRadius` — agents within this distance get full fidelity
- `activeRadius` — agents within this get active tier
- `backgroundTickInterval` — how often background agents update (default: every 4 ticks)

## Why this matters

The plan targets 100+ agents initially. Without LOD, every agent running full perception + social reasoning every tick would be O(n^2) in the spatial hash lookups alone. LOD reduces the effective agent count for expensive operations to the spotlight + active set.

## Source

- `the-similarity-fractal/src/sim/lod-system.js`
