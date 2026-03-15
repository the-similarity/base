"use client";
import { useEffect } from "react";
import { useTerminal } from "../../lib/terminal-context";
import { getDashboardData } from "../../lib/api";

export function TerminalDataLoader() {
  const { dispatch } = useTerminal();

  useEffect(() => {
    let cancelled = false;

    async function load() {
      dispatch({ type: "SET_LOADING", loading: true });
      try {
        const data = await getDashboardData();
        if (cancelled) return;
        dispatch({ type: "SET_DASHBOARD", data });
        dispatch({ type: "SET_LOADING", loading: false });
      } catch (err) {
        if (cancelled) return;
        dispatch({
          type: "SET_ERROR",
          error: err instanceof Error ? err.message : "Failed to load data",
        });
      }
    }

    load();
    return () => {
      cancelled = true;
    };
  }, [dispatch]);

  return null;
}
