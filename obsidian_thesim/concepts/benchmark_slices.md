# Benchmark slices — canonical catalogue

**What:** A single, append-only YAML catalogue of every benchmark slice every autoresearch lane uses. Eliminates the "one lane fixes a slice, another lane keeps running the broken one" bug class.

**Code:** `research/autoresearch/slices/`

## Files

| Path | Purpose |
|---|---|
| `catalogue.yaml` | Single source of truth — every slice's id, asset, dataset_path, date window, regime_class |
| `regimes/<class>.yaml` | Per-regime bucket — lists the catalogue IDs that belong to `calm` / `crisis` / `trend` / `mean_reverting` |
| `cross_asset/*.yaml` | Pair definitions — two catalogue IDs plus a join rule |
| `validate.py` | CI-runnable invariant checker (no heavy deps) |
| `loader.py` | Public API: `load_slice`, `load_regime`, `load_cross_asset_pair`, `load_many` |

## Invariants (enforced by `validate.py`)

1. **Append-only.** Once a slice `id` is on `main` it cannot be renamed or deleted. Obsolete entries get `status: deprecated` + `successor_id:` pointer. This protects the longitudinal record in `progress/autoresearch/experiments.jsonl`.
2. `start < end`, end is not in the future, dates are strict ISO `YYYY-MM-DD`.
3. `regime_class ∈ {calm, crisis, trend, mean_reverting}` — filename stem under `regimes/` must match.
4. `dataset_path` must exist on disk when `--check-data` is set (off by default in CI — parquet data lives outside the git repo).
5. Regime YAMLs list only catalogue IDs whose `regime_class` matches the filename.
6. Cross-asset pairs: both legs exist, `join_rule ∈ {intersection, union, left_anchor, right_anchor}`, date windows overlap, `pair_id` is unique across all files.
7. Slices marked `missing_data: true` bypass disk checks — downstream runners are expected to synth-fallback.

## Regime enum

| Regime | Meaning |
|---|---|
| `calm` | Low realized vol, shallow drawdowns, no tail events. Baseline environment. |
| `crisis` | Tail-event drawdown or realized-vol spike ≥ 2x trailing 6M median. |
| `trend` | Persistent directional move (bull OR bear) with strong autocorrelation. |
| `mean_reverting` | Range-bound oscillation, low net drift vs intra-window range. |

## Adding a slice

1. Pick a kebab-case `id` that encodes the asset + window (e.g., `aapl-calm-2019`).
2. Append a new entry under `slices:` in `catalogue.yaml` — never edit an existing entry's dates.
3. Add the `id` to the matching `regimes/<class>.yaml`.
4. If it becomes part of a cross-asset pair, add a file under `cross_asset/`.
5. Run `python -m research.autoresearch.slices.validate` — must exit 0.
6. Bench lanes that want to use it reference the `id` via [[loader.py]] (`load_slice(id)`).

## Adding a cross-asset pair

1. Create `cross_asset/<pair-id>.yaml` with `pair_id`, `left`, `right`, `join_rule`, `regime_class`.
2. Both legs must already be in `catalogue.yaml`.
3. `join_rule`:
   - `intersection` — keep timestamps present in both legs (safe default for same-calendar pairs)
   - `left_anchor` / `right_anchor` — mixed-calendar pair, take nearest-prior bar from the non-anchor leg
   - `union` — outer join, forward-fill; rarely used
4. Re-run validator.

## Consumers

- `research/autoresearch/retrieval_bench/slices.yaml` — references catalogue IDs via [[run_bench.py]] Mode B
- `research/autoresearch/benchmarks/projector-v2-core-v1.yaml` — `canonical_slices.catalogue_slice_ids`
- Future: parameter-sweep lane, foundation-model bench, strategy smoke tests

## Why this exists

Before the catalogue, each lane (1A retrieval_bench, projector-v2, parameter-sweep) inlined its own date windows. A curator fixing a typo or extending a window had to change N files. A future agent running an old bench could end up comparing against slice windows that a newer bench had silently moved. This broke longitudinal CRPS comparisons. Catalogue + loader + append-only rule = one place to edit, one place to look up.

See also: [[slice_catalogue_v1_414]] for the current per-regime counts + known gaps.
