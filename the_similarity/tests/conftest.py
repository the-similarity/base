"""Pytest fixtures and global setup for the_similarity test suite.

Lifecycle: imported by pytest before any test module is collected. The
multiprocessing start method must be set BEFORE any ProcessPoolExecutor
is constructed — pytest collection imports test modules which import
the_similarity.core.backtester, but workers aren't spawned until a test
actually runs the backtester, so setting it here is safe.

Why 'spawn' instead of 'fork':

    Linux defaults to fork() for multiprocessing. fork()'d children
    inherit the parent's memory pages, including locks held by native
    libraries (numpy MKL global lock, pyarrow GIL helpers, SQLite
    file locks). If a forked child tries to acquire one of those
    locks while the parent holds it, the child deadlocks
    indefinitely — pytest hangs and CI times out.

    'spawn' starts each worker as a fresh Python interpreter with no
    inherited state. macOS already defaults to spawn since Python 3.8
    for exactly this reason (the macOS Objective-C runtime has the
    same fork-unsafety problem). We mirror that on Linux for parity.

    Cost: spawn is slightly slower to start a worker (~100ms vs ~10ms
    for fork) because it has to re-import all modules. Acceptable for
    test runs; backtester workers run for seconds.

This is a test-only configuration. Production code that needs fork
behavior (none does today) can override per-call.
"""

from __future__ import annotations

import multiprocessing


def _force_spawn_start_method() -> None:
    """Set multiprocessing start method to 'spawn'.

    Idempotent: if already set (or set by another conftest), do nothing.
    """
    try:
        multiprocessing.set_start_method("spawn", force=True)
    except RuntimeError:
        # Already set by an earlier import; nothing to do.
        pass


_force_spawn_start_method()
