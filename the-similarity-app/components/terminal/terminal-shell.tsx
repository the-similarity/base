"use client";
import { useEffect } from "react";
import { useTerminal } from "@/lib/terminal-context";
import { TopBar } from "./top-bar";
import { ChartPanel } from "./chart-panel";
import { MatchList } from "./match-list";
import { DetailPanel } from "./detail-panel";

export function TerminalShell() {
  const { state, dispatch } = useTerminal();

  // Apply theme to document
  useEffect(() => {
    document.documentElement.setAttribute("data-theme", state.theme);
  }, [state.theme]);

  // Keyboard shortcuts
  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      // Don't capture when typing in an input
      if (
        e.target instanceof HTMLInputElement ||
        e.target instanceof HTMLTextAreaElement
      )
        return;

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
        case "/":
          e.preventDefault();
          document
            .querySelector<HTMLInputElement>("[data-search-input]")
            ?.focus();
          break;
      }
    }

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [dispatch, state.focusedIdx]);

  return (
    <div className="terminal">
      <TopBar />
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
