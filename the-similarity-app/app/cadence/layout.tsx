"use client";

import { useMemo, useRef, type ReactNode } from "react";
import { EngineProvider, useEngine } from "./_components/engine-context";
import { useParsedNarrative } from "./use-parse";
import { CadenceSidebar, CadenceTopBar, CadencePageIntro } from "./_components/shell";

export default function CadenceLayout({ children }: { children: ReactNode }) {
  const rootRef = useRef<HTMLDivElement>(null);

  return (
    <div ref={rootRef} className="cadence-root">
      <EngineProvider rootRef={rootRef}>
        <div style={{ display: "grid", gridTemplateColumns: "250px minmax(0,1fr)", minHeight: "100vh" }}>
          <CadenceSidebar />
          <main style={{ padding: 22, background: "#EEF2F6" }}>
            <CadenceTopBar />
            <CadencePageIntro />
            {children}
          </main>
        </div>
        <ComposerHost />
      </EngineProvider>

      <style>{`
        .cadence-root {
          --cad-line: #D7DEE7;
          --cad-muted: #6B7280;
          color: #0F172A;
          background: #EEF2F6;
          height: 100vh;
          overflow: auto;
          font-family: Inter, system-ui, -apple-system, Segoe UI, Roboto, sans-serif;
        }
        .cadence-root * { box-sizing: border-box; }
        .cadence-root button { border: none; font: inherit; cursor: pointer; }
        .cadence-root textarea, .cadence-root input { font: inherit; }
      `}</style>
    </div>
  );
}

function ComposerHost() {
  const { composerOpen, closeComposer, readOnlyEntry, text, setText, persistEntry } = useEngine();
  const { events, series } = useParsedNarrative(text);
  const avg = useMemo(() => Math.round(series.reduce((s, p) => s + p.v, 0) / (series.length || 1)), [series]);

  if (!composerOpen) return null;

  const readOnly = Boolean(readOnlyEntry);
  const value = readOnly ? readOnlyEntry?.text ?? "" : text;

  return (
    <div style={{ position: "fixed", inset: 0, background: "rgba(15,23,42,0.35)", display: "grid", placeItems: "center", zIndex: 50 }}>
      <div style={{ width: "min(820px, 92vw)", background: "#F8FAFC", borderRadius: 16, border: "1px solid #D7DEE7", padding: 18 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
          <h3 style={{ margin: 0 }}>{readOnly ? "Body log details" : "New body log"}</h3>
          <button onClick={closeComposer} style={{ background: "transparent", color: "#6B7280" }}>Close</button>
        </div>
        <textarea
          value={value}
          onChange={(e) => setText(e.target.value)}
          readOnly={readOnly}
          placeholder="Examples: late meal, alcohol 2 drinks, long run, travel day, poor sleep..."
          style={{ width: "100%", minHeight: 170, borderRadius: 12, border: "1px solid #CBD5E1", padding: 12, resize: "vertical", background: readOnly ? "#F1F5F9" : "#FFF" }}
        />
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: 10 }}>
          <div style={{ fontSize: 12, color: "#64748B" }}>{events.length} events · recovery score {avg}</div>
          {!readOnly ? (
            <button
              onClick={() => persistEntry({ text, events, series, avg })}
              style={{ background: "#0F172A", color: "#F8FAFC", padding: "8px 14px", borderRadius: 8, fontWeight: 600 }}
            >
              Save log
            </button>
          ) : null}
        </div>
      </div>
    </div>
  );
}
