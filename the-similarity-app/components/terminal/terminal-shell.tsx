"use client";
import { useEffect } from "react";
import { useTerminal } from "../../lib/terminal-context";
import { SplitPane } from "../ui/split-pane";
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

  const rightPane = state.selectedIdx !== null ? (
    <SplitPane
      direction="vertical"
      defaultRatio={0.55}
      minRatio={0.2}
      maxRatio={0.8}
      first={<MatchList />}
      second={<DetailPanel />}
    />
  ) : (
    <MatchList />
  );

  return (
    <div className="terminal">
      <TopBar />
      <SearchInput />
      <SplitPane
        direction="horizontal"
        defaultRatio={0.6}
        minRatio={0.25}
        maxRatio={0.8}
        first={<ChartPanel />}
        second={rightPane}
        className="terminal-body"
      />
    </div>
  );
}
