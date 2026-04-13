# Faction emergence

Factions in the [[3D Society Simulation]] are **emergent**, not pre-assigned. They form dynamically from social relationship clusters.

## Formation

When agents with strong mutual relationships (valence above threshold) cluster geographically, a faction crystallizes. The system detects these clusters each tick and assigns faction IDs.

## Faction state

Each faction tracks:
- **Members** — set of agent IDs
- **Inter-faction hostility** — pairwise hostility scores with other factions
- **Alliances** — set of allied faction IDs

## Dynamics

| Event | Trigger |
|-------|---------|
| **Recruitment** | Unaffiliated agent near high-relationship faction members |
| **Fragmentation** | Internal hostility exceeds threshold → faction splits |
| **Alliance** | Two factions with positive mutual sentiment |
| **Betrayal** | Faction attacks an allied faction's member |

Emits events: `alliance`, `betrayal` — tracked in [[Telemetry and observability]].

## Why emergent factions matter

Pre-assigned factions produce predictable dynamics. Emergent factions create the kind of **self-organizing complexity** that generates non-trivial patterns for the [[Self-similarity]] engine to discover. Faction modularity, polarization, and betrayal rate are all network-level telemetry metrics.

## Source

- `the-similarity-fractal/src/sim/faction-system.js`
