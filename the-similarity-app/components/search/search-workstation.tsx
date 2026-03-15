"use client";

import { useState, useRef, useCallback, useEffect } from "react";
import { Sparkline } from "./sparkline";
import { ScoreBreakdownBar } from "./score-breakdown-bar";
import { OverlayChart } from "./overlay-chart";
import { searchApi } from "../../lib/api";
import type { MatchResult, SearchResponse } from "../../lib/types";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const ALL_METHODS = [
  { key: "dtw", label: "DTW" },
  { key: "pearson_warped", label: "Pearson" },
  { key: "bempedelis_r2", label: "Bempedelis R\u00B2" },
  { key: "bempedelis_smoothness", label: "Bempedelis Smooth" },
  { key: "koopman", label: "Koopman" },
  { key: "wavelet_spectrum", label: "Wavelet" },
  { key: "emd", label: "EMD" },
  { key: "tda", label: "TDA" },
  { key: "transfer_entropy", label: "Transfer Entropy" },
] as const;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function parseValues(raw: string): number[] {
  return raw
    .split(/[,\n]+/)
    .map((s) => s.trim())
    .filter((s) => s.length > 0)
    .map(Number)
    .filter((n) => !Number.isNaN(n));
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function SearchWorkstation() {
  const [queryText, setQueryText] = useState("");
  const [historyText, setHistoryText] = useState("");
  const [activeMethods, setActiveMethods] = useState<Set<string>>(
    new Set(ALL_METHODS.map((m) => m.key))
  );
  const [topK, setTopK] = useState(20);
  const [forwardBars, setForwardBars] = useState(50);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [response, setResponse] = useState<SearchResponse | null>(null);
  const [selectedIdx, setSelectedIdx] = useState<number | null>(null);
  const [copied, setCopied] = useState(false);

  const abortRef = useRef<AbortController | null>(null);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      abortRef.current?.abort();
    };
  }, []);

  const toggleMethod = useCallback((key: string) => {
    setActiveMethods((prev) => {
      const next = new Set(prev);
      if (next.has(key)) {
        next.delete(key);
      } else {
        next.add(key);
      }
      return next;
    });
  }, []);

  const handleSearch = useCallback(async () => {
    const queryValues = parseValues(queryText);
    if (queryValues.length < 2) {
      setError("Query must contain at least 2 numeric values.");
      return;
    }

    const historyValues = parseValues(historyText);
    const methods = Array.from(activeMethods);
    if (methods.length === 0) {
      setError("Select at least one method.");
      return;
    }

    // Abort any in-flight request
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    setLoading(true);
    setError(null);
    setResponse(null);
    setSelectedIdx(null);

    try {
      const result = await searchApi(
        {
          queryValues,
          historyValues,
          activeMethods: methods,
          topK,
          forwardBars,
        },
        controller.signal
      );
      setResponse(result);
    } catch (err: unknown) {
      if (err instanceof Error && err.name === "AbortError") {
        // Cancelled by user
        return;
      }
      setError(err instanceof Error ? err.message : "Search failed.");
    } finally {
      setLoading(false);
    }
  }, [queryText, historyText, activeMethods, topK, forwardBars]);

  const handleCancel = useCallback(() => {
    abortRef.current?.abort();
    setLoading(false);
  }, []);

  const handleExport = useCallback(async () => {
    if (!response) return;
    try {
      await navigator.clipboard.writeText(JSON.stringify(response, null, 2));
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Fallback: select text
      setError("Could not copy to clipboard.");
    }
  }, [response]);

  const selectedMatch: MatchResult | null =
    selectedIdx !== null && response ? response.matches[selectedIdx] : null;

  return (
    <main className="page-shell">
      <div className="container">
        <header className="hero">
          <div>
            <p className="eyebrow">Search workstation</p>
            <h1 className="page-title">Pattern Search</h1>
            <p className="hero-copy">
              Paste a query series and run it against historical data using the
              full multi-method similarity pipeline.
            </p>
          </div>
        </header>

        <div className="search-layout">
          {/* ---- Sidebar ---- */}
          <aside className="search-sidebar">
            {/* Query input */}
            <div className="card">
              <p className="card-label">Query values</p>
              <textarea
                className="textarea-input"
                placeholder={"Paste comma-separated or newline-separated numbers\ne.g. 100, 102.5, 98.3, 101.1, ..."}
                value={queryText}
                onChange={(e) => setQueryText(e.target.value)}
              />
              <p className="card-delta neutral" style={{ marginTop: 4 }}>
                {parseValues(queryText).length} values parsed
              </p>
            </div>

            {/* History input */}
            <div className="card">
              <p className="card-label">History values</p>
              <textarea
                className="textarea-input"
                placeholder={"Optional: paste history series\nLeave empty to search against default dataset"}
                value={historyText}
                onChange={(e) => setHistoryText(e.target.value)}
              />
              <p className="card-delta neutral" style={{ marginTop: 4 }}>
                {historyText.trim()
                  ? `${parseValues(historyText).length} values parsed`
                  : "Will use server dataset catalog"}
              </p>
            </div>

            {/* Config panel */}
            <div className="card">
              <p className="card-label">Methods</p>
              <div className="method-toggles">
                {ALL_METHODS.map((m) => (
                  <label key={m.key} className="method-toggle">
                    <input
                      type="checkbox"
                      checked={activeMethods.has(m.key)}
                      onChange={() => toggleMethod(m.key)}
                    />
                    {m.label}
                  </label>
                ))}
              </div>
            </div>

            <div className="card">
              <p className="card-label">Parameters</p>
              <div style={{ display: "grid", gap: 12 }}>
                <div>
                  <label className="method-toggle">Top K</label>
                  <div className="slider-row">
                    <input
                      type="range"
                      min={1}
                      max={50}
                      value={topK}
                      onChange={(e) => setTopK(Number(e.target.value))}
                    />
                    <span className="slider-value">{topK}</span>
                  </div>
                </div>
                <div>
                  <label className="method-toggle">Forward bars</label>
                  <div className="slider-row">
                    <input
                      type="range"
                      min={10}
                      max={200}
                      value={forwardBars}
                      onChange={(e) => setForwardBars(Number(e.target.value))}
                    />
                    <span className="slider-value">{forwardBars}</span>
                  </div>
                </div>
              </div>
            </div>

            {/* Search / Cancel */}
            <div style={{ display: "grid", gap: 8 }}>
              {!loading ? (
                <button
                  type="button"
                  className="search-btn"
                  onClick={handleSearch}
                  disabled={parseValues(queryText).length < 2}
                >
                  Run search
                </button>
              ) : (
                <button
                  type="button"
                  className="search-btn search-btn-cancel"
                  onClick={handleCancel}
                >
                  Cancel
                </button>
              )}
            </div>
          </aside>

          {/* ---- Results area ---- */}
          <div className="search-results">
            {/* Error */}
            {error && (
              <div className="card">
                <p className="card-delta negative">{error}</p>
              </div>
            )}

            {/* Loading */}
            {loading && (
              <div className="loading-indicator">
                <div className="spinner" />
                Searching across candidates...
              </div>
            )}

            {/* Empty state */}
            {!loading && !response && !error && (
              <div className="empty-state">
                <span style={{ fontSize: 28, opacity: 0.3 }}>~</span>
                <span>Paste a query series and hit Run search</span>
                <span style={{ fontSize: 11, color: "var(--text-secondary)" }}>
                  Results will appear here
                </span>
              </div>
            )}

            {/* Results */}
            {response && (
              <>
                {/* Meta bar */}
                <div className="card" style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 8 }}>
                  <div style={{ display: "flex", gap: 16, fontSize: 12, color: "var(--text-secondary)" }}>
                    <span>
                      <strong style={{ color: "var(--text-primary)" }}>
                        {response.matches.length}
                      </strong>{" "}
                      matches
                    </span>
                  </div>
                  <button
                    type="button"
                    className="copy-btn"
                    onClick={handleExport}
                  >
                    {copied ? "Copied!" : "Export JSON"}
                  </button>
                </div>

                {/* Match cards */}
                {response.matches.map((match, idx) => (
                  <button
                    key={idx}
                    type="button"
                    className={`card result-card ${selectedIdx === idx ? "selected" : ""}`}
                    onClick={() =>
                      setSelectedIdx(selectedIdx === idx ? null : idx)
                    }
                    style={{
                      cursor: "pointer",
                      textAlign: "left",
                      width: "100%",
                      border:
                        selectedIdx === idx
                          ? "1px solid var(--active)"
                          : undefined,
                    }}
                  >
                    <div>
                      <div style={{ display: "flex", alignItems: "baseline", gap: 8 }}>
                        <span
                          style={{
                            fontSize: 11,
                            fontWeight: 700,
                            color: "var(--text-secondary)",
                            fontVariantNumeric: "tabular-nums",
                          }}
                        >
                          #{idx + 1}
                        </span>
                        <span className="card-value">
                          {match.confidenceScore.toFixed(1)}
                        </span>
                        <span className="card-unit">confidence</span>
                      </div>
                      <div
                        style={{
                          display: "flex",
                          gap: 12,
                          marginTop: 6,
                          fontSize: 11,
                          color: "var(--text-secondary)",
                        }}
                      >
                        <span>
                          {match.startDate ?? match.startIdx} &mdash; {match.endDate ?? match.endIdx}
                        </span>
                      </div>
                      <div style={{ marginTop: 8 }}>
                        <ScoreBreakdownBar breakdown={match.scoreBreakdown} />
                      </div>
                    </div>
                    <div>
                      {match.matchedSeries && match.matchedSeries.length > 2 && (
                        <Sparkline
                          values={match.matchedSeries}
                          width={100}
                          height={32}
                          color="var(--chart-match)"
                        />
                      )}
                    </div>
                  </button>
                ))}

                {/* Overlay chart */}
                {selectedMatch && selectedMatch.matchedSeries && (
                  <OverlayChart
                    queryValues={response.queryValues}
                    matchValues={selectedMatch.matchedSeries}
                    queryLabel="Your query"
                    matchLabel={`Match #${selectedIdx! + 1}`}
                  />
                )}
              </>
            )}
          </div>
        </div>
      </div>
    </main>
  );
}
