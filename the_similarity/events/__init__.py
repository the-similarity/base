"""
Events package — event graph, feature extraction, and analogue retrieval.

This package provides:
- ``features``: Convert raw event dicts to fixed-length feature vectors.
- ``event_graph``: In-memory graph of EventNodes with cosine-similarity search.
- ``retrieval``: Sliding-window analogue retrieval over historical event streams.
"""
