"""World events pillar — prediction market ingestion and forecast questions.

This package provides the data model and I/O for prediction market data:
binary forecast questions, price histories (probability over time), and
benchmark question sets for evaluation.

Modules
-------
- ``markets`` — Core dataclasses: ForecastQuestion, MarketPrice,
  MarketHistory, QuestionSet.
- ``market_loader`` — JSON persistence: load_questions / save_questions.
- ``market_adapter`` — Platform registry integration: register a
  QuestionSet as a RunRecord with kind=EVENTS.
"""
