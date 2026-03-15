"use client";
import { useRef, useEffect } from "react";
import { useTerminal } from "../../lib/terminal-context";
import { Sparkline } from "./sparkline";
import { ScoreBar } from "./score-bar";
import type { MatchResult } from "../../lib/types";

interface Props {
  match: MatchResult;
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
      <span className="match-card-score">{match.confidence_score.toFixed(1)}</span>
      <div className="match-card-sparkline">
        <Sparkline data={match.matched_series || []} height={20} width={70} />
      </div>
      <div className="match-card-bar">
        <ScoreBar breakdown={match.score_breakdown} />
      </div>
      <span className="match-card-meta">
        {match.start_date || `${match.start_idx}–${match.end_idx}`}
      </span>
      {match.regime && <span className="match-card-regime">{match.regime}</span>}
    </div>
  );
}
