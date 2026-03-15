"use client";
import { useTerminal } from "@/lib/terminal-context";
import { MatchCard } from "./match-card";

export function MatchList() {
  const { state } = useTerminal();

  if (state.loading) {
    return (
      <div className="terminal-panel" style={{ flex: 1 }}>
        <div className="terminal-panel-header">Matches</div>
        <div
          style={{
            color: "var(--text-muted)",
            fontFamily: "var(--font-mono)",
            fontSize: 12,
            padding: "var(--space-xl)",
          }}
        >
          Searching...
        </div>
      </div>
    );
  }

  if (state.error) {
    return (
      <div className="terminal-panel" style={{ flex: 1 }}>
        <div className="terminal-panel-header">Matches</div>
        <div
          style={{
            color: "var(--negative)",
            fontFamily: "var(--font-mono)",
            fontSize: 12,
            padding: "var(--space-xl)",
          }}
        >
          {state.error}
        </div>
      </div>
    );
  }

  if (state.matches.length === 0) {
    return (
      <div className="terminal-panel" style={{ flex: 1 }}>
        <div className="terminal-panel-header">Matches</div>
        <div
          style={{
            color: "var(--text-muted)",
            fontFamily: "var(--font-mono)",
            fontSize: 12,
            padding: "var(--space-xl)",
            textAlign: "center",
          }}
        >
          No matches yet. Load data to begin.
        </div>
      </div>
    );
  }

  return (
    <div
      className="terminal-panel"
      style={{ flex: 1, display: "flex", flexDirection: "column" }}
    >
      <div className="terminal-panel-header">
        Matches &middot; {state.matches.length} results
      </div>
      <div className="match-list">
        {state.matches.map((match, idx) => (
          <MatchCard
            key={`${match.startIdx}-${match.endIdx}`}
            match={match}
            rank={idx + 1}
            idx={idx}
          />
        ))}
      </div>
    </div>
  );
}
