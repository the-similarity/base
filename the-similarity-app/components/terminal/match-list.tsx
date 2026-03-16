"use client";
import { useTerminal } from "../../lib/terminal-context";
import { MatchCard } from "./match-card";

export function MatchList() {
  const { state, dispatch } = useTerminal();
  const hasMatches = state.matches.length > 0;

  return (
    <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" }}>
      <div className="terminal-panel-header" style={{ padding: "0 var(--space-lg)", paddingTop: "var(--space-lg)", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <span>Matches {hasMatches && <span>· {state.matches.length}</span>}</span>
        {hasMatches && (
          <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 10, color: "var(--text-muted)", fontFamily: "var(--font-mono)" }}>
            Fwd
            <input
              type="range"
              className="search-bar-range"
              style={{ width: 60 }}
              min={5}
              max={200}
              step={5}
              value={state.forwardBars}
              onChange={(e) => dispatch({ type: "SET_FORWARD_BARS", bars: Number(e.target.value) })}
            />
            <span style={{ minWidth: 20, textAlign: "right" }}>{state.forwardBars}</span>
          </label>
        )}
      </div>

      {state.loading && <div className="empty-msg">Searching…</div>}
      {state.error && <div className="empty-msg" style={{ color: "var(--negative)" }}>{state.error}</div>}
      {!state.loading && !state.error && state.matches.length === 0 && (
        <div className="empty-msg">No matches yet.<br />Open search to begin.</div>
      )}

      {state.matches.length > 0 && (
        <div className="match-list">
          {state.matches.map((match, idx) => (
            <MatchCard
              key={`${match.startIdx}-${match.endIdx}-${idx}`}
              match={match}
              rank={idx + 1}
              idx={idx}
            />
          ))}
        </div>
      )}
    </div>
  );
}
