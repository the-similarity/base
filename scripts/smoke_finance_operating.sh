#!/usr/bin/env bash
# Smoke test for the finance operating product.
#
# Exercises the end-to-end finance workflow on a clean DB:
#
#   1. Create an isolated SQLite registry at /tmp/finance-smoke.db.
#   2. Run a tiny backtest (5 trials) with registration.
#   3. Verify the run landed via `python -m the_similarity.platform list`.
#   4. Clean up.
#
# Exit codes:
#   0 — every step succeeded.
#   1 — any step failed (set -e catches it).
#
# The script is idempotent: running it repeatedly starts from a fresh
# DB. It never touches the operator's real registry.
set -euo pipefail

# -- config ----------------------------------------------------------------

export THE_SIMILARITY_REGISTRY_DB="${THE_SIMILARITY_REGISTRY_DB:-/tmp/finance-smoke.db}"
rm -f "$THE_SIMILARITY_REGISTRY_DB" \
      "$THE_SIMILARITY_REGISTRY_DB-journal" \
      "$THE_SIMILARITY_REGISTRY_DB-wal" \
      "$THE_SIMILARITY_REGISTRY_DB-shm"

echo "[smoke] registry: $THE_SIMILARITY_REGISTRY_DB"

# -- step 1: run a tiny backtest with registration -------------------------
# Uses synthetic GBM prices (no data file dependency) so this script works
# on any machine without needing SPY CSV data.

echo "[smoke] running backtest with registration..."
python -c "
import numpy as np
from the_similarity.api import backtest

# Generate synthetic prices — deterministic via seed.
rng = np.random.RandomState(42)
prices = 100.0 * np.exp(np.cumsum(rng.normal(0.0002, 0.012, 500)))

r = backtest(
    prices,
    window_size=60,
    forward_bars=20,
    n_trials=5,
    seed=42,
    register=True,
    source_id='synthetic-smoke',
)
print(f'hit_rate={r.hit_rate:.2f} crps={r.crps:.4f}')
run_id = getattr(r, 'run_id', None)
if run_id is None:
    raise RuntimeError('backtest(register=True) did not stamp run_id')
print(f'run_id={run_id}')
"
echo "[smoke] backtest: OK"

# -- step 2: verify run landed in registry ---------------------------------

echo "[smoke] listing finance runs..."
python -m the_similarity.platform list --kind finance
echo "[smoke] list: OK"

# -- cleanup ---------------------------------------------------------------

rm -f "$THE_SIMILARITY_REGISTRY_DB" \
      "$THE_SIMILARITY_REGISTRY_DB-journal" \
      "$THE_SIMILARITY_REGISTRY_DB-wal" \
      "$THE_SIMILARITY_REGISTRY_DB-shm"

echo ""
echo "Finance smoke: OK"
