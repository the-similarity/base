# Batch 3 Slop Audit 2026-04-17

Post-ship quality check on Synthetic Copies v2 (PRs #167-#171).

## Verdict: mostly clean, no cleanup PR needed

### Minor issues (accepted)

1. **Copula tests (13)** — asked for 8-10, got 13. Borderline padding. Only the correlation-preservation test truly validates the copula; rest are shape/protocol/determinism that any generator has.

2. **Comparison tests (14)** — disproportionate for a ranking function that's 3 lines of sorted(). Not as bad as Batch 2's 50-test risk flag situation.

3. **`compare_cli.py` is a separate file** — 208 lines for an argparse wrapper. Could be a subcommand in `cli.py`. Two CLI entry points for synthetic now. Minor architectural debt.

4. **Promotion uses hardcoded `"promoted:"` prefix** — `dataset_id="promoted:<name>"` for O(1) lookups. Fragile convention, not a contract. Works but would break if someone registers datasets with different ID patterns.

### Genuinely solid

- **Copula implementation** — proper empirical CDF + correlation extraction + nearest-PSD projection. Real math.
- **Privacy heuristics** — holdout leakage and attribute inference are real probes. `max(weighted_sum, worst_single_risk)` scoring is fail-closed.
- **Catalog dataset card** — actually reads scorecard data from metadata.
- **Honest docstrings** — privacy module still says "heuristic, not formal guarantees."

### Comparison to Batch 2

Batch 2 had: uncalibrated trust formula, placeholder review workflow, 50 padded tests, aspirational docs. Required a cleanup PR (#166).

Batch 3: no cleanup needed. The CI budget pressure + explicit "no padding" instructions in agent prompts worked.

See also: [[batch2 finance operating product 2026-04-17]], [[ci correctness gap 2026-04-17]]
