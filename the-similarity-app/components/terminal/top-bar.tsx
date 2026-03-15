"use client";
import { useTerminal } from "../../lib/terminal-context";
import { METHOD_LABELS, METHODS } from "../../lib/constants";

export function TopBar() {
  const { state, dispatch } = useTerminal();

  return (
    <div className="terminal-topbar">
      <span className="terminal-topbar-logo">THE SIMILARITY</span>
      <div className="terminal-topbar-sep" />

      <div style={{ display: "flex", alignItems: "center", gap: "var(--space-sm)" }}>
        <span className={`status-dot ${state.loading ? "status-dot--loading" : state.error ? "status-dot--error" : "status-dot--live"}`} />
        <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--text-secondary)" }}>
          {state.loading ? "searching…" : state.error ? "error" : `${state.matches.length} matches`}
        </span>
      </div>

      <div className="terminal-topbar-sep" />

      <div className="config-pills">
        {METHODS.map((method) => (
          <button
            key={method}
            className="config-pill"
            data-active={state.activeMethods.includes(method)}
            onClick={() => dispatch({ type: "TOGGLE_METHOD", method })}
          >
            {METHOD_LABELS[method] || method}
          </button>
        ))}
      </div>

      <div style={{ marginLeft: "auto", display: "flex", gap: "var(--space-md)", alignItems: "center" }}>
        <span style={{ display: "flex", gap: 6, alignItems: "center", color: "var(--text-muted)", fontSize: 10 }}>
          <span className="kbd">↑↓</span>nav
          <span className="kbd">⏎</span>select
          <span className="kbd">esc</span>clear
        </span>
        <button className="theme-toggle" onClick={() => dispatch({ type: "TOGGLE_THEME" })}>
          {state.theme === "dark" ? "☀" : "☽"}
        </button>
      </div>
    </div>
  );
}
