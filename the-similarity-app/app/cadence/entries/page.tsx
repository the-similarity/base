"use client";

import { useEngine } from "../_components/engine-context";
import { Panel } from "../_components/shell";

export default function EntriesPage() {
  const { entries, exportEntries, openComposer } = useEngine();

  return (
    <div style={{ display: "grid", gap: 12 }}>
      <Panel title="Ingestion log" subtitle="Data source and manual compose status.">
        <div style={{ display: "flex", gap: 8, marginBottom: 12 }}>
          <button style={{ background: "#0F172A", color: "white", borderRadius: 8, padding: "7px 11px" }} onClick={openComposer}>+ Manual body log</button>
          <button style={{ background: "#E2E8F0", borderRadius: 8, padding: "7px 11px" }} onClick={exportEntries}>Export JSON</button>
        </div>
        <ul style={{ margin: 0, paddingLeft: 18, color: "#475569" }}>
          <li>Apple Health — planned connector UI (OAuth) for v1.1</li>
          <li>Whoop / Oura / Garmin — planned connector adapters</li>
          <li>CGM + lab upload — planned CSV/PDF ingestion flow</li>
          <li>Local-first storage active now</li>
        </ul>
      </Panel>

      <Panel title="Raw entry count" subtitle="Current local dataset footprint.">
        <div style={{ fontSize: 34, fontWeight: 700 }}>{entries.length}</div>
      </Panel>
    </div>
  );
}
