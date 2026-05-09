"""Real-world dataset loaders for self-similarity experiments.

This package houses adapters that turn external public datasets into
the in-memory objects (typically numpy arrays of trajectories or
windowed series) the engine consumes. Each submodule corresponds to
one external source:

- :mod:`storm_tracks` — NOAA HURDAT2 hurricane tracks.

The pattern: a submodule exposes a small set of public functions
(``load_*``) and dataclasses (``Storm``, etc.), keeps all I/O
side effects out of import, and is safe to import from inside test
modules and adapters alike.
"""

from __future__ import annotations
