"use client";

import { useEngine } from "../_components/engine-context";
import { Panel } from "../_components/shell";

export default function ThreadPage() {
  const { entries, openReadOnly } = useEngine();

  return (
    <Panel title="Longitudinal thread" subtitle="All body logs, newest first.">
      <div style={{ display: "grid", gap: 10 }}>
        {entries.length === 0 ? <p style={{ color: "#64748B" }}>No logs yet. Start with a demo seed or new body note.</p> : null}
        {entries.map((entry) => (
          <button key={entry.id} onClick={() => openReadOnly(entry)} style={{ textAlign: "left", background: "white", border: "1px solid #D7DEE7", borderRadius: 12, padding: 12 }}>
            <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12, color: "#64748B" }}>
              <span>{new Date(entry.createdAt).toLocaleString()}</span>
              <span>Recovery {Math.round(entry.avg)}</span>
            </div>
            <div style={{ marginTop: 6, color: "#334155" }}>{entry.text.slice(0, 180)}</div>
          </button>
        ))}
      </div>
    </Panel>
  );
}
