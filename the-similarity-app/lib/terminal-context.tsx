"use client";
import { createContext, useContext, useReducer, useEffect, type ReactNode } from "react";
import type { MatchResult, DashboardData, SearchResponse } from "./types";

export interface TerminalState {
  matches: MatchResult[];
  searchResponse: SearchResponse | null;
  dashboardData: DashboardData | null;
  loading: boolean;
  error: string | null;
  selectedIdx: number | null;
  hoveredIdx: number | null;
  focusedIdx: number;
  activeMethods: string[];
  theme: "dark" | "light";
}

export type Action =
  | { type: "SET_MATCHES"; matches: MatchResult[] }
  | { type: "SET_SEARCH_RESPONSE"; response: SearchResponse }
  | { type: "SET_DASHBOARD"; data: DashboardData }
  | { type: "SET_LOADING"; loading: boolean }
  | { type: "SET_ERROR"; error: string | null }
  | { type: "SELECT"; idx: number | null }
  | { type: "HOVER"; idx: number | null }
  | { type: "FOCUS"; idx: number }
  | { type: "FOCUS_NEXT" }
  | { type: "FOCUS_PREV" }
  | { type: "TOGGLE_METHOD"; method: string }
  | { type: "TOGGLE_THEME" };

const initialState: TerminalState = {
  matches: [],
  searchResponse: null,
  dashboardData: null,
  loading: false,
  error: null,
  selectedIdx: null,
  hoveredIdx: null,
  focusedIdx: 0,
  activeMethods: [
    "dtw", "pearson_warped", "bempedelis_r2", "bempedelis_smoothness",
    "koopman", "wavelet_spectrum", "emd", "tda", "transfer_entropy",
  ],
  theme: "dark",
};

export function reducer(state: TerminalState, action: Action): TerminalState {
  switch (action.type) {
    case "SET_MATCHES":
      return { ...state, matches: action.matches, loading: false, error: null };
    case "SET_SEARCH_RESPONSE":
      return {
        ...state,
        searchResponse: action.response,
        matches: action.response.matches,
        loading: false,
        error: null,
        selectedIdx: null,
        hoveredIdx: null,
        focusedIdx: 0,
      };
    case "SET_DASHBOARD":
      return { ...state, dashboardData: action.data };
    case "SET_LOADING":
      return { ...state, loading: action.loading };
    case "SET_ERROR":
      return { ...state, error: action.error, loading: false };
    case "SELECT":
      return { ...state, selectedIdx: action.idx };
    case "HOVER":
      return { ...state, hoveredIdx: action.idx };
    case "FOCUS":
      return { ...state, focusedIdx: action.idx };
    case "FOCUS_NEXT":
      return {
        ...state,
        focusedIdx: Math.min(state.focusedIdx + 1, Math.max(0, state.matches.length - 1)),
      };
    case "FOCUS_PREV":
      return { ...state, focusedIdx: Math.max(state.focusedIdx - 1, 0) };
    case "TOGGLE_METHOD": {
      const methods = state.activeMethods.includes(action.method)
        ? state.activeMethods.filter((m) => m !== action.method)
        : [...state.activeMethods, action.method];
      return { ...state, activeMethods: methods };
    }
    case "TOGGLE_THEME":
      return { ...state, theme: state.theme === "dark" ? "light" : "dark" };
    default:
      return state;
  }
}

const TerminalContext = createContext<{
  state: TerminalState;
  dispatch: React.Dispatch<Action>;
} | null>(null);

export function TerminalProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(reducer, initialState);

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", state.theme);
  }, [state.theme]);

  return (
    <TerminalContext.Provider value={{ state, dispatch }}>
      {children}
    </TerminalContext.Provider>
  );
}

export function useTerminal() {
  const ctx = useContext(TerminalContext);
  if (!ctx) throw new Error("useTerminal must be used within TerminalProvider");
  return ctx;
}
