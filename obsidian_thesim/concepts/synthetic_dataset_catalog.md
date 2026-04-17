# Synthetic Dataset Catalog

Register, list, and inspect synthetic datasets via CLI and API. Implemented in `the_similarity/synthetic/catalog.py`.

## What it does

The catalog bridges synthetic run outputs (parquet files, scorecards) with the platform's `DatasetSpec` registry. When a synthetic run completes, the catalog reads the run directory, extracts file metadata (row count, column count, SHA-256 checksum), and registers the result as a `DatasetSpec` in the platform registry.

## DatasetSpec fields

A catalog entry maps to the platform's `DatasetSpec` contract:

| Field | Source |
|-------|--------|
| `dataset_id` | Auto-generated or `"promoted:<name>"` for promoted datasets |
| `name` | User-provided or derived from run directory |
| `version` | Run timestamp or `"promoted"` |
| `source` | `"synthetic:<run_id>"` linking back to the generation run |
| `metadata` | Row count, column count, file checksum, scorecard summary |

## Dataset card

Richer than the raw spec. `get_dataset_card()` combines:
- Registry row (DatasetSpec fields)
- Scorecard summary: headline metrics (fidelity score, privacy passed/failed, utility gap)
- File paths to artifacts (synth.parquet, scorecard.json)
- Privacy status from the scorecard

The card is what the API and CLI present to users -- a single view of a dataset's identity, quality, and provenance.

## CLI commands

Via `python -m the_similarity.synthetic.cli`:
- `catalog register <run_dir>` -- read a run directory, build a DatasetSpec, register in the platform registry
- `catalog list` -- list all synthetic datasets with summary columns
- `catalog show <dataset_id>` -- display the full dataset card for a specific dataset

## API

- `GET /platform/datasets/{id}/card` -- returns the dataset card as JSON, calls `get_dataset_card()` under the hood

## Links

- Code: `the_similarity/synthetic/catalog.py`
- Platform registry: [[platform_registry]]
- Promotion: [[generator_comparison]]
- Batch context: [[batch3 synthetic copies v2 2026-04-17]]
