"use client";
import { useEffect } from "react";
import { useTerminal } from "../../lib/terminal-context";
import { getDashboardData } from "../../lib/api";

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
          // Use top matches from dashboard data as initial match list
          if (data.topMatches && data.topMatches.length > 0) {
            dispatch({ type: "SET_MATCHES", matches: data.topMatches });
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
