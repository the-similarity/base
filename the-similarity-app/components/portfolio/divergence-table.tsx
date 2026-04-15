"use client";

import React, { useState, useMemo } from "react";

export interface DivergencePair {
  assetA: string;
  assetB: string;
  historicalCorr: number;
  recentCorr: number;
  divergenceScore: number;
  direction: "decorrelating" | "recorrelating";
}

type SortKey = keyof DivergencePair;

const columns: { key: SortKey; label: string; align?: "right" }[] = [
  { key: "assetA", label: "Asset A" },
  { key: "assetB", label: "Asset B" },
  { key: "historicalCorr", label: "Hist Corr", align: "right" },
  { key: "recentCorr", label: "Recent Corr", align: "right" },
  { key: "divergenceScore", label: "Divergence", align: "right" },
  { key: "direction", label: "Direction" },
];

export function DivergenceTable({ data }: { data: DivergencePair[] }) {
  const [sortKey, setSortKey] = useState<SortKey>("divergenceScore");
  const [sortAsc, setSortAsc] = useState(false);

  const sorted = useMemo(() => {
    const copy = [...data];
    copy.sort((a, b) => {
      const av = a[sortKey];
      const bv = b[sortKey];
      if (typeof av === "number" && typeof bv === "number") {
        return sortAsc ? av - bv : bv - av;
      }
      return sortAsc
        ? String(av).localeCompare(String(bv))
        : String(bv).localeCompare(String(av));
    });
    return copy;
  }, [data, sortKey, sortAsc]);

  function handleSort(key: SortKey) {
    if (key === sortKey) {
      setSortAsc(!sortAsc);
    } else {
      setSortKey(key);
      setSortAsc(false);
    }
  }

  return (
    <div className="portfolio-table-wrap">
      <table className="portfolio-table">
        <thead>
          <tr>
            {columns.map((col) => (
              <th
                key={col.key}
                className={`portfolio-table__th ${col.align === "right" ? "portfolio-table__th--right" : ""}`}
                onClick={() => handleSort(col.key)}
              >
                {col.label}
                {sortKey === col.key && (
                  <span className="portfolio-table__sort-arrow">
                    {sortAsc ? " \u25B2" : " \u25BC"}
                  </span>
                )}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {sorted.map((row, i) => (
            <tr key={`${row.assetA}-${row.assetB}`} className="portfolio-table__row">
              <td className="portfolio-table__td">{row.assetA}</td>
              <td className="portfolio-table__td">{row.assetB}</td>
              <td className="portfolio-table__td portfolio-table__td--mono portfolio-table__td--right">
                {row.historicalCorr.toFixed(2)}
              </td>
              <td className="portfolio-table__td portfolio-table__td--mono portfolio-table__td--right">
                {row.recentCorr.toFixed(2)}
              </td>
              <td className="portfolio-table__td portfolio-table__td--mono portfolio-table__td--right">
                <span
                  style={{
                    // Editorial ramp: strong negative ink for high divergence,
                    // primary text for mid, muted for low. No amber hue.
                    color:
                      row.divergenceScore > 0.3
                        ? "var(--negative)"
                        : row.divergenceScore > 0.15
                          ? "var(--text-primary)"
                          : "var(--text-muted)",
                    fontWeight: 600,
                  }}
                >
                  {row.divergenceScore.toFixed(2)}
                </span>
              </td>
              <td className="portfolio-table__td">
                <span
                  className="portfolio-direction-badge"
                  style={{
                    color:
                      row.direction === "decorrelating"
                        ? "var(--negative)"
                        : "var(--positive)",
                    borderColor:
                      row.direction === "decorrelating"
                        ? "var(--negative)"
                        : "var(--positive)",
                    background:
                      row.direction === "decorrelating"
                        ? "var(--negative-dim)"
                        : "var(--positive-dim)",
                  }}
                >
                  {row.direction === "decorrelating" ? "\u2197" : "\u2199"}{" "}
                  {row.direction}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
