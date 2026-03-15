"use client";
import { useState, useRef, useCallback, useEffect } from "react";
import { useTerminal } from "../../lib/terminal-context";
import { searchApi } from "../../lib/api";

function parseValues(raw: string): number[] {
  return raw
    .split(/[,\n]+/)
    .map((s) => s.trim())
    .filter((s) => s.length > 0)
    .map(Number)
    .filter((n) => !Number.isNaN(n));
}

export function SearchInput() {
  const { state, dispatch } = useTerminal();
  const [queryText, setQueryText] = useState("");
  const [historyText, setHistoryText] = useState("");
  const [expanded, setExpanded] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    return () => { abortRef.current?.abort(); };
  }, []);

  const queryCount = parseValues(queryText).length;
  const historyCount = historyText.trim() ? parseValues(historyText).length : 0;

  const handleSearch = useCallback(async () => {
    const queryValues = parseValues(queryText);
    if (queryValues.length < 2) {
      dispatch({ type: "SET_ERROR", error: "Query must contain at least 2 numeric values." });
      return;
    }

    const historyValues = parseValues(historyText);
    if (historyValues.length < 2 && historyText.trim()) {
      dispatch({ type: "SET_ERROR", error: "History must contain at least 2 numeric values." });
      return;
    }

    if (!historyText.trim()) {
      dispatch({ type: "SET_ERROR", error: "Paste history values to search against." });
      return;
    }

    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    dispatch({ type: "SET_LOADING", loading: true });
    dispatch({ type: "SET_ERROR", error: null });

    try {
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
  }, [queryText, historyText, state.activeMethods, dispatch]);

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
        <div className="search-bar-field">
          <label className="search-bar-label">
            Query
            <span className="search-bar-count">{queryCount} values</span>
          </label>
          <textarea
            className="search-bar-textarea"
            placeholder="Paste comma or newline separated values…"
            value={queryText}
            onChange={(e) => setQueryText(e.target.value)}
            rows={2}
          />
        </div>
        <div className="search-bar-field">
          <label className="search-bar-label">
            History
            <span className="search-bar-count">
              {historyText.trim() ? `${historyCount} values` : "required"}
            </span>
          </label>
          <textarea
            className="search-bar-textarea"
            placeholder="Paste the historical series to search against…"
            value={historyText}
            onChange={(e) => setHistoryText(e.target.value)}
            rows={2}
          />
        </div>
      </div>
      <div className="search-bar-actions">
        {!state.loading ? (
          <button
            type="button"
            className="search-bar-btn search-bar-btn--run"
            onClick={handleSearch}
            disabled={queryCount < 2}
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
