# Synthetic contracts

Module: `the_similarity/synthetic/contracts.py` · Shipped: 2026-04-15 (PR #126).

Shared dataclasses and typing.Protocols for the synthetic data lane. Every generator and scorecard downstream of this module ([[block_bootstrap_generator]], [[fidelity_scorecard]], [[privacy_scorecard]], [[utility_scorecard]]) conforms to these types.

## Dataclasses

- **SyntheticDataset** — `data` (ndarray or DataFrame), `index`, `columns`, `provenance`.
- **Provenance** — `source_id`, `generator_name`, `generator_version`, `seed`, `created_at` (ISO8601), `params` (dict). Every synthetic artifact must carry this.
- **FidelityReport** — `marginals`, `temporal`, `cross_series` (optional), `tails`, `overall_score`, `passed`.
- **PrivacyReport** — `nn_leakage`, `memorization`, `membership_proxy`, `overall_score`, `passed`.
- **UtilityReport** — `trts`, `tstr`, `real_baseline`, `transfer_gap`, `passed`.
- **Scorecard** — bundles `dataset`, `fidelity`, `privacy`, `utility`; exposes a computed `.passed` that ANDs the three sub-reports.

## Protocols

- **GeneratorProtocol** — `name: str`, `version: str`, `fit(real) -> None`, `sample(n, seed) -> SyntheticDataset`.
- **ScorecardProtocol** — `evaluate(real, synth) -> FidelityReport | PrivacyReport | UtilityReport`.

Both are `@runtime_checkable` so `isinstance(obj, GeneratorProtocol)` works for duck-type verification in tests.

## Design choices

- stdlib `dataclasses` — no pydantic dep.
- `numpy` / `pandas` behind `TYPE_CHECKING` so `data` accepts either without forcing a runtime import at contract level.
- `iso_now()` helper for `Provenance.created_at` — single source of truth for timestamp format.

## Why this exists

Five downstream agents built simultaneously against these types; the contract PR had to land first to unblock parallel work. Treating contracts as an explicit, named, versioned artifact — not as an implicit side-effect of the first module that happens to compile — is what made the 10-agent parallel run feasible.

See [[synthetic launch 2026-04-15]] for the full launch context.
