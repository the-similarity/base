/**
 * Runs — finance backtest runs list, surfaced inside the Lumen chrome.
 *
 * Data:
 *   fetchRuns('finance') → newest-first list from the platform API.
 *   Loading / empty / error states are rendered inline; on error we
 *   fall back to a compact card with a link to the canonical
 *   /finance route so the user is never blocked.
 *
 * Visual: a Lumen-styled HTML <table> using the `.lumen-table` class
 * defined in styles.tsx. Rows link to /finance/{run_id}; hover state
 * swaps to surface-2.
 */
"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Topbar } from "../shared";
import { fetchRuns, type Run } from "../../../../../lib/platform-api";
import type { ScreenProps } from "../screen-types";

/**
 * Pull a primitive value out of `run.summary` with a printable
 * fallback. Mirrors the helper in retrieve.tsx — kept inline here so
 * the screens stay self-contained.
 */
function readSummary(run: Run, key: string): string {
  const v = run.summary?.[key];
  if (v === null || v === undefined) return "—";
  if (typeof v === "number") {
    if (key === "hit_rate" || key === "trust_score") {
      return (v * 100).toFixed(1) + "%";
    }
    return String(v);
  }
  if (typeof v === "string") return v;
  return "—";
}

/** Map registry status string → Lumen status pill modifier class. */
function statusClass(status: string): string {
  switch (status) {
    case "complete":
    case "succeeded":
    case "completed":
      return "is-complete";
    case "running":
      return "is-running";
    case "failed":
    case "errored":
      return "is-failed";
    default:
      return "is-pending";
  }
}

export function ScreenRuns({ onCmdK }: ScreenProps) {
  const [runs, setRuns] = useState<Run[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchRuns("finance")
      .then((r) => {
        if (!cancelled) setRuns(r);
      })
      .catch((e: unknown) => {
        if (cancelled) return;
        console.warn("Lumen runs: fetchRuns(finance) failed", e);
        setError(String(e));
        setRuns([]);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="lumen-content-col lumen-screen-fade">
      <Topbar
        crumbs={["Workspace", "Finance", "Runs"]}
        onCmdK={onCmdK}
        actions={
          <Link href="/finance" className="lumen-btn">
            Open finance app
          </Link>
        }
      />
      <div className="lumen-scroll">
        <div className="lumen-scroll-pad">
          {/* Hero */}
          <div className="lumen-mb-24">
            <div className="lumen-eyebrow lumen-mb-12">Finance · runs</div>
            <div
              className="lumen-display"
              style={{ fontSize: 40, marginBottom: 12 }}
            >
              Backtest runs
            </div>
            <div className="lumen-text-2" style={{ fontSize: 14, maxWidth: 640 }}>
              Walk-forward backtests across 1.13M+ rows of market data.
            </div>
          </div>

          {/* States: loading / error+empty / data */}
          {runs === null && (
            <div className="lumen-card">
              <div
                className="lumen-text-3"
                style={{ padding: 22, textAlign: "center", fontSize: 13 }}
              >
                Loading runs…
              </div>
            </div>
          )}

          {runs !== null && runs.length === 0 && (
            <div className="lumen-card">
              <div
                className="lumen-text-3"
                style={{ padding: 22, textAlign: "center", fontSize: 13 }}
              >
                {error
                  ? "Run registry unavailable. Open /finance for the canonical view."
                  : "No finance runs registered yet."}
              </div>
            </div>
          )}

          {runs !== null && runs.length > 0 && (
            <div className="lumen-card" style={{ overflow: "hidden" }}>
              <table className="lumen-table">
                <thead>
                  <tr>
                    <th>Run</th>
                    <th>Date</th>
                    <th>Symbol</th>
                    <th className="is-right">Hit rate</th>
                    <th className="is-right">Trust score</th>
                    <th className="is-right">Grade</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {runs.map((r) => {
                    const dateStr = (() => {
                      try {
                        return new Date(r.created_at)
                          .toISOString()
                          .slice(0, 10);
                      } catch {
                        return "—";
                      }
                    })();
                    return (
                      <tr
                        key={r.run_id}
                        className="is-link"
                        // navigate via Link wrapped on the first cell;
                        // also let the whole row click via JS for ergonomics.
                        onClick={() => {
                          if (typeof window !== "undefined") {
                            window.location.href = `/finance/${r.run_id}`;
                          }
                        }}
                      >
                        <td className="is-mono" title={r.run_id}>
                          <Link
                            href={`/finance/${r.run_id}`}
                            style={{
                              color: "inherit",
                              textDecoration: "none",
                              borderBottom: "1px dotted var(--ink-4)",
                            }}
                          >
                            {r.run_id.slice(0, 8)}
                          </Link>
                        </td>
                        <td className="is-mono">{dateStr}</td>
                        <td>{readSummary(r, "symbol")}</td>
                        <td className="is-right">
                          {readSummary(r, "hit_rate")}
                        </td>
                        <td className="is-right">
                          {readSummary(r, "trust_score")}
                        </td>
                        <td className="is-right">
                          {readSummary(r, "calibration_grade")}
                        </td>
                        <td>
                          <span
                            className={`lumen-status ${statusClass(r.status)}`}
                          >
                            {r.status || "pending"}
                          </span>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
