# Changelog

All notable changes to this project will be documented in this file.

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
