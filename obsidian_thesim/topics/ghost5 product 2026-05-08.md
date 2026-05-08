# Ghost5 product 2026-05-08

Ghost5 is a sellable $39/month product surface at `/ghost5`.

The user workflow is deliberately narrow:

1. Choose a historical window on the tape.
2. Press "Set as entry".
3. Receive the 20 closest non-overlapping historical windows where the same setup occurred.
4. Read what happened after those entries: forward move, drawdown, win rate, and median continuation.

Implementation entry points:

- `/ghost5` reuses the Lumen workstation wrapper and the real `<Workstation>` component, configured for 20 analogs.
- `/api/ghost5` reads `the-similarity-data/manifests/catalog.json` and the selected parquet file, then returns the deterministic JSON contract for the selected entry window.
- `the-similarity-app/lib/ghost5.ts` owns the matching contract shared by the page and API.

Ghost5 must not fork a second chart surface. The user-facing UI stays on the Lumen workstation component stack; Ghost5-specific behavior is configuration and service API, not a parallel chart implementation.

Ghost5 mode hides the regular workstation option chips (`Matches`, `Next`, and cross-timeframe `Other views`). The product promise is narrower: always show 20 histories, prefer candles when OHLC is available, and ask the user which history card represents their setup. That confirmation is the hook for future real-time setup notifications.

Related notes: [[Analog forecasting]], [[Similarity analysis]], [[terminal forward windows]]
