"use client";

/**
 * Finance run comparison page — /finance/compare?ids=abc,def,ghi,...
 *
 * Multi-run comparison table supporting N columns dynamically.
 * Features:
 * - N-column comparison: each run gets its own column, best value highlighted
 * - Run selector: dropdown to add more runs from API
 * - Metric delta display: absolute value + delta from best
 * - Summary row: winner = run with most "best" metrics
 * - Copy as CSV: exports comparison table to clipboard
 * - Calibration comparison: side-by-side calibration data when available
 */

import { useEffect, useState, useCallback, Suspense } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import Link from "next/link";
import { fetchRun, fetchRuns, type Run } from "../../../lib/platform-api";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Safely traverse nested objects by key path.
 * Returns undefined if any intermediate key is missing or not an object.
 */
function dig(obj: Record<string, unknown>, ...keys: string[]): unknown {
  let cur: unknown = obj;
  for (const k of keys) {
    if (cur == null || typeof cur !== "object") return undefined;
    cur = (cur as Record<string, unknown>)[k];
  }
  return cur;
}

/** Format a numeric value to `decimals` fixed places; "-" for null/NaN. */
function fmt(val: unknown, decimals = 4): string {
  if (val == null) return "-";
  const n = Number(val);
  if (Number.isNaN(n)) return "-";
  return n.toFixed(decimals);
}

/** Format a numeric value as a percentage (multiply by 100). */
function pct(val: unknown): string {
  if (val == null) return "-";
  const n = Number(val);
  if (Number.isNaN(n)) return "-";
  return `${(n * 100).toFixed(1)}%`;
}

/** Extract the ticker/symbol label from a run's config. */
function runSymbol(run: Run): string {
  const sym = dig(run.config, "symbol") ?? dig(run.config, "ticker");
  return sym != null ? String(sym) : "-";
}

// ---------------------------------------------------------------------------
// Metric definitions
// ---------------------------------------------------------------------------

/** Describes a single metric row in the comparison table. */
interface MetricDef {
  label: string;
  /** Key path into run.summary to extract the raw value. */
  path: string[];
  /** Formatting function for display. */
  format: (v: unknown) => string;
  /**
   * Comparison direction:
   * - "higher" = higher numeric value is better
   * - "lower"  = lower numeric value is better
   * - "none"   = no ranking (e.g. categorical values)
   */
  direction: "higher" | "lower" | "none";
}

const METRICS: MetricDef[] = [
  { label: "Hit Rate", path: ["hit_rate"], format: pct, direction: "higher" },
  { label: "CRPS", path: ["crps"], format: (v) => fmt(v, 4), direction: "lower" },
  { label: "Coverage", path: ["coverage"], format: pct, direction: "higher" },
  { label: "Profit Factor", path: ["profit_factor"], format: (v) => fmt(v, 2), direction: "higher" },
  { label: "Max Drawdown", path: ["max_drawdown"], format: pct, direction: "higher" },
  { label: "Sharpe Ratio", path: ["sharpe_ratio"], format: (v) => fmt(v, 2), direction: "higher" },
  { label: "Trust Score", path: ["trust_score"], format: (v) => fmt(v, 3), direction: "higher" },
  { label: "Calibration Grade", path: ["calibration_grade"], format: (v) => (v != null ? String(v) : "-"), direction: "none" },
];

// ---------------------------------------------------------------------------
// Calibration percentile buckets — standard quantiles used in backtester
// ---------------------------------------------------------------------------

const CALIBRATION_PERCENTILES = [10, 20, 30, 40, 50, 60, 70, 80, 90];

// ---------------------------------------------------------------------------
// Run Selector component — dropdown to add additional runs
// ---------------------------------------------------------------------------

/**
 * Fetches all finance runs and renders a search/select dropdown.
 * Excludes runs that are already in the comparison (by ID).
 */
function RunSelector({
  excludeIds,
  onSelect,
}: {
  excludeIds: Set<string>;
  onSelect: (runId: string) => void;
}) {
  const [allRuns, setAllRuns] = useState<Run[]>([]);
  const [loadingRuns, setLoadingRuns] = useState(false);
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");

  /* Fetch available runs when the dropdown opens for the first time. */
  useEffect(() => {
    if (!open || allRuns.length > 0) return;
    setLoadingRuns(true);
    fetchRuns("finance")
      .then((runs) => setAllRuns(runs))
      .catch(() => setAllRuns([]))
      .finally(() => setLoadingRuns(false));
  }, [open, allRuns.length]);

  /* Filter runs by search term (matches run_id or symbol). */
  const filtered = allRuns.filter((r) => {
    if (excludeIds.has(r.run_id)) return false;
    if (!search) return true;
    const q = search.toLowerCase();
    const sym = runSymbol(r).toLowerCase();
    return r.run_id.toLowerCase().includes(q) || sym.includes(q);
  });

  return (
    <div style={{ position: "relative", display: "inline-block" }}>
      <button
        onClick={() => setOpen(!open)}
        style={{
          fontFamily: "var(--mono)",
          fontSize: 12,
          padding: "6px 14px",
          border: "1px solid var(--rule)",
          borderRadius: 4,
          background: "var(--bg-elevated)",
          color: "var(--ink-2)",
          cursor: "pointer",
        }}
      >
        + Add run
      </button>

      {open && (
        <div
          style={{
            position: "absolute",
            top: "100%",
            left: 0,
            marginTop: 4,
            width: 280,
            maxHeight: 300,
            overflowY: "auto",
            background: "var(--bg-elevated)",
            border: "1px solid var(--rule)",
            borderRadius: 6,
            boxShadow: "0 4px 16px rgba(0,0,0,.08)",
            zIndex: 10,
          }}
        >
          {/* Search input */}
          <div style={{ padding: "8px 10px", borderBottom: "1px solid var(--rule)" }}>
            <input
              type="text"
              placeholder="Search by ID or symbol..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              autoFocus
              style={{
                width: "100%",
                fontFamily: "var(--mono)",
                fontSize: 11,
                padding: "4px 8px",
                border: "1px solid var(--rule)",
                borderRadius: 3,
                background: "var(--bg-inset)",
                color: "var(--ink)",
                outline: "none",
              }}
            />
          </div>

          {/* Run list */}
          {loadingRuns ? (
            <div style={{ padding: 16, fontSize: 11, color: "var(--ink-3)", textAlign: "center" }}>
              Loading runs...
            </div>
          ) : filtered.length === 0 ? (
            <div style={{ padding: 16, fontSize: 11, color: "var(--ink-3)", textAlign: "center" }}>
              No runs available
            </div>
          ) : (
            filtered.slice(0, 20).map((r) => (
              <button
                key={r.run_id}
                onClick={() => {
                  onSelect(r.run_id);
                  setOpen(false);
                  setSearch("");
                }}
                style={{
                  display: "block",
                  width: "100%",
                  textAlign: "left",
                  padding: "8px 12px",
                  border: "none",
                  borderBottom: "1px solid var(--rule)",
                  background: "transparent",
                  cursor: "pointer",
                  fontFamily: "var(--mono)",
                  fontSize: 11,
                  color: "var(--ink)",
                }}
                onMouseEnter={(e) => {
                  (e.target as HTMLElement).style.background = "var(--bg-hover)";
                }}
                onMouseLeave={(e) => {
                  (e.target as HTMLElement).style.background = "transparent";
                }}
              >
                <span style={{ fontWeight: 600 }}>{r.run_id.slice(0, 8)}</span>
                <span style={{ color: "var(--ink-3)", marginLeft: 8 }}>{runSymbol(r)}</span>
              </button>
            ))
          )}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// CSV export helper
// ---------------------------------------------------------------------------

/**
 * Build a CSV string from the comparison data.
 * Columns: Metric, then one column per run (header = truncated run_id).
 * Includes delta columns for each run showing distance from best.
 */
function buildCsv(runs: Run[]): string {
  const headers = ["Metric"];
  for (const r of runs) {
    headers.push(r.run_id.slice(0, 8));
    headers.push(`${r.run_id.slice(0, 8)} (delta)`);
  }

  const rows: string[][] = [headers];

  for (const m of METRICS) {
    const row: string[] = [m.label];
    const values = runs.map((r) => {
      const raw = dig(r.summary, ...m.path);
      return raw != null ? Number(raw) : NaN;
    });

    /* Determine best value for delta computation. */
    const validValues = values.filter((v) => !Number.isNaN(v));
    const bestVal =
      m.direction === "none" || validValues.length === 0
        ? NaN
        : m.direction === "higher"
          ? Math.max(...validValues)
          : Math.min(...validValues);

    for (let i = 0; i < runs.length; i++) {
      const formatted = m.format(dig(runs[i].summary, ...m.path));
      row.push(formatted);

      /* Delta from best — 0 means this IS the best. */
      if (Number.isNaN(values[i]) || Number.isNaN(bestVal) || m.direction === "none") {
        row.push("-");
      } else {
        const delta = values[i] - bestVal;
        row.push(delta === 0 ? "0" : delta.toFixed(4));
      }
    }

    rows.push(row);
  }

  /* Winner summary row. */
  const winCounts = computeWinCounts(runs);
  const winnerRow: string[] = ["Winner"];
  for (let i = 0; i < runs.length; i++) {
    winnerRow.push(`${winCounts[i]} best`);
    winnerRow.push(""); // no delta for winner row
  }
  rows.push(winnerRow);

  return rows.map((r) => r.map((c) => `"${c}"`).join(",")).join("\n");
}

// ---------------------------------------------------------------------------
// Win count computation — how many metrics each run "wins"
// ---------------------------------------------------------------------------

/**
 * For each run, count how many metrics it has the best value in.
 * Returns an array parallel to the runs array.
 */
function computeWinCounts(runs: Run[]): number[] {
  const counts = new Array(runs.length).fill(0);

  for (const m of METRICS) {
    if (m.direction === "none") continue;

    const values = runs.map((r) => {
      const raw = dig(r.summary, ...m.path);
      return raw != null ? Number(raw) : NaN;
    });

    const validValues = values.filter((v) => !Number.isNaN(v));
    if (validValues.length === 0) continue;

    const bestVal =
      m.direction === "higher"
        ? Math.max(...validValues)
        : Math.min(...validValues);

    /* Award a win to every run that ties for best. */
    for (let i = 0; i < runs.length; i++) {
      if (!Number.isNaN(values[i]) && values[i] === bestVal) {
        counts[i]++;
      }
    }
  }

  return counts;
}

// ---------------------------------------------------------------------------
// Calibration comparison section
// ---------------------------------------------------------------------------

/**
 * CalibrationRow: a single expected vs observed percentile row.
 */
interface CalibrationEntry {
  expected: number;
  observed: number | null;
}

/**
 * Extract calibration data from a run's summary.
 * Expects summary.calibration to be an object with percentile keys
 * (e.g., { "10": 0.12, "20": 0.18, ... }) or summary.calibration_data
 * as an array of {expected, observed} entries.
 */
function extractCalibration(run: Run): CalibrationEntry[] | null {
  /* Try summary.calibration_data as array first. */
  const calData = dig(run.summary, "calibration_data");
  if (Array.isArray(calData) && calData.length > 0) {
    return calData.map((entry: { expected?: number; observed?: number }) => ({
      expected: Number(entry.expected ?? 0),
      observed: entry.observed != null ? Number(entry.observed) : null,
    }));
  }

  /* Try summary.calibration as { percentile: observed } map. */
  const calMap = dig(run.summary, "calibration");
  if (calMap != null && typeof calMap === "object" && !Array.isArray(calMap)) {
    const map = calMap as Record<string, unknown>;
    const entries: CalibrationEntry[] = [];
    for (const p of CALIBRATION_PERCENTILES) {
      const val = map[String(p)];
      entries.push({
        expected: p,
        observed: val != null ? Number(val) : null,
      });
    }
    /* Only return if at least one observed value exists. */
    if (entries.some((e) => e.observed != null)) return entries;
  }

  return null;
}

/**
 * Renders a side-by-side calibration comparison section.
 * Each run's expected vs observed percentiles shown in adjacent columns.
 */
function CalibrationComparison({ runs }: { runs: Run[] }) {
  /* Extract calibration data for all runs. */
  const calibrations = runs.map(extractCalibration);

  /* Only render if at least one run has calibration data. */
  if (calibrations.every((c) => c == null)) return null;

  /* Merge all expected percentiles into a unified set. */
  const allExpected = new Set<number>();
  for (const cal of calibrations) {
    if (cal) {
      for (const entry of cal) {
        allExpected.add(entry.expected);
      }
    }
  }
  const sortedExpected = Array.from(allExpected).sort((a, b) => a - b);

  return (
    <div style={{ marginTop: 40 }}>
      <h2
        style={{
          fontFamily: "var(--serif)",
          fontSize: 18,
          fontWeight: 600,
          color: "var(--ink)",
          marginBottom: 16,
        }}
      >
        Calibration Comparison
      </h2>
      <p
        style={{
          fontFamily: "var(--sans)",
          fontSize: 12,
          color: "var(--ink-3)",
          marginBottom: 12,
        }}
      >
        Expected vs observed coverage percentiles. A well-calibrated model has observed
        values close to expected.
      </p>

      <div className="portfolio-table-wrap" style={{ overflowX: "auto" }}>
        <table className="portfolio-table" style={{ minWidth: runs.length * 120 + 120 }}>
          <thead>
            <tr>
              <th className="portfolio-table__th" style={{ width: 100 }}>
                Expected
              </th>
              {runs.map((r, i) => (
                <th
                  key={r.run_id}
                  className="portfolio-table__th portfolio-table__th--right"
                  colSpan={1}
                >
                  <span style={{ fontSize: 10, fontWeight: 600 }}>
                    {r.run_id.slice(0, 8)}
                  </span>
                  <br />
                  <span style={{ fontSize: 9, color: "var(--ink-4)", fontWeight: 400 }}>
                    observed
                  </span>
                  {calibrations[i] == null && (
                    <>
                      <br />
                      <span style={{ fontSize: 9, color: "var(--ink-4)", fontStyle: "italic" }}>
                        no data
                      </span>
                    </>
                  )}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {sortedExpected.map((exp) => (
              <tr key={exp} className="portfolio-table__row">
                <td
                  className="portfolio-table__td portfolio-table__td--mono"
                  style={{ fontWeight: 600 }}
                >
                  {exp}%
                </td>
                {runs.map((r, i) => {
                  const cal = calibrations[i];
                  if (!cal) {
                    return (
                      <td
                        key={r.run_id}
                        className="portfolio-table__td portfolio-table__td--mono portfolio-table__td--right"
                        style={{ color: "var(--ink-4)" }}
                      >
                        -
                      </td>
                    );
                  }
                  const entry = cal.find((e) => e.expected === exp);
                  const obs = entry?.observed;
                  if (obs == null) {
                    return (
                      <td
                        key={r.run_id}
                        className="portfolio-table__td portfolio-table__td--mono portfolio-table__td--right"
                        style={{ color: "var(--ink-4)" }}
                      >
                        -
                      </td>
                    );
                  }

                  /* Color based on deviation from expected. */
                  const deviation = Math.abs(obs - exp);
                  let color = "var(--positive)"; // good: within 5pp
                  if (deviation > 15) color = "var(--negative)"; // poor: >15pp deviation
                  else if (deviation > 5) color = "var(--warn)"; // moderate: 5-15pp

                  return (
                    <td
                      key={r.run_id}
                      className="portfolio-table__td portfolio-table__td--mono portfolio-table__td--right"
                      style={{ color, fontWeight: 600 }}
                    >
                      {obs.toFixed(1)}%
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Inner component (needs useSearchParams, must be wrapped in Suspense)
// ---------------------------------------------------------------------------

function CompareInner() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const idsParam = searchParams.get("ids") ?? "";

  /* Parse run IDs from URL — no cap on count (supports N-way comparison). */
  const ids = idsParam
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);

  const [runs, setRuns] = useState<Run[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [copyFeedback, setCopyFeedback] = useState(false);

  /* Fetch all runs by their IDs whenever the URL parameter changes. */
  useEffect(() => {
    if (ids.length < 2) {
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    Promise.all(ids.map((id) => fetchRun(id)))
      .then((results) => {
        /* Filter out any nulls from failed fetches. */
        setRuns(results.filter((r): r is Run => r != null));
      })
      .catch((err) =>
        setError(err instanceof Error ? err.message : String(err))
      )
      .finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [idsParam]);

  /**
   * Add a run to the comparison by updating the URL query parameter.
   * This triggers a re-fetch via the useEffect above.
   */
  const handleAddRun = useCallback(
    (runId: string) => {
      const newIds = [...ids, runId];
      router.push(`/finance/compare?ids=${newIds.join(",")}`);
    },
    [ids, router]
  );

  /**
   * Remove a run from the comparison by ID.
   * If fewer than 2 remain, the empty state will render.
   */
  const handleRemoveRun = useCallback(
    (runId: string) => {
      const newIds = ids.filter((id) => id !== runId);
      router.push(`/finance/compare?ids=${newIds.join(",")}`);
    },
    [ids, router]
  );

  /**
   * Copy the comparison table as CSV to the clipboard.
   * Shows brief feedback on success.
   */
  const handleCopyCSV = useCallback(() => {
    if (runs.length < 2) return;
    const csv = buildCsv(runs);
    navigator.clipboard
      .writeText(csv)
      .then(() => {
        setCopyFeedback(true);
        setTimeout(() => setCopyFeedback(false), 2000);
      })
      .catch(() => {
        /* Fallback: no-op if clipboard unavailable. */
      });
  }, [runs]);

  // -------------------------------------------------------------------------
  // Empty state — fewer than 2 IDs in the URL
  // -------------------------------------------------------------------------

  if (ids.length < 2 && !loading) {
    return (
      <div className="deck-page">
        <div className="deck-page__inner">
          <p className="deck-page__label">
            <Link href="/finance" style={{ color: "inherit", textDecoration: "none" }}>
              Finance
            </Link>{" "}
            / Compare
          </p>
          <h1 className="deck-page__title">Compare Runs</h1>

          {/* Allow adding runs even from empty state. */}
          <div style={{ marginTop: 16, marginBottom: 16 }}>
            <RunSelector excludeIds={new Set(ids)} onSelect={handleAddRun} />
          </div>

          <div className="deck-feed-empty" style={{ marginTop: 32 }}>
            Select at least two runs from the{" "}
            <Link href="/finance" style={{ color: "var(--accent)" }}>
              finance runs list
            </Link>{" "}
            to compare.
          </div>
        </div>
      </div>
    );
  }

  // -------------------------------------------------------------------------
  // Loading state
  // -------------------------------------------------------------------------

  if (loading) {
    return (
      <div className="deck-page">
        <div className="deck-page__inner">
          <div className="deck-feed-empty">Loading comparison...</div>
        </div>
      </div>
    );
  }

  // -------------------------------------------------------------------------
  // Error state
  // -------------------------------------------------------------------------

  if (error) {
    return (
      <div className="deck-page">
        <div className="deck-page__inner">
          <div className="match-list-error" style={{ padding: 40 }}>
            <div className="match-list-error__icon">!</div>
            <p className="match-list-error__text">{error}</p>
            <Link href="/finance" className="match-list-error__retry">
              Back to runs
            </Link>
          </div>
        </div>
      </div>
    );
  }

  // -------------------------------------------------------------------------
  // Validate loaded runs — need at least 2
  // -------------------------------------------------------------------------

  if (runs.length < 2) {
    return (
      <div className="deck-page">
        <div className="deck-page__inner">
          <div className="deck-feed-empty">
            Could not load enough runs for comparison. At least 2 are required.
          </div>
        </div>
      </div>
    );
  }

  // -------------------------------------------------------------------------
  // Compute per-run win counts for the summary row
  // -------------------------------------------------------------------------

  const winCounts = computeWinCounts(runs);
  const maxWins = Math.max(...winCounts);

  /* Build a title from run symbols. */
  const symbols = runs.map(runSymbol);
  const title =
    runs.length <= 4
      ? symbols.join(" vs ")
      : `${symbols.slice(0, 3).join(", ")} + ${runs.length - 3} more`;

  /* Track which IDs are currently compared (for excluding from the selector). */
  const currentIdSet = new Set(runs.map((r) => r.run_id));

  return (
    <div className="deck-page">
      <div className="deck-page__inner">
        <p className="deck-page__label">
          <Link href="/finance" style={{ color: "inherit", textDecoration: "none" }}>
            Finance
          </Link>{" "}
          / Compare
        </p>
        <h1 className="deck-page__title">{title}</h1>
        <p className="deck-page__intro">
          Multi-run comparison. Best metric per row highlighted green with bold weight.
          Deltas show distance from the best value.
        </p>

        {/* ----------------------------------------------------------------- */}
        {/* Toolbar: add run + copy CSV                                       */}
        {/* ----------------------------------------------------------------- */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 12,
            marginBottom: 20,
            flexWrap: "wrap",
          }}
        >
          <RunSelector excludeIds={currentIdSet} onSelect={handleAddRun} />

          <button
            onClick={handleCopyCSV}
            style={{
              fontFamily: "var(--mono)",
              fontSize: 12,
              padding: "6px 14px",
              border: "1px solid var(--rule)",
              borderRadius: 4,
              background: copyFeedback ? "var(--positive-soft)" : "var(--bg-elevated)",
              color: copyFeedback ? "var(--positive)" : "var(--ink-2)",
              cursor: "pointer",
              transition: "background 200ms, color 200ms",
            }}
          >
            {copyFeedback ? "Copied!" : "Copy as CSV"}
          </button>
        </div>

        {/* ----------------------------------------------------------------- */}
        {/* Comparison table — N columns                                      */}
        {/* ----------------------------------------------------------------- */}
        <div className="portfolio-table-wrap" style={{ overflowX: "auto" }}>
          <table className="portfolio-table" style={{ minWidth: runs.length * 140 + 160 }}>
            <thead>
              <tr>
                <th className="portfolio-table__th" style={{ width: 160, position: "sticky", left: 0, background: "var(--bg-elevated)", zIndex: 2 }}>
                  Metric
                </th>
                {runs.map((r, i) => (
                  <th
                    key={r.run_id}
                    className="portfolio-table__th portfolio-table__th--right"
                    style={{ minWidth: 120 }}
                  >
                    <div style={{ display: "flex", alignItems: "center", justifyContent: "flex-end", gap: 6 }}>
                      <Link
                        href={`/finance/${r.run_id}`}
                        style={{
                          color: "inherit",
                          textDecoration: "none",
                          borderBottom: "1px dotted var(--rule-strong)",
                        }}
                      >
                        {r.run_id.slice(0, 8)}
                      </Link>
                      {/* Remove button — only show if 3+ runs so we don't go below 2. */}
                      {runs.length > 2 && (
                        <button
                          onClick={() => handleRemoveRun(r.run_id)}
                          title="Remove from comparison"
                          style={{
                            border: "none",
                            background: "none",
                            cursor: "pointer",
                            color: "var(--ink-4)",
                            fontSize: 14,
                            lineHeight: 1,
                            padding: 0,
                          }}
                        >
                          x
                        </button>
                      )}
                    </div>
                    <span style={{ fontSize: 10, color: "var(--ink-3)", fontWeight: 500 }}>
                      {symbols[i]}
                    </span>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {METRICS.map((m) => {
                /* Extract all numeric values for this metric across runs. */
                const values = runs.map((r) => {
                  const raw = dig(r.summary, ...m.path);
                  return raw != null ? Number(raw) : NaN;
                });
                const validValues = values.filter((v) => !Number.isNaN(v));

                /* Determine the best value for highlighting and delta. */
                const bestVal =
                  m.direction === "none" || validValues.length === 0
                    ? NaN
                    : m.direction === "higher"
                      ? Math.max(...validValues)
                      : Math.min(...validValues);

                return (
                  <tr key={m.label} className="portfolio-table__row">
                    <td
                      className="portfolio-table__td"
                      style={{
                        fontWeight: 600,
                        position: "sticky",
                        left: 0,
                        background: "var(--bg-elevated)",
                        zIndex: 1,
                      }}
                    >
                      {m.label}
                    </td>

                    {runs.map((r, i) => {
                      const rawVal = dig(r.summary, ...m.path);
                      const numVal = values[i];
                      const formatted = m.format(rawVal);

                      /* Determine cell color: green for best, red for non-best. */
                      const canCompare =
                        m.direction !== "none" &&
                        !Number.isNaN(numVal) &&
                        !Number.isNaN(bestVal) &&
                        validValues.length > 1;

                      const isBest = canCompare && numVal === bestVal;
                      const color = !canCompare
                        ? "inherit"
                        : isBest
                          ? "var(--positive)"
                          : "var(--negative)";

                      /* Compute delta from best for non-best runs. */
                      let deltaStr = "";
                      if (
                        canCompare &&
                        !Number.isNaN(numVal) &&
                        !Number.isNaN(bestVal) &&
                        !isBest
                      ) {
                        const delta = numVal - bestVal;
                        /* Format delta the same way the metric is formatted.
                           For percentage metrics, show delta as pp. */
                        const absDelta = Math.abs(delta);
                        deltaStr =
                          m.format === pct
                            ? ` (${delta >= 0 ? "+" : "-"}${(absDelta * 100).toFixed(1)}pp)`
                            : ` (${delta >= 0 ? "+" : ""}${delta.toFixed(4)})`;
                      }

                      return (
                        <td
                          key={r.run_id}
                          className="portfolio-table__td portfolio-table__td--mono portfolio-table__td--right"
                          style={{
                            color,
                            fontWeight: isBest ? 700 : 400,
                            whiteSpace: "nowrap",
                          }}
                        >
                          {formatted}
                          {deltaStr && (
                            <span
                              style={{
                                fontSize: 10,
                                opacity: 0.7,
                                fontWeight: 400,
                              }}
                            >
                              {deltaStr}
                            </span>
                          )}
                        </td>
                      );
                    })}
                  </tr>
                );
              })}

              {/* ------------------------------------------------------------- */}
              {/* Summary / Winner row                                          */}
              {/* ------------------------------------------------------------- */}
              <tr
                className="portfolio-table__row"
                style={{ borderTop: "2px solid var(--rule-strong)" }}
              >
                <td
                  className="portfolio-table__td"
                  style={{
                    fontWeight: 700,
                    position: "sticky",
                    left: 0,
                    background: "var(--bg-elevated)",
                    zIndex: 1,
                    fontFamily: "var(--serif)",
                    fontSize: 13,
                  }}
                >
                  Winner
                </td>
                {runs.map((r, i) => {
                  const isOverallWinner = winCounts[i] === maxWins && maxWins > 0;
                  return (
                    <td
                      key={r.run_id}
                      className="portfolio-table__td portfolio-table__td--mono portfolio-table__td--right"
                      style={{
                        fontWeight: isOverallWinner ? 700 : 400,
                        color: isOverallWinner ? "var(--positive)" : "var(--ink-3)",
                      }}
                    >
                      {winCounts[i]} best
                      {isOverallWinner && runs.length > 2 && (
                        <span
                          style={{
                            marginLeft: 6,
                            fontSize: 10,
                            fontWeight: 700,
                            color: "var(--positive)",
                          }}
                        >
                          WINNER
                        </span>
                      )}
                    </td>
                  );
                })}
              </tr>
            </tbody>
          </table>
        </div>

        {/* ----------------------------------------------------------------- */}
        {/* Calibration comparison section                                     */}
        {/* ----------------------------------------------------------------- */}
        <CalibrationComparison runs={runs} />

        {/* ----------------------------------------------------------------- */}
        {/* Footer link                                                       */}
        {/* ----------------------------------------------------------------- */}
        <div style={{ marginTop: 24 }}>
          <Link
            href="/finance"
            style={{
              fontFamily: "var(--mono)",
              fontSize: 12,
              color: "var(--ink-3)",
              textDecoration: "none",
              borderBottom: "1px dotted var(--rule-strong)",
            }}
          >
            Back to all runs
          </Link>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Page component — Suspense boundary required for useSearchParams
// ---------------------------------------------------------------------------

export default function FinanceComparePage() {
  return (
    <Suspense
      fallback={
        <div className="deck-page">
          <div className="deck-page__inner">
            <div className="deck-feed-empty">Loading comparison...</div>
          </div>
        </div>
      }
    >
      <CompareInner />
    </Suspense>
  );
}
