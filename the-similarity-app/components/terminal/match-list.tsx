"use client";
import { useTerminal } from "../../lib/terminal-context";
import { MatchCard } from "./match-card";

export function MatchList() {
  const { state } = useTerminal();

  return (
    <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" }}>
      <div className="terminal-panel-header" style={{ padding: "0 var(--space-lg)", paddingTop: "var(--space-lg)" }}>
        Matches {state.matches.length > 0 && <span>· {state.matches.length}</span>}
      </div>

      {state.loading && <div className="empty-msg">Searching…</div>}
      {state.error && <div className="empty-msg" style={{ color: "var(--negative)" }}>{state.error}</div>}
      {!state.loading && !state.error && state.matches.length === 0 && (
        <div className="empty-msg">No matches yet.<br />Load data to begin.</div>
      )}

      {state.matches.length > 0 && (
        <div className="match-list">
          {state.matches.map((match, idx) => (
            <MatchCard
              key={`${match.start_idx}-${match.end_idx}`}
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
