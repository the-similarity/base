# Event Contracts

Schemas for the world-event prediction pillar. These define the data model that flows through the entire pipeline: ingest, graph construction, retrieval, prediction, and scoring.

## Event

A world event with a date, category, severity, and feature vector.

| Field | Type | Purpose |
|-------|------|---------|
| `event_id` | str | Unique identifier (e.g. `evt-001`) |
| `name` | str | Human-readable event name |
| `category` | str | Domain tag: `economic`, `health`, `geopolitical` |
| `date_iso` | str | ISO-8601 date string |
| `date_ordinal` | int | Days since epoch, used for temporal distance |
| `severity` | float | 0-1 scale, used in feature vector |
| `description` | str | Free-text description |
| `feature_vector` | ndarray | Optional pre-computed embedding; if None, derived from metadata |

Converts to `StateVector` via `to_state_vector()` for graph construction. The default 4-D embedding is `[date_ordinal_scaled, severity, category_hash, description_len_scaled]` — intentionally simplistic for v1.

## EventSeries

Ordered sequence of related events (e.g., all Fed rate decisions). Not yet used in v1 but part of Agent 1's contract for temporal chain analysis.

## ForecastQuestion

A binary (yes/no) forecast question tied to an event.

| Field | Type | Purpose |
|-------|------|---------|
| `question_id` | str | Unique identifier |
| `event_id` | str | FK to Event |
| `text` | str | The question text |
| `resolution` | bool or None | True/False outcome; None = unresolved |
| `resolution_date` | str or None | When the outcome became known |
| `metadata` | dict | Free-form context |

## MarketHistory

Market data context for a question — price series, volatility, volume around the event date. Part of Agent 2's contract. Not consumed by the v1 base-rate predictor but planned for v2 feature vectors.

## Code paths

- v1 inline definitions: `examples/event_prediction_demo.py`
- Agent 1 contracts (when landed): `the_similarity/events/contracts.py`
- Agent 2 questions (when landed): `the_similarity/events/questions.py`
- Graph construction: `the_similarity/core/state_graph.py`

## Related

- [[event_scorecard]] — scoring metrics for predictions
- [[batch6 world event prediction v1 2026-04-18]] — decision record
