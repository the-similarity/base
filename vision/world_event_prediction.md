# World Event Prediction — Pillar Vision

## What this pillar does

World Event Prediction is one of The Similarity's five pillars. It brings **multimodal forecasting** to world events by combining event history, market signals, and text context into a structured prediction pipeline.

The core thesis: **historical analogues are informative priors for future events**. If a geopolitical escalation today resembles past escalations in its economic context, severity, and timing, the resolution patterns of past forecast questions provide a meaningful (if noisy) signal.

## The v1 workflow

```
Ingest events          Ingest questions          Build event graph
    |                       |                         |
    v                       v                         v
Event(id, name,       ForecastQuestion(id,       KNN graph over
 category, date,       event_id, text,           event feature
 severity, desc)       resolution)               vectors
    |                       |                         |
    +----------- + ---------+                         |
                 |                                    |
                 v                                    v
         For each resolved question:           Retrieve analogues
         find analogous historical             (nearest-neighbor
         events via graph topology             events in feature
                 |                              space)
                 v
         Predict P(resolution=True)
         from analogue base rates
                 |
                 v
         Score with EventScorecard
         (Brier, log score,
          calibration error, grade)
                 |
                 v
         Register eval run in
         platform registry
```

### Contracts

| Contract | Module | Purpose |
|----------|--------|---------|
| `Event` | Agent 1's events module | A world event with date, category, severity, feature vector |
| `EventSeries` | Agent 1's events module | Ordered sequence of related events |
| `ForecastQuestion` | Agent 2's questions module | A yes/no question with known resolution |
| `MarketHistory` | Agent 2's questions module | Market data context for a question |
| `EventScorecard` | Agent 4's scorecard module | Brier score, calibration, log score, grade |

### Graph

The event graph (built on `the_similarity/core/state_graph.py`) connects events by feature similarity. Each event is embedded as a `StateVector` with features derived from date, severity, category, and description. KNN retrieval finds the most similar historical events to use as analogues for prediction.

### Scoring

The `EventScorecard` evaluates binary predictions on four axes:

- **Brier score**: Mean squared error of predicted probabilities vs outcomes. Range [0, 1], lower is better. 0.0 = perfect, 0.25 = coin-flip baseline.
- **Log score**: Mean negative log-likelihood. More aggressively penalizes confident wrong predictions than Brier.
- **Calibration error**: |mean(predicted) - mean(observed)|. Measures systematic over/under-confidence.
- **Grade**: Letter grade from Brier score. A (<0.10), B (<0.20), C (<0.30), D (<0.40), F (>=0.40).

## What's honest about v1

**v1 uses naive base-rate estimation, not a real forecaster.** The prediction for each question is simply the fraction of resolved questions associated with analogue events that resolved True. This is a weak signal — it captures category-level base rates but misses the specific content, timing, and context that distinguish one question from another.

**The value is the eval scaffold, not the predictions.** v1 establishes:

1. **Data contracts** — structured schemas for events, questions, and scorecards that all downstream components can depend on.
2. **Graph infrastructure** — reusable KNN retrieval over event embeddings, sharing the same `state_graph.py` used by other pillars.
3. **Scoring pipeline** — Brier/calibration/log-score computation that will evaluate all future forecasting models on the same terms.
4. **Registry integration** — eval runs are persisted in the platform registry, enabling comparison across model versions.

## What's next

### Near-term (v2)

- **LLM-based prediction**: Use Claude to read event descriptions and question text, then output calibrated probability estimates. The base-rate prior from v1 becomes one input to the LLM prompt.
- **Richer feature vectors**: Replace the 4-D heuristic embedding with text embeddings (e.g., from a sentence transformer) for higher-fidelity analogue retrieval.
- **Market signal integration**: Incorporate `MarketHistory` data (price changes, volatility, volume) into the feature vector so the graph captures market context, not just event metadata.

### Medium-term (v3)

- **Ensemble prediction**: Combine LLM predictions with base-rate priors, market-derived signals, and domain-specific models using the existing `ensemble.py` infrastructure.
- **Continuous calibration tracking**: Track calibration over time as new questions resolve. Surface calibration drift as an alert via `alerts.py`.
- **Live market ingestion**: Connect to real-time market data feeds to automatically create `MarketHistory` records for new events.

### Long-term

- **Cross-pillar fusion**: Use the state graph's cross-domain bridge queries to find connections between world events and synthetic data scenarios. A market crash in a synthetic world that resembles a historical crash provides additional analogue signal.
- **Conditional forecasting**: "If event X happens, what is the probability of Y?" — requires causal graph extensions beyond KNN.
- **Forecast tournament**: Run multiple models (LLM, ensemble, base-rate) on the same question set and track which outperforms over time, automatically promoting the best model.
