"use client";
import { useRef, useEffect } from "react";
import { useTerminal } from "../../lib/terminal-context";
import { ScoreBar } from "./score-bar";
import { Sparkline } from "./sparkline";
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

  // Resolve dates from OHLC data using indices, fall back to raw indices
  const ohlcDates = state.ohlcData?.dates;
  let window: string;
  if (match.startDate && match.endDate) {
    window = `${match.startDate.slice(0, 10)} → ${match.endDate.slice(0, 10)}`;
  } else if (ohlcDates && ohlcDates[match.startIdx] && ohlcDates[match.endIdx]) {
    window = `${ohlcDates[match.startIdx].slice(0, 10)} → ${ohlcDates[match.endIdx].slice(0, 10)}`;
  } else {
    window = `[${match.startIdx}–${match.endIdx}]`;
  }

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
      <span className="match-card-score">{match.confidenceScore.toFixed(1)}</span>
      {match.matchedSeries && match.matchedSeries.length > 2 ? (
        <span className="match-card-sparkline">
          <Sparkline data={match.matchedSeries} width={60} height={18} />
        </span>
      ) : (
        <span style={{ flex: 1, fontSize: 11, color: "var(--text-secondary)" }}>{window}</span>
      )}
      <span className="match-card-bar">
        <ScoreBar breakdown={match.scoreBreakdown} />
      </span>
      <span style={{
        fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--text-muted)",
      }}>
        {window}
      </span>
    </div>
  );
}
