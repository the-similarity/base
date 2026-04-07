# 3D Society Simulation Plan

## Goal

Turn `the-similarity-fractal` from a terrain viewer into a true 3D simulation world where:

- agents live inside the terrain rather than floating over a symbolic map
- the world produces rich social, economic, ecological, and conflict dynamics
- the self-similarity engine observes those dynamics as multiscale signals
- recurring patterns, regime shifts, and precursor structures can be detected early
- the system is efficient enough to scale to `100+` active agents, with a path to much larger populations later

This plan intentionally does **not** start with a toy version and then bolt depth on later. The foundation should be rich from the beginning, even if the initial population count is modest.

## Core Principles

### 1. Simulation Is Authoritative

The renderer is not the world. The simulation owns truth.

- terrain state
- resources
- points of interest
- agents
- factions
- environment conditions
- events
- telemetry
- similarity observations

The 3D scene is a projection of simulation state.

### 2. Rich State, Cheap Updates

We want deep state without forcing every subsystem to run at maximum cost every frame.

- simulation ticks should be fixed-step and decoupled from render FPS
- nearby / spotlight agents can update at high fidelity
- distant / background agents can update at reduced cadence
- telemetry and similarity analysis run on structured outputs, not raw scene queries

### 3. Terrain Must Matter

The terrain is not decoration. It shapes society.

- slope affects movement cost
- water affects settlement and disease
- biome affects resources
- isolation affects trade and survival
- chokepoints affect conflict
- elevation and region boundaries affect migration and clustering

### 4. Similarity Engine Is An Observer, Not A Puppet Master

The self-similarity engine should not directly choose actions for agents.

It should:

- observe trajectories and collective signals
- identify motifs and repeated regimes
- detect anomalies
- score precursor patterns
- support forecasting
- support scenario generation and interventions

Agents still produce the world causally. The similarity engine becomes the universe's pattern memory.

## Desired Architecture

We should build toward five layers.

### 1. World Layer

Owns physical and ecological structure.

- terrain heightmap
- walkability grid
- slope grid
- water map
- biome map
- resource fields
- settlement regions
- points of interest
- climate / weather state

### 2. Agent Simulation Layer

Owns embodied and social entities.

- agent identity
- position / locomotion state
- needs
- inventory
- health / injury / disease
- knowledge / memory
- relationships
- group / faction alignment
- goals / drives / policy state

### 3. Event and Economy Layer

Owns world-changing interactions.

- resource gathering
- trade
- conflict
- alliances
- births / deaths
- migration
- disease spread
- construction / settlement growth
- cultural diffusion

### 4. Telemetry and Similarity Layer

Owns structured observability.

- global time series
- regional tensors
- network metrics
- rolling windows
- motif indexes
- precursor libraries
- anomaly scores
- regime clustering

### 5. Presentation Layer

Owns the 3D experience only.

- terrain mesh
- agent meshes / sprites / impostors
- camera and controls
- overlays
- heatmaps
- timeline
- debugging views
- intervention controls

## Target Code Structure

This is the recommended shape inside `the-similarity-fractal`.

```text
the-similarity-fractal/
  3d_sim_plan.md
  index.html
  src/
    app.js
    fractal.js
    terrain-renderer.js
    sim/
      engine.js
      tick-scheduler.js
      world-state.js
      agent-state.js
      environment-system.js
      movement-system.js
      perception-system.js
      decision-system.js
      interaction-system.js
      economy-system.js
      disease-system.js
      faction-system.js
      lifecycle-system.js
      telemetry-system.js
      similarity-system.js
      lod-system.js
      event-bus.js
      rng.js
    world/
      terrain-sampler.js
      nav-grid.js
      region-map.js
      poi-generator.js
      resource-field.js
      climate.js
    render/
      scene-bridges.js
      agent-renderer.js
      debug-overlays.js
      heatmap-renderer.js
    data/
      metric-schema.js
      event-schema.js
      sim-config.js
```

## Rich Foundation Requirements

These are the minimum foundations that still count as "rich."

### World Representation

We need more than a mesh. We need simulation-friendly fields derived from terrain.

Required derived maps:

- `height[y][x]`
- `slope[y][x]`
- `walk_cost[y][x]`
- `water[y][x]`
- `biome[y][x]`
- `resource_food[y][x]`
- `resource_material[y][x]`
- `hazard[y][x]`
- `region_id[y][x]`
- `settlement_pressure[y][x]`

These should be generated once per world and cached.

### Agent State

Each agent should start richer than "x/y + one mood."

Minimum state:

- id
- position
- velocity / current path
- home region / current region
- health
- hunger
- energy
- hydration
- stress / fear
- social need
- wealth / goods
- profession / role
- skills
- faction / group ids
- memory summaries
- local beliefs
- relationship scores
- current goal stack
- current action
- alive / injured / infected

### Event Model

Important world changes should emit events, not just mutate state silently.

Minimum events:

- move
- gather
- consume
- trade
- fight
- injury
- death
- birth
- heal
- infection
- recovery
- alliance
- betrayal
- migrate
- discover_resource
- settlement_expand
- scarcity_warning

### Telemetry Model

Telemetry must exist from the start, not as an afterthought.

Minimum global metrics per tick:

- population_alive
- births
- deaths
- injuries
- infections
- recoveries
- conflicts
- trades
- migrations
- food_stock
- material_stock
- average_hunger
- average_health
- average_stress
- inequality_gini
- faction_count
- alliance_count

Minimum regional metrics per region per tick:

- population
- deaths
- conflicts
- food_pressure
- migration_in
- migration_out
- disease_load
- wealth_density
- hostility_index

Minimum network metrics per analysis interval:

- average_relationship_valence
- polarization
- clustering
- faction modularity
- betrayal_rate
- centralization

## Simulation Model

## Time Model

Use a fixed simulation tick. Rendering remains independent.

Recommended:

- render: browser `requestAnimationFrame`
- simulation: `4-10` ticks per second initially
- telemetry aggregation: every tick
- similarity analysis: every `N` ticks or on rolling windows

This avoids tying society logic to framerate.

## Spatial Model

The sim should be `2.5D` first, not full rigid-body 3D.

That means:

- agents move in `x/z`
- height comes from terrain sampling
- terrain height is looked up, not physically simulated
- movement cost depends on slope and biome
- cliffs / water / severe slope can be blocked or penalized

This is the right efficiency tradeoff. We want embodied world logic without expensive per-agent rigid-body physics.

## Movement

Do not move agents with raw scene raycasts every frame.

Instead:

- precompute a navigation grid from the terrain
- each cell stores movement cost, height, slope, and passability
- agents plan across that grid
- renderer places them at sampled terrain height

Required movement behaviors:

- wander
- travel to POI
- gather resource
- flee
- pursue target
- migrate to better region
- return home
- patrol

## Perception

Agents should not scan the full world.

Use:

- spatial hash or region buckets for nearby agents
- field-based resource lookup
- coarse line-of-sight / visibility if needed
- region-local memory summaries

Perception layers:

- immediate neighborhood
- current region summary
- known remote regions from memory / rumor

## Decision Model

The first decision system should be rich, but still computationally controlled.

Recommended split:

- drives / needs layer
- role / profession layer
- social relationship layer
- environmental pressure layer
- event reactivity layer

Do not begin with full LLM-native cognition for everyone.

Better:

- deterministic / stochastic utility model for all agents
- optional richer reasoning for spotlight agents later
- state-driven policies that are inspectable and fast

## Economy and Survival

Survival pressure should be real immediately.

Required loops:

- food acquisition and consumption
- shelter / rest effects
- wealth and exchange
- resource depletion and regeneration
- migration when a region becomes bad
- conflict when scarcity and hostility rise

If survival is fake, the emergent patterns will be fake too.

## Society and Factions

We should start with overlapping structures, not just isolated individuals.

Minimum:

- pairwise relationships
- factions / alliances
- local social clusters
- group hostility
- recruitment / fragmentation

This matters because many repeating patterns will be collective, not individual.

## Disease and Casualty Dynamics

This matters for the self-similarity goal and should exist early.

Minimum disease model:

- infection state
- transmissibility
- severity
- recovery probability
- death risk
- region-specific spread conditions

Minimum casualty pathways:

- starvation
- violence
- disease
- environmental hazard

We need cause-specific death channels so the similarity engine can distinguish "similar curves, different mechanisms."

## Self-Similarity Integration

This is the key differentiator.

## What To Feed Into The Engine

We should formalize observables into three layers.

### Layer A: Global Signals

1D time series over ticks.

Examples:

- `deaths[t]`
- `births[t]`
- `conflicts[t]`
- `trades[t]`
- `migration[t]`
- `avg_hunger[t]`
- `avg_health[t]`
- `inequality[t]`
- `disease_load[t]`

### Layer B: Regional Signals

2D tensors over `region x time`.

Examples:

- `deaths[region, t]`
- `conflicts[region, t]`
- `food_pressure[region, t]`
- `migration_net[region, t]`
- `wealth_density[region, t]`

### Layer C: Multimetric Tensors

3D tensors over `metric x region x time`.

Examples:

- combined social stress tensor
- conflict + hunger + migration precursor tensor

## Similarity Tasks

We should support these from the start as explicit product goals.

### 1. Motif Search

Ask:

- where have we seen a similar pattern before?
- in this run?
- across previous runs?

### 2. Regime Detection

Classify windows into coarse states such as:

- stable
- scarcity rising
- fragmented conflict
- epidemic
- recovery
- collapse cascade

### 3. Precursor Matching

Given the current window, search for historically similar windows and examine what followed.

Example:

- current pattern: rising hunger + outward migration + increased local hostility
- matched prior windows
- later outcome: casualty spike in `10-20` ticks

### 4. Cross-Scale Self-Similarity

Check if local unrest resembles broader systemic unrest.

Examples:

- one valley conflict wave resembles prior world-scale conflict regime
- a settlement-level collapse mirrors district-level decline

### 5. Anomaly Detection

Identify windows that are not well-explained by prior motifs.

This is critical because it tells us whether we are seeing:

- noise
- a known pattern
- a new emergent regime

## Forecasting Design

Forecasting should be analogue-based and contextual.

We should not claim:

- "the shape looks similar, therefore the future is guaranteed"

We should do:

- nearest-neighbor historical matches
- outcome distributions of matched windows
- confidence intervals
- mechanism labels

Each forecast window should include:

- signal shape
- world context
- causal context

Context fields:

- region water access
- biome
- weather regime
- food supply
- disease state
- faction polarization
- settlement density
- policy / intervention state

## Efficiency Strategy

This project must be rich, but not stupidly expensive.

### Required Efficiency Features From The Start

#### 1. Fixed-Step Sim

- do not run decisions at render FPS

#### 2. LOD For Agents

At least three tiers:

- spotlight
- active
- background

Suggested behavior:

- spotlight: full perception + social reasoning every tick
- active: full survival / movement / event response every tick, reduced social detail
- background: coarse updates every `N` ticks using summaries

#### 3. Terrain-Derived Navigation Cache

- no per-agent expensive mesh raycasts as the main logic path

#### 4. Batched Data Structures

Even if we start in JS objects, we should design for later conversion to more compact arrays.

#### 5. Headless Mode

The simulation must be able to run without 3D rendering so we can generate many runs for pattern mining.

This is essential for your self-similarity engine.

## Implementation Phases

The phases below are ordered to preserve rich foundations, not to build a toy.

## Phase 1: World Extraction and Sim Kernel

Deliverable:

- a terrain-backed world state that can step independently of rendering

Tasks:

- create `src/sim/engine.js`
- create `src/sim/world-state.js`
- create `src/world/terrain-sampler.js`
- create `src/world/nav-grid.js`
- derive walkability, slope, water, biome, and region maps from current terrain output
- create fixed-step scheduler
- allow renderer to read world state rather than own it

Exit criteria:

- world can load in headless mode
- nav grid is inspectable
- regions and POIs exist on terrain

## Phase 2: Embodied Agents and Survival Loops

Deliverable:

- agents can survive, move, gather, consume, rest, and die inside the 3D terrain world

Tasks:

- create agent state schema
- create movement system on nav grid
- create needs system
- create resource field system
- create basic POI assignment
- implement death channels

Exit criteria:

- `50-100` agents can roam and survive on terrain
- deaths happen for identifiable reasons
- no renderer-owned truth

## Phase 3: Social Layer and Collective Structure

Deliverable:

- social relationships, factions, migration, and conflict begin to produce structured society

Tasks:

- relationship system
- faction / alliance system
- conflict resolution
- migration system
- region pressure summaries
- social event bus

Exit criteria:

- alliances and conflict patterns emerge
- regions become socially differentiated
- telemetry reflects collective shifts

## Phase 4: Telemetry and Pattern Memory

Deliverable:

- the world emits structured multiscale signals suitable for the self-similarity engine

Tasks:

- create telemetry schema
- record global metrics per tick
- record regional metrics per tick
- record event streams with causes
- build rolling window extraction
- serialize runs for offline analysis

Exit criteria:

- a full run can be exported as structured signals
- global and regional metric history is queryable

## Phase 5: Similarity Analysis Integration

Deliverable:

- your engine can index sim runs, search motifs, and score precursor risk

Tasks:

- create `src/sim/similarity-system.js`
- define analysis windows
- define feature sets
- run motif search over rolling windows
- classify repeated regimes
- estimate analogue-based casualty risk
- render overlays for detected regimes and warnings

Exit criteria:

- current world state can be compared to historical windows
- top analogue windows are retrievable
- risk forecasts are exposed in UI/debug output

## Phase 6: Intervention and Scenario Testing

Deliverable:

- the world can test "what if" policies against current or historical precursor states

Tasks:

- food-drop intervention
- migration controls
- diplomacy boost
- quarantine / disease response
- region resource injection
- compare alternate futures from similar precursor states

Exit criteria:

- interventions change outcome distributions
- similarity engine can compare with and without intervention trajectories

## Initial Build Order

This is the actual first sequence I would implement.

1. `world-state.js`
2. `terrain-sampler.js`
3. `nav-grid.js`
4. `engine.js`
5. `agent-state.js`
6. `movement-system.js`
7. `environment-system.js`
8. `telemetry-system.js`
9. `event-bus.js`
10. `lod-system.js`
11. `decision-system.js`
12. `interaction-system.js`
13. `similarity-system.js`

This order gives us real world structure first, then real agents, then observability, then analysis.

## Data Contracts

We should standardize a few core contracts immediately.

### World Snapshot

```js
{
  tick,
  terrain: {
    size,
    worldScale,
    heightMap,
    slopeMap,
    waterMap,
    biomeMap,
    regionMap,
    navGrid,
  },
  environment: {
    weather,
    temperature,
    diseasePressure,
    resourceFields,
    pois,
  },
  agents: [...],
  factions: [...],
  events: [...],
  telemetry: {...},
}
```

### Agent Snapshot

```js
{
  id,
  alive,
  position: { x, y, z },
  regionId,
  needs: { hunger, energy, hydration, social, stress },
  health: { hp, injury, infection, diseaseSeverity },
  inventory,
  role,
  factionId,
  relationships,
  memorySummary,
  currentGoal,
  currentAction,
}
```

### Telemetry Slice

```js
{
  tick,
  global: {...},
  regional: {
    [regionId]: {...}
  },
  network: {...}
}
```

## Product Views We Should Eventually Add

These views will make the system usable as a real simulation instrument.

- terrain view
- agent view
- faction view
- resource heatmap
- migration flow view
- conflict heatmap
- disease spread view
- telemetry timeline
- pattern match browser
- analogue explorer
- precursor warning panel

## Risks

### 1. Overusing LLMs Too Early

This will make the system slow and hard to scale.

Use LLMs only for spotlight depth later, not as the base cognition engine.

### 2. Treating Mesh Queries As Simulation

That will destroy performance.

Use derived grids and cached world fields for logic.

### 3. Confusing Similarity With Causality

Pattern matches need context and mechanism labels.

### 4. Building Presentation Before Telemetry

If we skip telemetry discipline, the similarity system will be blind later.

### 5. Flattening Everything Into One Giant Loop

Keep systems modular so they can be profiled, reduced, or moved off-thread later.

## Success Criteria

This plan is working if, after implementation, we can say:

- the 3D terrain world is the real simulation environment, not just a renderer
- agents survive, move, group, trade, fight, migrate, and die because of terrain and society
- we can run the simulation headless
- every run emits rich multiscale telemetry
- the self-similarity engine can retrieve prior analogue patterns
- the system can estimate risk of outcomes such as casualty spikes from precursor motifs

## Immediate Next Step

Begin Phase 1 in the fractal project itself:

- create the simulation kernel and world extraction modules
- make terrain-derived nav / slope / region maps first-class data
- stop treating the current scene as the source of truth

That is the point where this project becomes a real universe instead of a terrain demo.
