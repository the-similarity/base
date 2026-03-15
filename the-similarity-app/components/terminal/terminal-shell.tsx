"use client";
import { useEffect } from "react";
import { useTerminal } from "../../lib/terminal-context";
import { TopBar } from "./top-bar";
import { SearchInput } from "./search-input";
import { ChartPanel } from "./chart-panel";
import { MatchList } from "./match-list";
import { DetailPanel } from "./detail-panel";

export function TerminalShell() {
  const { state, dispatch } = useTerminal();

  // Keyboard shortcuts
  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return;

      switch (e.key) {
        case "ArrowDown":
        case "j":
          e.preventDefault();
          dispatch({ type: "FOCUS_NEXT" });
          break;
        case "ArrowUp":
        case "k":
          e.preventDefault();
          dispatch({ type: "FOCUS_PREV" });
          break;
        case "Enter":
          e.preventDefault();
          dispatch({ type: "SELECT", idx: state.focusedIdx });
          break;
        case "Escape":
          e.preventDefault();
          dispatch({ type: "SELECT", idx: null });
          break;
      }
    }

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [dispatch, state.focusedIdx]);

  return (
    <div className="terminal">
      <TopBar />
      <SearchInput />
      <div className="terminal-body">
        <div className="terminal-left">
          <ChartPanel />
        </div>
        <div className="terminal-right">
          <MatchList />
          {state.selectedIdx !== null && <DetailPanel />}
        </div>
      </div>
    </div>
  );
}
