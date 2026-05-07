# Personalized Setup Scanner v1 — Schema Contract

> Wire-level contract that Worktrees B (delivery), C (frontend), and D (public surfaces) mock against until Worktree A's PR lands. Owned by Worktree A. Generated 2026-05-07.

## Persistence — SQLite tables

Migrations live under `the_similarity/platform/migrations/` and are applied automatically by `RunRegistry._apply_migrations()` on connect. Idempotent — safe to re-run.

### Table: `setups` (`migrations/0001_setups.sql`)

| Column               | Type    | Nullable | Notes                                                                 |
|----------------------|---------|----------|-----------------------------------------------------------------------|
| `id`                 | TEXT    | NO       | Primary key. Caller-supplied opaque ID.                               |
| `user_id`            | TEXT    | NO       | Multi-tenant FK. Indexed.                                             |
| `name`               | TEXT    | NO       | Human display name.                                                   |
| `instrument`         | TEXT    | NO       | Symbol the region was drawn on (`BTCUSDT`, `XAUUSD`). Indexed.        |
| `timeframe`          | TEXT    | NO       | Bar size (`1h`, `4h`, `1d`).                                          |
| `region_start_ts`    | TEXT    | NO       | ISO-8601 UTC.                                                         |
| `region_end_ts`      | TEXT    | NO       | ISO-8601 UTC.                                                         |
| `region_series_json` | TEXT    | NO       | JSON-encoded list of floats — the actual price series.                |
| `created_at`         | TEXT    | NO       | ISO-8601 UTC.                                                         |
| `updated_at`         | TEXT    | NO       | ISO-8601 UTC.                                                         |

Indexes: `idx_setups_user_id`, `idx_setups_instrument`.

### Table: `feedback` (`migrations/0002_feedback.sql`)

| Column       | Type | Nullable | Notes                                                              |
|--------------|------|----------|--------------------------------------------------------------------|
| `id`         | TEXT | NO       | Primary key. Caller-supplied.                                      |
| `user_id`    | TEXT | NO       | Multi-tenant FK.                                                   |
| `setup_id`   | TEXT | NO       | FK to `setups.id` (`ON DELETE CASCADE`).                           |
| `alert_id`   | TEXT | YES      | Set when `kind == "alert"`; `NULL` otherwise.                      |
| `analog_id`  | TEXT | YES      | Set when `kind == "analog"`; `NULL` otherwise.                     |
| `kind`       | TEXT | NO       | Discriminator: `"alert"` or `"analog"`. Indexed.                   |
| `thumb`      | TEXT | NO       | `"up"` or `"down"`.                                                |
| `free_text`  | TEXT | YES      | Optional note.                                                     |
| `created_at` | TEXT | NO       | ISO-8601 UTC.                                                      |

Indexes: `idx_feedback_user_setup` (composite), `idx_feedback_setup_id`, `idx_feedback_kind`.

### Table: `schema_migrations` (created by registry)

| Column       | Type | Nullable | Notes                                |
|--------------|------|----------|--------------------------------------|
| `version`    | TEXT | NO       | Four-digit prefix from filename.     |
| `applied_at` | TEXT | NO       | ISO-8601 UTC.                        |

## Python dataclasses (`the_similarity/platform/contracts.py`)

```python
@dataclass
class Setup:
    id: str
    user_id: str
    name: str
    instrument: str
    timeframe: str
    region_start_ts: str
    region_end_ts: str
    region_series: list[float] = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict: ...
    @classmethod
    def from_dict(cls, d: dict) -> "Setup": ...
```

```python
@dataclass
class Feedback:
    id: str
    user_id: str
    setup_id: str
    kind: str           # "alert" | "analog"
    thumb: str          # "up" | "down"
    alert_id: str | None = None
    analog_id: str | None = None
    free_text: str | None = None
    created_at: str = ""

    def to_dict(self) -> dict: ...
    @classmethod
    def from_dict(cls, d: dict) -> "Feedback": ...
```

```python
@dataclass
class InstrumentScanResult:
    instrument: str
    analogs: list[dict] = field(default_factory=list)   # see "Analog JSON shape" below
    forecast: dict | None = None                        # see "Forecast JSON shape" below
    error: str | None = None                            # truthy on per-instrument failure
```

```python
@dataclass
class ScanResult:
    setup_id: str
    user_id: str
    created_at: str
    per_instrument: list[InstrumentScanResult] = field(default_factory=list)
    top_n: list[dict] = field(default_factory=list)     # flat ranked across universe
    universe: list[str] = field(default_factory=list)   # symbols actually scanned, in order
    run_id: str | None = None                           # set when registry.register_run was called
```

## RunKind extension

`the_similarity/platform/artifacts.py`:

```python
class RunKind(str, Enum):
    # ... existing members ...
    SETUP_SCAN = "setup_scan"
```

Schemas synced: `the_similarity/platform/artifacts_schema.json`, `the_similarity/platform/platform_schema.json`. Default pillar mapping for `SETUP_SCAN` is `"finance"`.

## Registry method signatures (`the_similarity/platform/registry.py`)

```python
class RunRegistry:
    # Setups
    def create_setup(self, setup: Setup) -> str: ...
    def get_setup(self, setup_id: str) -> Setup | None: ...
    def list_setups(self, user_id: str, limit: int = 100, offset: int = 0) -> list[Setup]: ...
    def delete_setup(self, setup_id: str) -> bool: ...

    # Feedback
    def record_feedback(self, feedback: Feedback) -> str: ...
    def list_feedback(
        self,
        user_id: str,
        setup_id: str | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> list[Feedback]: ...
```

Validation:

- `create_setup` — empty `user_id` raises `ValueError`. Auto-stamps `created_at` and `updated_at` if blank.
- `list_setups` / `list_feedback` — empty `user_id` raises `ValueError` (multi-tenant guardrail).
- `record_feedback` — `kind ∈ {"alert", "analog"}` and `thumb ∈ {"up", "down"}`; otherwise `ValueError`. Auto-stamps `created_at` if blank. Cascades on `setups.id` via FK.

## Engine helpers

```python
# the_similarity/core/scorer.py — additive, does not change compute_confidence
def compute_goodrun_score(
    registry: RunRegistry,
    user_id: str,
    setup_id: str | None = None,
) -> dict:
    # returns:
    # {
    #   "user_id": str, "setup_id": str | None,
    #   "thumbs_up": int, "thumbs_down": int, "total": int,
    #   "net_score": float in [-1.0, 1.0],
    #   "alert_thumbs_up": int, "alert_thumbs_down": int,
    #   "analog_thumbs_up": int, "analog_thumbs_down": int,
    # }
```

```python
# the_similarity/core/scanner.py
DataLoader = Callable[[str, str, int], np.ndarray]  # (instrument, timeframe, n_bars) -> closes

def scan(
    setup: Setup,
    *,
    universe: Sequence[str] | None = None,           # default UNIVERSE_DEFAULT (37 symbols)
    config: Config | None = None,
    data_loader: DataLoader | None = None,           # default default_data_loader
    history_bars: int = 720,
    top_k: int = 5,
    top_n: int = 20,
    forward_bars: int = 50,
    max_workers: int = 6,
    registry: RunRegistry | None = None,             # optional — when set, persists RunKind.SETUP_SCAN
) -> ScanResult: ...
```

Universe constants (also exported):

- `UNIVERSE_CRYPTO`: 30-tuple of USDT-quoted Binance pairs.
- `UNIVERSE_FX_GOLD`: `("EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "USDCAD", "XAUUSD")`.
- `UNIVERSE_DEFAULT`: concatenation (37 symbols).

## Analog JSON shape

Each analog dict in `InstrumentScanResult.analogs` (and in the flat `ScanResult.top_n`):

```jsonc
{
  "start_idx": 1234,                 // int — index into the per-instrument history array
  "end_idx": 1284,                   // int (exclusive)
  "start_date": "2024-03-15T00:00:00Z",  // string | null
  "end_date":   "2024-03-19T00:00:00Z",  // string | null
  "confidence_score": 78.4,          // float in [0, 100]
  "score_breakdown": {
    "bempedelis_r2": 0.61,
    "bempedelis_smoothness": 0.72,
    "koopman": 0.84,
    "wavelet_spectrum": 0.55,
    "emd": 0.49,
    "tda": 0.31,
    "dtw": 0.78,
    "pearson_warped": 0.66,
    "transfer_entropy": 0.42
  },
  "regime": "trending_up",           // string | null
  "forward_window": [0.0, 0.012, ...],  // list[float] — cumulative returns; null if missing
  "matched_series": [42.1, 42.7, ...], // list[float] — raw matched values; null if missing
  "instrument": "BTCUSDT"            // present ONLY in ScanResult.top_n entries
}
```

Heavy diagnostic fields (`koopman_eigenvalues`, `persistence_diagram`, `transform_alpha`, `transform_beta`, `fractal_spectrum`) are intentionally dropped — the API surface doesn't need them at v1.

## Forecast JSON shape

```jsonc
{
  "bars": 50,                                 // int — forward horizon
  "percentiles": [10, 25, 50, 75, 90],        // list[int]
  "curves": {
    "10": [0.0, -0.001, -0.002, ...],         // list[float] of length `bars`
    "25": [...],
    "50": [...],                              // median projection (cumulative returns)
    "75": [...],
    "90": [...]
  }
}
```

Keys are stringified percentiles because JSON object keys must be strings. `null` for the entire `forecast` field when no analogs were found on that instrument.

## RunRecord shape for `RunKind.SETUP_SCAN`

```jsonc
{
  "run_id": "<32-char hex>",
  "kind": "setup_scan",
  "config": {
    "user_id": "<user_id>",
    "setup_id": "<setup_id>",
    "instrument": "BTCUSDT",
    "timeframe": "1h",
    "history_bars": 720,
    "top_k": 5,
    "top_n": 20,
    "forward_bars": 50,
    "universe": ["BTCUSDT", "ETHUSDT", "..."]
  },
  "seed": null,
  "summary": { /* the full ScanResult.to_dict() */ },
  "created_at": "...",
  "status": "succeeded",
  "pillar": "finance",
  "artifact_paths": {},
  "provenance": {
    "generator_name": "the_similarity.core.scanner",
    "generator_version": "0.1.0",
    "created_at": "...",
    "params": {
      "max_workers": 6,
      "elapsed_seconds": 3.214
    }
  }
}
```

## Partial-success contract (for B/C/D)

Per-instrument failures (network timeout, missing data, engine raise) record an `error` string on that `InstrumentScanResult` and **do not** abort the scan. The frontend should render `error` as a soft warning ("couldn't fetch BTCUSDT — try again") rather than a fatal toast. The top-N flat list silently skips error rows because they have empty `analogs`.

FX/gold symbols on the v1 default loader will return `error: "FX/gold loader not wired in v1 default loader (..."` until either `yfinance` is added to `pyproject.toml` or a custom `data_loader` is injected. The schema is unaffected — frontend should treat the error as a soft "coming soon" message.
