"""Test package for the customer-facing FastAPI app (the-similarity-api).

The package marker exists so ``python -m pytest tests/`` discovers tests
through the canonical import path (``tests.test_platform_routes``) rather
than the bare-filename path — this matters when fixtures in ``conftest.py``
need to import helpers from sibling test modules.
"""
