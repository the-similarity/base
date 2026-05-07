# Setup scanner

The personalized cross-instrument scanner — Worktree A's contribution to [[personalized_setup_scanner]] v1.

## What it does

Given a user-defined :class:`Setup` (chart region: instrument + timeframe + price series), sweep the engine's existing matcher + projector across a fixed 37-symbol universe (top crypto + FX majors + gold) and return:

- per-instrument top-K analogs with score breakdowns,
- per-instrument forward-cone forecast,
- a flat top-N ranked across the entire universe.

Code: [`the_similarity/core/scanner.py`](the_similarity/core/scanner.py).

## Why this lives in the engine, not the API

The scanner is pure orchestration over [[matcher]] + [[projector]] + [[run_registry]]. Putting it in `the_similarity/core/` means:

- Tests run without spinning up FastAPI.
- The CLI and any future batch jobs can import `scan(...)` directly.
- The API layer becomes a thin HTTP surface that calls `scan()` and serializes the result.

## Key parameters (defaults)

| Parameter      | Default | Notes |
|----------------|---------|-------|
| `universe`     | `UNIVERSE_DEFAULT` (37 syms) | 30 USDT-quoted Binance crypto + 6 FX majors + XAUUSD |
| `history_bars` | 720     | ~30 days of 1h bars or 24 hours of 1m bars |
| `top_k`        | 5       | Per-instrument analogs (matches v1 cold-backtest UI) |
| `top_n`        | 20      | Flat cross-instrument leaderboard size |
| `forward_bars` | 50      | Cone horizon |
| `max_workers`  | 6       | Thread-pool size; tuned to Binance ~1200 req/min limit |

## Tradeoffs

- **Threads, not processes.** The matcher releases the GIL on numpy / scipy / dtaidistance kernels, so a `ThreadPoolExecutor` parallelizes well without the pickling overhead of `ProcessPoolExecutor`. Smaller windows = pickling cost dominates.
- **Hardcoded crypto universe.** We do not query Binance's `/api/v3/exchangeInfo` at scan time — saves an HTTP hop per scan and the top-30 set is stable for months. Refresh is a manual TODO.
- **FX/gold stub.** v1 default loader raises `NotImplementedError` for FX symbols because `yfinance` is not in `pyproject.toml`. The partial-success contract turns this into a per-instrument `error` string rather than a fatal scan failure.
- **Partial-but-shipped beats blocked.** Per-instrument failures (network, missing data, engine raise) are caught in `_scan_one_instrument` and recorded as `error` on `InstrumentScanResult`. The rest of the universe still gets scanned. The frontend should render `error` as a soft warning.

## Persistence

When a `RunRegistry` is supplied, the full `ScanResult` is JSON-serialized into `RunRecord.summary` under `RunKind.SETUP_SCAN`. `user_id` and `setup_id` go into `RunRecord.config` so multi-tenant scoping works via SQL filters on the JSON-encoded TEXT (small corpus; index later if needed).

The setups + feedback tables themselves live alongside the registry tables and are created by plain-SQL migrations under `the_similarity/platform/migrations/`. Migration runner is `RunRegistry._apply_migrations()` — idempotent, version-tracked in a `schema_migrations` table, applied inside a SAVEPOINT for atomicity.

## Goodrun feedback hook

Per the v1 plan, every alert and analog the user sees can be marked thumbs-up/down with optional free-text. v1 persists these from day 1 even though the v1 confidence score does not yet aggregate them — that's the moat for v2 ([[personalized_setup_scanner]]).

The aggregation helper `compute_goodrun_score(registry, user_id, setup_id=None)` lives in [`the_similarity/core/scorer.py`](the_similarity/core/scorer.py) (additive; does not change `compute_confidence`). Returns thumbs counts + a `[-1, 1]` net_score plus per-kind breakdown. This is the surface v2's training pipeline imports.

## Schema contract for parallel worktrees

Worktrees B (delivery), C (frontend), and D (public surfaces) mock against [`vision/setup_scanner_schema_contract.md`](vision/setup_scanner_schema_contract.md) until A's PR lands. The contract is the single source of truth for table columns, dataclass shapes, registry method signatures, and JSON wire formats.

## Related

- [[matcher]] — Tier 0/1/2 search pipeline the scanner calls.
- [[projector]] — forecast cone logic the scanner calls.
- [[run_registry]] — persistence layer the scanner extends.
- [[personalized_setup_scanner]] — the product spec / v1 plan.
- [[goodrun]] — the legacy goodrun infrastructure (`the-similarity-api/app/goodruns.py`).
