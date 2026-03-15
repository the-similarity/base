"use client";
import { useState, useRef, useCallback, useEffect } from "react";
import { useTerminal } from "../../lib/terminal-context";
import { fetchCatalog, fetchSeries, searchApi } from "../../lib/api";
import type { CatalogItem } from "../../lib/types";

function formatSymbol(item: CatalogItem): string {
  return item.symbol.replace(/_/g, "/").toUpperCase();
}

function formatTimeframe(tf: string): string {
  return tf.toUpperCase();
}

const ASSET_ICONS: Record<string, string> = {
  crypto: "C",
  stocks: "S",
  forex: "F",
  commodities: "G",
};

export function SearchSidebar() {
  const { state, dispatch } = useTerminal();
  const [catalog, setCatalog] = useState<CatalogItem[]>([]);
  const [selectedDataset, setSelectedDataset] = useState<string>("");
  const [querySize, setQuerySize] = useState(60);
  const [filterText, setFilterText] = useState("");
  const [expandedGroups, setExpandedGroups] = useState<Set<string>>(new Set(["crypto", "stocks"]));
  const abortRef = useRef<AbortController | null>(null);

  // Load catalog on mount
  useEffect(() => {
    fetchCatalog()
      .then(setCatalog)
      .catch(() => {});
  }, []);

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

  // Filter
  const filter = filterText.toLowerCase();
  const filteredGroups = Object.entries(groups).reduce<Record<string, CatalogItem[]>>(
    (acc, [key, items]) => {
      const filtered = filter
        ? items.filter((i) =>
            i.symbol.toLowerCase().includes(filter) ||
            i.assetClass.toLowerCase().includes(filter) ||
            i.timeframe.toLowerCase().includes(filter)
          )
        : items;
      if (filtered.length > 0) acc[key] = filtered;
      return acc;
    },
    {},
  );

  const toggleGroup = (group: string) => {
    setExpandedGroups((prev) => {
      const next = new Set(prev);
      if (next.has(group)) next.delete(group);
      else next.add(group);
      return next;
    });
  };

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
      const series = await fetchSeries(assetClass, symbol, timeframe);

      if (series.values.length < querySize + 10) {
        dispatch({ type: "SET_ERROR", error: `Not enough data (${series.values.length} points, need ${querySize + 10}).` });
        return;
      }

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
    } catch (err: unknown) {
      if (err instanceof Error && err.name === "AbortError") return;
      dispatch({ type: "SET_ERROR", error: err instanceof Error ? err.message : "Search failed." });
    }
  }, [selectedDataset, querySize, state.activeMethods, dispatch]);

  const handleCancel = useCallback(() => {
    abortRef.current?.abort();
    dispatch({ type: "SET_LOADING", loading: false });
  }, [dispatch]);

  return (
    <div className="search-sidebar">
      {/* Search filter */}
      <div className="search-sidebar__filter">
        <input
          type="text"
          className="search-sidebar__filter-input"
          placeholder="Filter datasets…"
          value={filterText}
          onChange={(e) => setFilterText(e.target.value)}
        />
      </div>

      {/* Dataset list */}
      <div className="search-sidebar__list">
        {Object.entries(filteredGroups).map(([ac, items]) => (
          <div key={ac} className="search-sidebar__group">
            <button
              type="button"
              className="search-sidebar__group-header"
              onClick={() => toggleGroup(ac)}
            >
              <span className="search-sidebar__group-icon">{ASSET_ICONS[ac] ?? "?"}</span>
              <span className="search-sidebar__group-name">
                {ac.charAt(0).toUpperCase() + ac.slice(1)}
              </span>
              <span className="search-sidebar__group-count">{items.length}</span>
              <span className={`search-sidebar__chevron ${expandedGroups.has(ac) ? "open" : ""}`}>
                ›
              </span>
            </button>
            {expandedGroups.has(ac) && (
              <div className="search-sidebar__group-items">
                {items.map((item) => {
                  const id = `${item.assetClass}/${item.symbol}/${item.timeframe}`;
                  const isActive = selectedDataset === id;
                  return (
                    <button
                      key={id}
                      type="button"
                      className="search-sidebar__item"
                      data-active={isActive}
                      onClick={() => setSelectedDataset(id)}
                    >
                      <span className="search-sidebar__item-symbol">
                        {formatSymbol(item)}
                      </span>
                      <span className="search-sidebar__item-tf">
                        {formatTimeframe(item.timeframe)}
                      </span>
                      <span className="search-sidebar__item-rows">
                        {item.rowCount.toLocaleString()}
                      </span>
                    </button>
                  );
                })}
              </div>
            )}
          </div>
        ))}
        {catalog.length === 0 && (
          <div className="search-sidebar__empty">No datasets available</div>
        )}
      </div>

      {/* Controls */}
      <div className="search-sidebar__controls">
        <div className="search-sidebar__control-group">
          <label className="search-sidebar__label">
            Query window
            <span className="search-sidebar__label-value">{querySize}</span>
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
        </div>

        {!state.loading ? (
          <button
            type="button"
            className="search-sidebar__run-btn"
            onClick={handleSearch}
            disabled={!selectedDataset}
          >
            Run search
          </button>
        ) : (
          <button
            type="button"
            className="search-sidebar__cancel-btn"
            onClick={handleCancel}
          >
            Cancel
          </button>
        )}
      </div>
    </div>
  );
}
