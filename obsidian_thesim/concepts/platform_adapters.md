# Platform Adapters

Thin wrappers that lift existing pillar outputs into the shared
[[platform_rest_api|Platform]] run registry without forcing each pillar to
adopt the registry as a hard dependency.

## Three adapters

| Adapter | Path | Wraps | Kind |
|---|---|---|---|
| **Finance** | `the_similarity/platform/adapters/finance.py` | `the_similarity/api.py::backtest` (`BacktestReport`) | `RunKind.FINANCE` |
| **Copies** | `the_similarity/platform/adapters/copies.py` | `the_similarity/synthetic/cli.py` run dir (scorecard.json + provenance.json) | `RunKind.COPIES` |
| **Worlds** | `the-similarity-fractal/src/platform/registry-client.js` | Headless runner JSONL output | `RunKind.WORLDS` |

All three build a unified `RunArtifact` (see `the_similarity/platform/artifacts.py`) and land a row in the `RunRegistry` (SQLite at `~/.the_similarity/registry.db`, override with `$THE_SIMILARITY_REGISTRY_DB`).

## Opt-in wiring

Each host surface exposes the adapter behind a `--register` / `register=True` switch so default behavior is **byte-identical** to the pre-adapter version:

- `the_similarity.api.backtest(..., register=True, source_id="spy")` — stamps `run_id` on the returned report.
- `python -m the_similarity.synthetic.cli ... --register` — prints the run_id alongside the run dir.
- `node src/sim/headless/runner.js ... --register [--api-url ...]` — best-effort POST to the Platform API.

The worlds adapter is **best-effort**: a missing / unreachable API logs to stderr and the runner exits 0. Finance and copies adapters raise on DB errors because the caller explicitly asked for registration.

## New `RunKind.FINANCE`

Added to `RunKind` additively (enum values are stable public API). The JSON schema (`the_similarity/platform/artifacts_schema.json`) was updated to match so the TS side validates finance rows too.

## Pillar label in summary

The `RunArtifact` contract has no `pillar` field — we mirror the label into `summary["pillar"]` (`"finance"`, `"copies"`, `"worlds"`) so UI clients can filter without a schema change. `kind` carries the same information for Python consumers.

## Worlds HTTP contract

Client POSTs a full `RunArtifact`-shaped JSON to `POST /platform/runs`. The server side of this endpoint is owned by the Platform API agent; until it lands, the client gets a 404 and logs the skip (best-effort fallback keeps runners green).

Default API URL: `http://localhost:8787` (matches `DEFAULT_PORT` in `the_similarity/platform/api/main.py`).

## Tests

`the_similarity/tests/test_platform_adapters.py` covers:

1. Finance: dict + object + minimal report shapes, calibration keys stringified for JSON safety.
2. Copies: full + parquet-less run dirs, missing-dir raises.
3. Worlds: stdlib ThreadingHTTPServer captures the POST body; a second test proves ECONNREFUSED resolves to `null` so `--register` never breaks the runner.

## Related notes

- [[platform_rest_api]] — FastAPI surface (routes.py).
- [[finance_pilot]] — what finance backtests are trying to prove.
- [[block_bootstrap_generator]] — primary copies generator today.
