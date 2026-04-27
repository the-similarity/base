"use client";

import { useMemo } from "react";
import { useEngine } from "../_components/engine-context";
import { Panel } from "../_components/shell";

export default function TagsPage() {
  const { entries } = useEngine();
  const rows = useMemo(() => {
    const map = new Map<string, number>();
    for (const e of entries) {
      for (const ev of e.events) map.set(ev.tag, (map.get(ev.tag) ?? 0) + 1);
    }
    return [...map.entries()].sort((a, b) => b[1] - a[1]);
  }, [entries]);

  return (
    <Panel title="Context tags" subtitle="travel · illness · fasting · hard training · jet lag">
      {rows.length === 0 ? <p style={{ color: "#64748B" }}>No context tags yet. Add a manual body note from Today.</p> : null}
      <div style={{ display: "grid", gap: 8 }}>
        {rows.map(([tag, count]) => (
          <div key={tag} style={{ display: "flex", justifyContent: "space-between", background: "white", border: "1px solid #D7DEE7", borderRadius: 10, padding: "8px 10px" }}>
            <span>{tag}</span>
            <strong>{count}</strong>
          </div>
        ))}
      </div>
    </Panel>
  );
}
