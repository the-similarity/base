"use client";
import { useRef, useEffect } from "react";
import { useTerminal } from "../../lib/terminal-context";
import type { MatchCard as MatchCardType } from "../../lib/types";

interface Props {
  match: MatchCardType;
  rank: number;
  idx: number;
}

export function MatchCard({ match, rank, idx }: Props) {
  const { state, dispatch } = useTerminal();
  const ref = useRef<HTMLDivElement>(null);
  const isSelected = state.selectedIdx === idx;
  const isHighlighted = state.hoveredIdx === idx || state.focusedIdx === idx;

  useEffect(() => {
    if (state.focusedIdx === idx && ref.current) {
      ref.current.scrollIntoView({ block: "nearest", behavior: "smooth" });
    }
  }, [state.focusedIdx, idx]);

  const deltaClass = match.delta > 0 ? "positive" : match.delta < 0 ? "negative" : "";
  const deltaSign = match.delta > 0 ? "+" : "";

  return (
    <div
      ref={ref}
      className="match-card"
      data-selected={isSelected}
      data-highlighted={isHighlighted}
      onClick={() => dispatch({ type: "SELECT", idx })}
      onMouseEnter={() => dispatch({ type: "HOVER", idx })}
      onMouseLeave={() => dispatch({ type: "HOVER", idx: null })}
    >
      <span className="match-card-rank">{rank}</span>
      <span className="match-card-score">{match.score.toFixed(1)}</span>
      <span style={{ flex: 1, fontSize: 11, color: "var(--text-secondary)" }}>{match.label}</span>
      <span className="match-card-meta">{match.method}</span>
      <span className="match-card-regime">{match.regime}</span>
      <span style={{
        fontFamily: "var(--font-mono)", fontSize: 10, fontWeight: 600,
        color: deltaClass === "positive" ? "var(--positive)" : deltaClass === "negative" ? "var(--negative)" : "var(--text-muted)",
      }}>
        {deltaSign}{match.delta.toFixed(1)}%
      </span>
    </div>
  );
}
