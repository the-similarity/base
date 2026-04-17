# Batch 3: Synthetic Copies v2 (2026-04-17)

Decision record for the Copies v2 batch, shipped as 5 parallel agent PRs.

## What was decided

Extend the synthetic copies pipeline from a single generator (block bootstrap) to a multi-generator system with comparison, expanded privacy, and a dataset catalog.

## The batch

| Agent | Deliverable | Status |
|-------|-------------|--------|
| Agent 1 | GaussianCopulaGenerator | Parallel PR |
| Agent 2 | ComparisonRunner + promotion logic | Parallel PR |
| Agent 3 | Expanded privacy scorecard (attribute inference, holdout leakage, tail exposure) | Parallel PR |
| Agent 4 | Synthetic dataset catalog | Parallel PR |
| Agent 5 | Tests, demos, docs (this agent) | Parallel PR |

## Alternatives considered

1. **TimeGAN as the second generator.** Rejected: requires a torch dependency we don't want to add yet. Gaussian copula is pure numpy/scipy and ships without new deps.

2. **Formal differential privacy instead of expanded heuristic privacy.** Rejected for v2: DP noise injection changes the generator output distribution and requires careful epsilon accounting. The heuristic scorecard is a stepping stone — it catches obvious leaks now while we design the DP layer properly.

3. **Full Pareto-front comparison.** Rejected: adds UI/UX complexity. A single composite metric is easier to automate and explain. Pareto front is a v3 feature.

4. **Customer-uploaded source data in v2.** Deferred: requires an upload endpoint, schema validation, and storage infrastructure. v2 focuses on the generator and scoring layer; source data is still local CSV/parquet.

## Why this order

- The block bootstrap proved the pipeline works (v1).
- Adding a second generator forces us to build comparison infrastructure, which is the real value — the system now scales to N generators without manual intervention.
- Privacy expansion is independent of generators and can land in parallel.
- The catalog is the persistence layer that ties everything together for the platform API and future UI.

## Risks

- **Merge conflicts across 5 parallel PRs.** Mitigated by giving each agent a distinct file scope and avoiding shared hot files (_MOC.md, pyproject.toml, etc.).
- **GaussianCopulaGenerator quality.** The copula may produce poor fidelity on non-stationary financial data. This is acceptable — the comparison runner will demote it automatically.
- **Privacy scorecard false confidence.** Users may interpret "privacy passed" as a formal guarantee. The vision doc and scorecard docstrings are explicit that these are heuristics.

## Links

- Vision: `vision/synthetic_copies_v2.md`
- Demo: `examples/synthetic_copies_comparison.py`
- Integration test: `the_similarity/tests/test_synthetic_copies_v2.py`
- Concepts: [[gaussian_copula_generator]], [[generator_comparison]]
