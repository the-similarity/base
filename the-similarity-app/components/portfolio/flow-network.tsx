"use client";

import React from "react";

export interface FlowEdge {
  source: string;
  target: string;
  teForward: number;
  teReverse: number;
  netFlow: number;
  direction: "forward" | "reverse";
}

function Bar({ value, maxValue, color }: { value: number; maxValue: number; color: string }) {
  const pct = Math.min((value / maxValue) * 100, 100);
  return (
    <div className="portfolio-flow-bar">
      <div
        className="portfolio-flow-bar__fill"
        style={{ width: `${pct}%`, background: color }}
      />
    </div>
  );
}

export function FlowNetwork({ data }: { data: FlowEdge[] }) {
  const maxTE = Math.max(...data.map((d) => Math.max(d.teForward, d.teReverse)), 0.01);

  return (
    <div className="portfolio-table-wrap">
      <table className="portfolio-table">
        <thead>
          <tr>
            <th className="portfolio-table__th">Source</th>
            <th className="portfolio-table__th">Target</th>
            <th className="portfolio-table__th portfolio-table__th--right">TE Forward</th>
            <th className="portfolio-table__th">
              <span style={{ opacity: 0 }}>bar</span>
            </th>
            <th className="portfolio-table__th portfolio-table__th--right">TE Reverse</th>
            <th className="portfolio-table__th">
              <span style={{ opacity: 0 }}>bar</span>
            </th>
            <th className="portfolio-table__th portfolio-table__th--right">Net Flow</th>
            <th className="portfolio-table__th">Flow</th>
          </tr>
        </thead>
        <tbody>
          {data.map((row) => (
            <tr key={`${row.source}-${row.target}`} className="portfolio-table__row">
              <td className="portfolio-table__td portfolio-table__td--mono">
                {row.source}
              </td>
              <td className="portfolio-table__td portfolio-table__td--mono">
                {row.target}
              </td>
              <td className="portfolio-table__td portfolio-table__td--mono portfolio-table__td--right">
                {row.teForward.toFixed(3)}
              </td>
              <td className="portfolio-table__td portfolio-table__td--bar">
                <Bar value={row.teForward} maxValue={maxTE} color="var(--accent)" />
              </td>
              <td className="portfolio-table__td portfolio-table__td--mono portfolio-table__td--right">
                {row.teReverse.toFixed(3)}
              </td>
              <td className="portfolio-table__td portfolio-table__td--bar">
                <Bar value={row.teReverse} maxValue={maxTE} color="var(--text-muted)" />
              </td>
              <td className="portfolio-table__td portfolio-table__td--mono portfolio-table__td--right">
                <span
                  style={{
                    color:
                      Math.abs(row.netFlow) > 0.05
                        ? row.netFlow > 0
                          ? "var(--positive)"
                          : "var(--negative)"
                        : "var(--text-secondary)",
                    fontWeight: 600,
                  }}
                >
                  {row.netFlow >= 0 ? "+" : ""}
                  {row.netFlow.toFixed(3)}
                </span>
              </td>
              <td className="portfolio-table__td">
                <span className="portfolio-flow-direction">
                  {row.direction === "forward" ? (
                    <>
                      {row.source} <span style={{ color: "var(--accent)" }}>\u2192</span>{" "}
                      {row.target}
                    </>
                  ) : (
                    <>
                      {row.target} <span style={{ color: "var(--accent)" }}>\u2192</span>{" "}
                      {row.source}
                    </>
                  )}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
