"use client";
import { useState, useRef, useCallback, useEffect } from "react";
import { useTerminal } from "../../lib/terminal-context";
import { fetchCatalog, fetchSeries, fetchOhlc, searchApi } from "../../lib/api";
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

type SearchProgress = {
  stage: string;
  completed: number;
  total: number;
  topScore: number;
};

const PROGRESS_STAGES = [
  { label: "Prefiltering...", duration: 1000 },
  { label: "Scoring Tier 1...", duration: 2000 },
  { label: "Enriching Tier 2...", duration: 0 }, // runs until results arrive
];

export function SearchSidebar() {
  const { state, dispatch } = useTerminal();
  const [catalog, setCatalog] = useState<CatalogItem[]>([]);
  const [selectedDataset, setSelectedDataset] = useState<string>("");
  const [querySize, setQuerySize] = useState(60);
  const [filterText, setFilterText] = useState("");
  const [expandedGroups, setExpandedGroups] = useState<Set<string>>(new Set(["crypto", "stocks"]));
  const [progress, setProgress] = useState<SearchProgress | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const progressTimers = useRef<ReturnType<typeof setTimeout>[]>([]);

  // Load catalog on mount
  useEffect(() => {
    fetchCatalog()
      .then(setCatalog)
      .catch(() => {});
  }, []);

  useEffect(() => {
    return () => {
      abortRef.current?.abort();
      progressTimers.current.forEach(clearTimeout);
    };
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

  const startProgressSimulation = useCallback(() => {
    progressTimers.current.forEach(clearTimeout);
    progressTimers.current = [];

    // Stage 0: Prefiltering
    setProgress({ stage: PROGRESS_STAGES[0].label, completed: 0, total: 100, topScore: 0 });

    let elapsed = 0;
    for (let i = 0; i < PROGRESS_STAGES.length; i++) {
      const stage = PROGRESS_STAGES[i];
      const timer = setTimeout(() => {
        const pct = i === 0 ? 25 : i === 1 ? 60 : 85;
        setProgress((prev) => ({
          stage: stage.label,
          completed: pct,
          total: 100,
          topScore: prev?.topScore ?? 0,
        }));
      }, elapsed);
      progressTimers.current.push(timer);
      elapsed += stage.duration;
      if (stage.duration === 0) break; // tier 2 runs until done
    }
  }, []);

  const finishProgress = useCallback((topScore: number) => {
    progressTimers.current.forEach(clearTimeout);
    progressTimers.current = [];
    setProgress({ stage: "Done", completed: 100, total: 100, topScore });
    const timer = setTimeout(() => setProgress(null), 1500);
    progressTimers.current.push(timer);
  }, []);

  const clearProgress = useCallback(() => {
    progressTimers.current.forEach(clearTimeout);
    progressTimers.current = [];
    setProgress(null);
  }, []);

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
    startProgressSimulation();

    try {
      const [series, ohlc] = await Promise.all([
        fetchSeries(assetClass, symbol, timeframe),
        fetchOhlc(assetClass, symbol, timeframe).catch(() => null),
      ]);

      if (ohlc) {
        dispatch({ type: "SET_OHLC", data: ohlc });
      }

      if (series.values.length < querySize + 10) {
        dispatch({ type: "SET_ERROR", error: `Not enough data (${series.values.length} points, need ${querySize + 10}).` });
        clearProgress();
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
          forwardBars: 200, // fetch max, slider controls display
        },
        controller.signal,
      );

      const topScore = response.matches.length > 0
        ? response.matches[0].confidenceScore
        : 0;
      finishProgress(topScore);
      dispatch({ type: "SET_SEARCH_RESPONSE", response });
    } catch (err: unknown) {
      clearProgress();
      if (err instanceof Error && err.name === "AbortError") return;
      dispatch({ type: "SET_ERROR", error: err instanceof Error ? err.message : "Search failed." });
    }
  }, [selectedDataset, querySize, state.activeMethods, dispatch, startProgressSimulation, finishProgress, clearProgress]);

  const handleCancel = useCallback(() => {
    abortRef.current?.abort();
    clearProgress();
    dispatch({ type: "SET_LOADING", loading: false });
  }, [dispatch, clearProgress]);

  return (
    <div className="search-sidebar">
      {/* Search filter */}
      <div className="search-sidebar__filter">
        <input
          type="text"
          className="search-sidebar__filter-input"
          placeholder="Filter datasets\u2026"
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
                &#x203A;
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

        {/* Search Progress */}
        {progress && (
          <div className="search-progress">
            <div className="search-progress-stage">
              <span className={progress.stage !== "Done" ? "search-progress-pulse" : ""}>
                {progress.stage}
              </span>
              {progress.topScore > 0 && (
                <span className="search-progress-score">
                  Top: {progress.topScore.toFixed(1)}
                </span>
              )}
            </div>
            <div className="search-progress-bar">
              <div
                className="search-progress-fill"
                style={{ width: `${(progress.completed / progress.total) * 100}%` }}
              />
            </div>
          </div>
        )}

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
