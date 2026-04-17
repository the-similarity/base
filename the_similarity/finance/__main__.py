"""Entry point for ``python -m the_similarity.finance``.

Routes directly to the benchmark CLI so the user can run either::

    python -m the_similarity.finance run --symbol SPY
    python -m the_similarity.finance.benchmark run --symbol SPY

Both forms behave identically.
"""

from the_similarity.finance.benchmark import main

if __name__ == "__main__":
    raise SystemExit(main())
