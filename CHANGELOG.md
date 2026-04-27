# Changelog

All notable changes to this project will be documented in this file.

## [0.3.0] - 2026-04-26

The workstation became a real instrument: real metrics replace placeholders, you can pin analogs and watch the forecast respond, share a workstation view by URL, and step through everything from the keyboard.

### Added
- Pinned analogs drive the forecast — curated matches re-weight the projected cone instead of the raw top-K
- Analog detail drawer — click any match to inspect score breakdown, matched segment, and source metadata before pinning
- Multi-analog palette with rank badges and hover preview — every pinned analog gets its own color and previews its segment on hover
- Dataset dropdown showing source, last-updated, and row count for every available series
- Shareable workstation URLs — query, dataset, pinned analogs, and chart settings round-trip through the URL
- Keyboard shortcuts (`?` opens help, `1`-`6` switch ranges, `j`/`k` cycle matches, `/` focuses search, `Esc` closes panels) plus a command palette
- Visible top-K and forecast-horizon controls on the workstation toolbar
- Manual Search button — searches no longer fire on every keystroke
- Lightweight-charts "Pro" view as an alternate chart mode with axis-drag zoom, candle rendering, trackpad horizontal pan, and clickable analog overlays
- Vol-normalized analog overlay and chart-settings popover for picking how analogs scale relative to the query
- Real trust and calibration metrics in the workstation, sourced from the backtest pipeline instead of hardcoded values
- `/home` landing page with an embedded analog match segment
- `/fractal` route — standalone Three.js world sim embedded into the Next.js app
- `/demo` and `/prudent-demo` showcase pages for product walkthroughs
- `goodruns` API (`the-similarity-api/app/goodruns.py`) for surfacing high-quality historical runs
- `/healthz` alias on the API so frontend health probes succeed
- Right-panel analog preview — workstation right rail previews whichever analog is hovered or active

### Changed
- Calibration panel now reads real backtest metrics; synthetic leftovers removed
- Forecast cone scale corrected — backend curves are treated as centered returns, not absolute prices
- Workstation analog match segment fades so the query line stays readable; match segment no longer renders inside the query window
- Theme-aware marquee no longer flips to cream in dark mode
- Offline banner, empty state, and responsive breakpoints added across the workstation
- Fractal iteration slider tuning passes — capped at 10, water/forest light up past level 8 (the flatness-slider experiment was tried and reverted in this release)

### Fixed
- LensRadar viewBox widened so axis labels stop clipping
- RunRegistry uses per-thread SQLite connections so concurrent reads no longer deadlock

### For contributors
- New routes extracted: `/workstation` (split out from `/`), `/home`, `/fractal`, `/demo`, `/prudent-demo`
- Workstation component rewritten (~3,000 lines) — now consumes shared `MatchResult` types and a new URL-state library
- Test count: 1,136 backend tests across 78 files; new frontend tests for analog drawer, dataset dropdown, line-chart palette, shortcuts help, URL state, workstation pinning, and workstation search row

## [0.2.1] - 2026-04-12

### Added
- JEPA autoresearch framework: playbooks, benchmarks, and experiment ledger schema for structured research lanes
- Baseline backtest script (`research/autoresearch/scripts/run_baseline_backtest.py`) for recording reproducible walk-forward baselines before experimental signals
- Obsidian wiki entries for JEPA and Karpathy autoresearch research paths
- JEPA retrieval-core and projector-calibration benchmark manifests with guardrailed writable scopes
- Experiment ledger JSON schema for machine-readable research tracking
- Smoke baseline report for JEPA retrieval lane

### Changed
- Fixed Poetry readme path to point at existing `docs/overview/README.md`

## [0.2.0] - 2026-03-14

Initial public release with 9-method tiered pipeline, walk-forward backtester, ensemble forecasting, TradingView Pine Script mirror, and 3D terrain engine.
