"use client";
import { useEffect } from "react";
import { useTerminal } from "../../lib/terminal-context";
import { getDashboardData } from "../../lib/api";
import type { MatchResult } from "../../lib/types";

/** Convert dashboard MatchCard items into MatchResult shape for unified rendering. */
function matchCardsToResults(cards: { label: string; window: string; score: number; delta: number; method: string; regime: string }[]): MatchResult[] {
  return cards.map((card, i) => ({
    startIdx: 0,
    endIdx: 0,
    startDate: card.window.split(" -> ")[0] || null,
    endDate: card.window.split(" -> ")[1] || null,
    confidenceScore: card.score,
    scoreBreakdown: {
      bempedelisR2: 0, bempedelisSmoothness: 0, koopman: 0,
      waveletSpectrum: 0, emd: 0, tda: 0, dtw: 0, pearsonWarped: 0, transferEntropy: 0,
    },
    matchedSeries: null,
    transformAlpha: null,
    transformBeta: null,
    transformR2: 0,
    koopmanEigenvalues: null,
    fractalSpectrum: null,
    persistenceDiagram: null,
    forwardWindow: null,
  }));
}

export function DataLoader() {
  const { dispatch } = useTerminal();

  useEffect(() => {
    let cancelled = false;

    async function load() {
      dispatch({ type: "SET_LOADING", loading: true });
      try {
        const data = await getDashboardData();
        if (!cancelled) {
          dispatch({ type: "SET_DASHBOARD", data });
          if (data.topMatches && data.topMatches.length > 0) {
            dispatch({ type: "SET_MATCHES", matches: matchCardsToResults(data.topMatches) });
          } else {
            dispatch({ type: "SET_LOADING", loading: false });
          }
        }
      } catch (err) {
        if (!cancelled) {
          dispatch({ type: "SET_ERROR", error: String(err) });
        }
      }
    }

    load();
    return () => { cancelled = true; };
  }, [dispatch]);

  return null;
}
