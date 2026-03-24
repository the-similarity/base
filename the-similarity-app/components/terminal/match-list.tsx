"use client";
import { useTerminal } from "../../lib/terminal-context";
import { MatchCard } from "./match-card";

function SkeletonCards() {
  return (
    <div className="match-list">
      {[0, 1, 2, 3].map((i) => (
        <div key={i} className="skeleton-card">
          <div className="skeleton skeleton-rank" />
          <div className="skeleton skeleton-score" />
          <div className="skeleton skeleton-bar" />
          <div className="skeleton skeleton-meta" />
        </div>
      ))}
    </div>
  );
}

function EmptyState() {
  return (
    <div className="match-list-empty">
      <div className="match-list-empty__art">
        <pre className="match-list-empty__ascii">{`
    .---.
   /     \\
  | () () |
   \\  ^  /
    '---'
   /|   |\\
  / |   | \\
`}</pre>
      </div>
      <div className="match-list-empty__text">
        Select a dataset and run search
      </div>
      <div className="match-list-empty__hint">
        Choose from the sidebar, then click <span className="kbd">Run search</span>
      </div>
    </div>
  );
}

export function MatchList() {
  const { state, dispatch } = useTerminal();
  const hasMatches = state.matches.length > 0;

  const handleRetry = () => {
    dispatch({ type: "SET_ERROR", error: null });
  };

  return (
    <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" }}>
      <div className="terminal-panel-header" style={{ padding: "0 var(--space-lg)", paddingTop: "var(--space-lg)", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <span>Matches {hasMatches && <span>&middot; {state.matches.length}</span>}</span>
        {hasMatches && (
          <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 10, color: "var(--text-muted)", fontFamily: "var(--font-mono)" }}>
            Fwd
            <input
              type="range"
              className="search-bar-range"
              style={{ width: 140 }}
              min={5}
              max={500}
              step={5}
              value={Math.min(state.forwardBars, 500)}
              onChange={(e) => dispatch({ type: "SET_FORWARD_BARS", bars: Number(e.target.value) })}
            />
            <input
              type="number"
              className="fwd-number-input"
              min={5}
              step={5}
              value={state.forwardBars}
              onChange={(e) => {
                const v = Math.max(5, Number(e.target.value) || 5);
                dispatch({ type: "SET_FORWARD_BARS", bars: v });
              }}
            />
          </label>
        )}
      </div>

      {state.loading && <SkeletonCards />}

      {!state.loading && state.error && (
        <div className="match-list-error">
          <div className="match-list-error__icon">!</div>
          <div className="match-list-error__text">{state.error}</div>
          <button
            type="button"
            className="match-list-error__retry"
            onClick={handleRetry}
          >
            Dismiss
          </button>
        </div>
      )}

      {!state.loading && !state.error && state.matches.length === 0 && <EmptyState />}

      {state.matches.length > 0 && !state.loading && (
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
