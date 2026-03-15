"use client";
import { useTerminal } from "../../lib/terminal-context";

const METHOD_LABELS: Record<string, string> = {
  dtw: "DTW",
  pearson_warped: "Pearson",
  bempedelis_r2: "Bemp R\u00B2",
  bempedelis_smoothness: "Bemp Smooth",
  koopman: "Koopman",
  wavelet_spectrum: "Wavelet",
  emd: "EMD",
  tda: "TDA",
  transfer_entropy: "TE",
};

const ALL_METHODS = Object.keys(METHOD_LABELS);

export function TopBar() {
  const { state, dispatch } = useTerminal();

  return (
    <div className="terminal-topbar">
      <span className="terminal-topbar-logo">THE SIMILARITY</span>
      <div className="terminal-topbar-separator" />

      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: "var(--space-sm)",
        }}
      >
        <span
          className={`status-dot ${state.loading ? "status-dot--loading" : state.error ? "status-dot--error" : "status-dot--live"}`}
        />
        <span
          style={{
            fontFamily: "var(--font-mono)",
            fontSize: 11,
            color: "var(--text-secondary)",
          }}
        >
          {state.loading
            ? "searching..."
            : state.error
              ? "error"
              : `${state.matches.length} matches`}
        </span>
      </div>

      <div className="terminal-topbar-separator" />

      <div className="config-pills">
        {ALL_METHODS.map((method) => (
          <button
            key={method}
            className="config-pill"
            data-active={state.activeMethods.includes(method)}
            onClick={() => dispatch({ type: "TOGGLE_METHOD", method })}
          >
            {METHOD_LABELS[method]}
          </button>
        ))}
      </div>

      <div
        style={{
          marginLeft: "auto",
          display: "flex",
          gap: "var(--space-md)",
          alignItems: "center",
        }}
      >
        <span
          style={{
            display: "flex",
            gap: "var(--space-xs)",
            alignItems: "center",
            color: "var(--text-muted)",
            fontSize: 11,
          }}
        >
          <span className="kbd">&uarr;&darr;</span> navigate
          <span className="kbd">&crarr;</span> select
          <span className="kbd">esc</span> clear
          <span className="kbd">/</span> search
        </span>
        <button
          onClick={() => dispatch({ type: "TOGGLE_THEME" })}
          style={{
            background: "none",
            border: "1px solid var(--border)",
            borderRadius: "var(--radius-sm)",
            color: "var(--text-secondary)",
            padding: "2px 8px",
            cursor: "pointer",
            fontSize: 11,
            fontFamily: "var(--font-mono)",
          }}
        >
          {state.theme === "dark" ? "\u2600" : "\u263D"}
        </button>
      </div>
    </div>
  );
}
