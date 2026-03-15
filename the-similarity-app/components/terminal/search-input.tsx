"use client";
import { useState, useRef, useCallback, useEffect } from "react";
import { useTerminal } from "../../lib/terminal-context";
import { fetchCatalog, fetchSeries, searchApi } from "../../lib/api";
import type { CatalogItem } from "../../lib/types";

function formatSymbol(item: CatalogItem): string {
  return `${item.symbol.toUpperCase()} · ${item.timeframe}`;
}

function formatAssetClass(ac: string): string {
  return ac.charAt(0).toUpperCase() + ac.slice(1);
}

export function SearchInput() {
  const { state, dispatch } = useTerminal();
  const [expanded, setExpanded] = useState(false);
  const [catalog, setCatalog] = useState<CatalogItem[]>([]);
  const [selectedDataset, setSelectedDataset] = useState<string>("");
  const [querySize, setQuerySize] = useState(60);
  const [loadingData, setLoadingData] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  // Load catalog on first expand
  useEffect(() => {
    if (!expanded || catalog.length > 0) return;
    fetchCatalog()
      .then(setCatalog)
      .catch(() => dispatch({ type: "SET_ERROR", error: "Could not load dataset catalog." }));
  }, [expanded, catalog.length, dispatch]);

  useEffect(() => {
    return () => { abortRef.current?.abort(); };
  }, []);

  // Group catalog by asset class
  const groups = catalog.reduce<Record<string, CatalogItem[]>>((acc, item) => {
    const key = item.assetClass;
    if (!acc[key]) acc[key] = [];
    acc[key].push(item);
    return acc;
  }, {});

  const handleSearch = useCallback(async () => {
    if (!selectedDataset) {
      dispatch({ type: "SET_ERROR", error: "Select a dataset first." });
      return;
    }

    const [assetClass, symbol, timeframe] = selectedDataset.split("/");

    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    dispatch({ type: "SET_LOADING", loading: true });
    dispatch({ type: "SET_ERROR", error: null });

    try {
      // Fetch the full series
      const series = await fetchSeries(assetClass, symbol, timeframe);

      if (series.values.length < querySize + 10) {
        dispatch({ type: "SET_ERROR", error: `Not enough data. Dataset has ${series.values.length} points, need at least ${querySize + 10}.` });
        return;
      }

      // Query = last N bars, History = everything before that
      const queryValues = series.values.slice(-querySize);
      const historyValues = series.values.slice(0, -querySize);

      const response = await searchApi(
        {
          queryValues,
          historyValues,
          activeMethods: state.activeMethods,
          topK: 20,
          forwardBars: 50,
        },
        controller.signal,
      );
      dispatch({ type: "SET_SEARCH_RESPONSE", response });
      setExpanded(false);
    } catch (err: unknown) {
      if (err instanceof Error && err.name === "AbortError") return;
      dispatch({ type: "SET_ERROR", error: err instanceof Error ? err.message : "Search failed." });
    }
  }, [selectedDataset, querySize, state.activeMethods, dispatch]);

  const handleCancel = useCallback(() => {
    abortRef.current?.abort();
    dispatch({ type: "SET_LOADING", loading: false });
  }, [dispatch]);

  if (!expanded) {
    return (
      <div className="search-bar-collapsed">
        <button
          type="button"
          className="search-bar-toggle"
          onClick={() => setExpanded(true)}
        >
          <span className="search-bar-icon">/</span>
          <span>Search patterns…</span>
        </button>
        {state.searchResponse && (
          <span className="search-bar-status">
            {state.searchResponse.matches.length} matches found
          </span>
        )}
      </div>
    );
  }

  return (
    <div className="search-bar">
      <div className="search-bar-fields">
        {/* Dataset picker */}
        <div className="search-bar-field">
          <label className="search-bar-label">
            Dataset
          </label>
          <select
            className="search-bar-select"
            value={selectedDataset}
            onChange={(e) => setSelectedDataset(e.target.value)}
          >
            <option value="">Choose a dataset…</option>
            {Object.entries(groups).map(([ac, items]) => (
              <optgroup key={ac} label={formatAssetClass(ac)}>
                {items.map((item) => {
                  const id = `${item.assetClass}/${item.symbol}/${item.timeframe}`;
                  return (
                    <option key={id} value={id}>
                      {formatSymbol(item)} — {item.rowCount.toLocaleString()} bars
                    </option>
                  );
                })}
              </optgroup>
            ))}
          </select>
        </div>

        {/* Query window size */}
        <div className="search-bar-field">
          <label className="search-bar-label">
            Query window
            <span className="search-bar-count">{querySize} bars</span>
          </label>
          <input
            type="range"
            className="search-bar-range"
            min={20}
            max={200}
            step={5}
            value={querySize}
            onChange={(e) => setQuerySize(Number(e.target.value))}
          />
          <div className="search-bar-range-labels">
            <span>20</span>
            <span>200</span>
          </div>
        </div>
      </div>

      <div className="search-bar-actions">
        {!state.loading ? (
          <button
            type="button"
            className="search-bar-btn search-bar-btn--run"
            onClick={handleSearch}
            disabled={!selectedDataset}
          >
            Run
          </button>
        ) : (
          <button
            type="button"
            className="search-bar-btn search-bar-btn--cancel"
            onClick={handleCancel}
          >
            Cancel
          </button>
        )}
        <button
          type="button"
          className="search-bar-btn search-bar-btn--close"
          onClick={() => setExpanded(false)}
        >
          Collapse
        </button>
      </div>
    </div>
  );
}
