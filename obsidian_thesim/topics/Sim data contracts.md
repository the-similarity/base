# Sim data contracts

Standardized data shapes shared across all modules in the [[3D Society Simulation]].

## World Snapshot

The complete simulation state at one tick, returned by `engine.getSnapshot()`:

```js
{
  tick,
  terrain: { size, worldScale, heightMap, slopeMap, waterMap, biomeMap, regionMap, navGrid },
  environment: { weather, temperature, diseasePressure, resourceFields, pois },
  agents: [...],
  factions: [...],
  events: [...],
  telemetry: {...}
}
```

## Agent Snapshot

Per-agent state, rich from the start:

```js
{
  id, alive,
  position: { x, y, z },
  regionId,
  needs: { hunger, energy, hydration, social, stress },
  health: { hp, injury, infection, diseaseSeverity },
  inventory: [{ type, quantity }],
  role,           // gatherer, hunter, trader, builder, healer, soldier, leader
  factionId,
  relationships,  // Map<agentId, valence>
  memorySummary,
  currentGoal,
  currentAction
}
```

## Telemetry Slice

Per-tick observability data:

```js
{
  tick,
  global: { population_alive, births, deaths, ... },
  regional: { [regionId]: { population, deaths, conflicts, ... } },
  network: { polarization, clustering, faction_modularity, ... }
}
```

## Event

World-changing interactions emitted through the EventBus:

```js
{ type, tick, agentId, ...payload, timestamp }
```

17 event types: MOVE, GATHER, CONSUME, TRADE, FIGHT, INJURY, DEATH, BIRTH, HEAL, INFECTION, RECOVERY, ALLIANCE, BETRAYAL, MIGRATE, DISCOVER_RESOURCE, SETTLEMENT_EXPAND, SCARCITY_WARNING.

## Source

- `the-similarity-fractal/src/data/event-schema.js`
- `the-similarity-fractal/src/data/metric-schema.js`
- `the-similarity-fractal/src/data/sim-config.js`
