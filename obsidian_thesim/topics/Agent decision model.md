# Agent decision model

Each agent in the [[3D Society Simulation]] uses a **utility-based decision system** — not LLM cognition. This keeps the sim fast enough for 100+ agents while producing rich emergent behavior.

## How it works

Every tick, each agent scores candidate actions against its current state:

| Action | Primary driver | Role bonus |
|--------|---------------|------------|
| GATHER_FOOD | hunger | gatherer, hunter |
| GATHER_MATERIAL | low inventory | builder |
| DRINK | hydration | — |
| REST | low energy | — |
| SOCIALIZE | social need | leader |
| TRADE | has surplus + nearby trader | trader |
| MIGRATE | region pressure high | — |
| FLEE | nearby threat + low hp | — |
| FIGHT | hostility + target nearby | soldier |
| PATROL | faction territory | soldier |

The highest-scoring action becomes `currentGoal` and `currentAction`. The [[Sim LOD system]] affects evaluation depth: spotlight agents evaluate all actions; background agents use a fast path (top 3 only).

## Why not LLMs?

The plan explicitly warns against LLM-native cognition for all agents early on. Deterministic/stochastic utility models are:
- Inspectable (you can read the utility scores)
- Fast (no API calls per agent per tick)
- Scalable (works for hundreds of agents)

Optional richer reasoning for "spotlight" agents can be added later without changing the base system.

## Source

- `the-similarity-fractal/src/sim/decision-system.js`
- `the-similarity-fractal/src/sim/interaction-system.js`
