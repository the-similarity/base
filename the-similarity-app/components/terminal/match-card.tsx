"use client";
import { useRef, useEffect } from "react";
import { useTerminal } from "../../lib/terminal-context";
import { Sparkline } from "./sparkline";
import { ScoreBar } from "./score-bar";
import type { MatchResult } from "../../lib/types";

interface MatchCardProps {
  match: MatchResult;
  rank: number;
  idx: number;
}

export function MatchCard({ match, rank, idx }: MatchCardProps) {
  const { state, dispatch } = useTerminal();
  const ref = useRef<HTMLDivElement>(null);
  const isSelected = state.selectedIdx === idx;
  const isHighlighted = state.hoveredIdx === idx;
  const isFocused = state.focusedIdx === idx;

  // Auto-scroll focused card into view
  useEffect(() => {
    if (isFocused && ref.current) {
      ref.current.scrollIntoView({ block: "nearest", behavior: "smooth" });
    }
  }, [isFocused]);

  return (
    <div
      ref={ref}
      className="match-card"
      data-selected={isSelected || undefined}
      data-highlighted={isHighlighted || isFocused || undefined}
      onClick={() => dispatch({ type: "SELECT", idx })}
      onMouseEnter={() => dispatch({ type: "HOVER", idx })}
      onMouseLeave={() => dispatch({ type: "HOVER", idx: null })}
    >
      <span className="match-card-rank">#{rank}</span>
      <span className="match-card-score">
        {match.confidenceScore.toFixed(1)}
      </span>
      <div className="match-card-sparkline">
        <Sparkline data={match.matchedSeries || []} height={24} />
      </div>
      <div style={{ flex: 1, minWidth: 80 }}>
        <ScoreBar breakdown={match.scoreBreakdown} />
      </div>
      <span className="match-card-meta">
        {match.startDate ? `${match.startDate}` : `idx ${match.startIdx}`}
      </span>
    </div>
  );
}
