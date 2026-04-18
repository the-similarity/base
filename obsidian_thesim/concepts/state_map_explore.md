# State Map — Explore Page

Visual exploration surface for the [[platform_registry|Platform Registry]]'s run universe.

## What it does

Renders all registered runs (finance backtests, synthetic copies, world simulations) as a 2D scatter plot on a `<canvas>`. Each run is a circle:
- **Color** encodes `kind`: finance (blue), copies (green), worlds (orange)
- **Size** encodes a quality metric: `trust_score` (finance), `fidelity` (copies), `alive_ratio` (worlds), or uniform 0.5 if unavailable

## Key interactions
- **Pan** (drag) and **zoom** (scroll wheel)
- **Hover** shows a tooltip with run_id, kind, label
- **Click** selects a run, opening a detail sidebar with metrics
- **"Find Similar"** calls `GET /platform/state/nearest/{id}` and highlights the k nearest neighbors with dashed rings
- **Cluster toggle** fetches `GET /platform/state/clusters` and draws convex hulls around cluster members

## Implementation notes
- Uses HTML5 Canvas (2D context), not Three.js/R3F — avoids a heavy dependency for what is a scatter plot
- Graham scan for convex hull computation
- Camera state stored in refs (not React state) to avoid re-renders during pan/zoom — only `draw()` is called
- `ResizeObserver` handles canvas resize with DPR scaling

## API endpoints consumed
- `GET /platform/state/projection` — array of `ProjectionPoint`
- `GET /platform/state/nearest/{run_id}?k=5` — array of `Neighbor`
- `GET /platform/state/clusters` — array of `Cluster`

Types are defined in `the-similarity-app/lib/platform-api.ts`.

## Code paths
- Page: `the-similarity-app/app/explore/page.tsx`
- API client: `the-similarity-app/lib/platform-api.ts` (fetchProjection, fetchNearest, fetchClusters)
- CSS: `the-similarity-app/app/globals.css` (`.explore-*` classes)
- Nav link: `the-similarity-app/components/nav.tsx`
