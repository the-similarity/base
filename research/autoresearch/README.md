# Autoresearch framework

This directory holds the **repo-native autoresearch operating system** for The Similarity.

The goal is to make autonomous research:
- bounded,
- benchmarked,
- reversible,
- and durable.

## Directory layout

- `benchmarks/` — named benchmark manifests. Agents should reference these IDs instead of inventing ad hoc evaluation slices.
- `playbooks/` — human-maintained instructions for a specific research lane.
- `ledger/` — the experiment schema and examples for append-only logging.

## Core rules

1. **Bounded write scope**
   Every lane names the exact files or directories it may edit.

2. **Frozen evaluator**
   Agents may not modify the benchmark definition, acceptance rules, or evaluation harness during a lane run.

3. **Fixed budget**
   Every lane specifies a fixed trial count, seed policy, and runtime/compute ceiling.

4. **Keep / discard discipline**
   A run is kept only if it improves the named scorecard. Otherwise it is reverted or left unpromoted.

5. **Append-only ledger**
   Every run gets a machine-readable log record, including failures.

## Canonical log location

Production runs should append records to:

- `progress/autoresearch/experiments.jsonl`

A checked-in example is provided as:

- `progress/autoresearch/experiments.template.jsonl`

## Recommended initial usage

Start with the JEPA retrieval lane:
- benchmark: `jepa-retrieval-core-v1`
- playbook: `playbooks/JEPA_RETRIEVAL_LANE.md`

## What this framework is for

Use it for:
- JEPA representation experiments,
- method ablations,
- projector calibration variants,
- weight / configuration searches with fixed benchmarks.

Do **not** use it for:
- vague literature review,
- architecture brainstorming,
- unconstrained production refactors,
- experiments without a fixed scorecard.
