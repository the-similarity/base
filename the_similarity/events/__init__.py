"""Events package — event graph, feature extraction, analogue retrieval, evaluation, and prediction markets.

This package provides:
- ``features``: Convert raw event dicts to fixed-length feature vectors.
- ``event_graph``: In-memory graph of EventNodes with cosine-similarity search.
- ``retrieval``: Sliding-window analogue retrieval over historical event streams.
- ``scorecard``: Probabilistic forecast evaluation (Brier, calibration, resolution, log score).
- ``eval_adapter``: Platform registry integration for event evaluation results.
- ``markets`` — Core dataclasses: ForecastQuestion, MarketPrice,
  MarketHistory, QuestionSet.
- ``market_loader`` — JSON persistence: load_questions / save_questions.
- ``market_adapter`` — Platform registry integration: register a
  QuestionSet as a RunRecord with kind=EVENTS.
"""
