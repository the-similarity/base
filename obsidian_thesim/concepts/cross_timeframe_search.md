# Cross-Timeframe Search

Lets a user query at one resolution (e.g. 60 bars at 1h) and find analogues
across multiple resampled resolutions of the same underlying history (e.g.
5min, 15min, 1h, 4h, 1D). The query window is rescaled per-timeframe via
linear interpolation so it covers the same temporal duration at every
resolution; matches across all resolutions are merged and deduplicated.

## End-to-end path

| Layer | File | What it does |
|-------|------|--------------|
| Engine | `the_similarity/api.py::cross_timeframe_search` | Resamples history per timeframe, scales query, runs `search()` per resample, projects forward windows, merges + dedupes |
| Engine | `the_similarity/api.py::_resample_timeseries` | `df.resample(target_timeframe).last()` on `TimeSeries` with dates |
| Engine | `the_similarity/core/projector.py::project` | Reuses pre-populated `match.forward_window` when present (cross-timeframe path) instead of slicing original history with resampled-frame indices |
| Contract | `the_similarity/contracts/api.py::SearchRequest` | `timeframes: list[str]` + `history_dates: list[str]` |
| API | `the-similarity-api/app/services.py::execute_search` | Branches on `request.timeframes` — empty → `search()`, non-empty → `cross_timeframe_search()` |
| Frontend | `the-similarity-app/lib/types.ts::SearchRequest` | Mirrors the contract (`timeframes?`, `historyDates?`) |
| Frontend | `the-similarity-app/components/workstation/workstation.tsx` | Chip selector for `5min / 15min / 1h / 4h / 1D`, only rendered when `loadedDates.length === loadedValues.length` |

## Invariants

- **`forward_window` is the bridge.** Cross-timeframe matches carry indices in the *resampled* history's coordinate system, so any downstream code that slices the original history with `match.end_idx` is wrong. `cross_timeframe_search` projects per-resample so each match arrives with `forward_window` already filled in cumulative-return space, and `project()` reuses it.
- **`history_dates` is required when `timeframes` is non-empty.** Pandas resample needs a `DatetimeIndex`. The service returns `400` rather than letting the engine raise `ValueError`.
- **Empty `timeframes` is a strict no-op.** The branch only fires when the array is non-empty, so the legacy single-timeframe path (and all of its tests) is untouched.

## UI contract notes

- The chip selector is local component state (no localStorage) — every session starts back at single-timeframe.
- A toggle is part of the dirty check, so changing the selection pulses the Search button just like a window drag.
- Selection is snapshotted at search-start, so a chip toggle mid-flight cannot change which engine path produced the visible result.

## Related

- [[concepts/Engine map]]
- [[concepts/analog_palette]]
