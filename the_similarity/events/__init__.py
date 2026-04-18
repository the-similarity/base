"""Events package — event graph, feature extraction, analogue retrieval, and evaluation.

This package provides:
- ``features``: Convert raw event dicts to fixed-length feature vectors.
- ``event_graph``: In-memory graph of EventNodes with cosine-similarity search.
- ``retrieval``: Sliding-window analogue retrieval over historical event streams.
- ``scorecard``: Probabilistic forecast evaluation (Brier, calibration, resolution, log score).
- ``eval_adapter``: Platform registry integration for event evaluation results.
"""
