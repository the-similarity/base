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

## Adapter responsibilities (the contract)

Every adapter MUST:

1. **Run the pillar-native pipeline.** Produce whatever on-disk artifacts the pillar emits (parquet, JSONL, scorecard.json, etc.).
2. **Anchor `run_dir`.** Compute a canonical output directory (e.g. `<kind>-<seed>-<YYYYMMDD-HHMMSS>`) and record it in `provenance["run_dir"]` so the HTTP artifact streamer can resolve relative paths.
3. **Extract headline numbers** into `RunRecord.summary` — see [[scorecard_summary]] for canonical keys.
4. **Build provenance** with `generator_name`, `generator_version`, `seed`, `created_at`, plus pillar-specific knobs (scenario name for worlds, source_id for copies, symbol/date-range for finance).
5. **Call `write_artifact(run_dir, artifact)`** to materialize `artifact.json`.
6. **Call `registry.register(artifact)`** to index the record.

Step 6 is the invariant — an adapter that produces artifacts but does not register is invisible to the rest of the platform.

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

## Invariants

- **No adapter mutates another pillar's artifacts.** One adapter, one run_dir, one `artifact.json`.
- **Adapters never update the summary after registration.** To enrich, produce a new `RunRecord` with a new `run_id` (or, for same-id re-registration via eval, document the re-registration in provenance).
- **Run dirs are immutable from the registry's perspective.** Moving a run dir invalidates the `provenance["run_dir"]` anchor and the artifact-streaming endpoint will 404.

## Tests

`the_similarity/tests/test_platform_adapters.py` covers:

1. Finance: dict + object + minimal report shapes, calibration keys stringified for JSON safety.
2. Copies: full + parquet-less run dirs, missing-dir raises.
3. Worlds: stdlib ThreadingHTTPServer captures the POST body; a second test proves ECONNREFUSED resolves to `null` so `--register` never breaks the runner.

## Related notes

- [[platform_rest_api]] — FastAPI surface (routes.py).
- [[run_record]] — the output shape every adapter produces
- [[platform_registry]] — where adapters register
- [[finance_pilot]] — what finance backtests are trying to prove.
- [[block_bootstrap_generator]] — primary copies generator today.
- [[synthetic_contracts]] — the copies-side `Provenance` / `Scorecard` dataclasses adapters embed
- `the_similarity/platform/api/routes.py`
- `the_similarity/synthetic/cli.py`
- `the-similarity-fractal/src/sim/headless/runner.js`
