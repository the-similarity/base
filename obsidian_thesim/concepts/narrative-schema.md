# Narrative Schema

The `the_similarity/narrative/` package provides structured representation of free-text market narratives.

## What it does

Converts text like *"The market crashed sharply for 5 days, then consolidated"* into a `NarrativeSequence` of typed events with intensity, duration, and transitions.

## Key contracts

- **`NarrativeType`** — 8 canonical regimes: CRASH, RALLY, CONSOLIDATION, BREAKOUT, REVERSAL, DRIFT, SPIKE, MEAN_REVERSION
- **`NarrativeEvent`** — event_type + intensity (0-1) + duration_bars + description
- **`NarrativeTransition`** — from_event + to_event + trigger + sharpness (0-1)
- **`NarrativeSequence`** — ordered events + transitions + source_text + metadata

All support `to_dict()` / `from_dict()` for JSON serialization.

## Parser

`parse_narrative(text)` is a **rule-based keyword parser** (not NLU). One event per sentence, first keyword match wins. Intensity from modifiers ("slightly"=0.3, "sharply"=0.8). Duration from time phrases ("for 3 days" -> 3).

Designed as a baseline/fallback. Future ML-based parsers should produce the same `NarrativeSequence` output.

## Code paths

- Contracts: `the_similarity/narrative/contracts.py`
- Parser: `the_similarity/narrative/parser.py`
- Examples: `the_similarity/narrative/data/example_narratives.json`
- Tests: `the_similarity/tests/test_narrative_parser.py`

## Links

- [[synthetic-data]] — narratives feed into synthetic generation
- [[projector]] — narrative events map to quantitative forecast parameters
