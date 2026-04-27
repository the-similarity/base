"use client";

/**
 * ThemeToggle — a small icon button that flips the document's data-theme
 * between "light" and "dark". Persists the choice in localStorage under
 * the same `ts-settings` key the workstation uses, so toggling here
 * carries over when the user navigates into /workstation.
 *
 * Renders as a `.nav__iconbtn` so it picks up the existing marquee-cluster
 * styling (same size / border / hover as the search and account buttons).
 *
 * Hydration-safe: on first render we can't know the stored theme (the
 * initialiser runs on the client only), so the button starts in a neutral
 * "light" state and immediately corrects after mount. We intentionally
 * don't render nothing-until-mounted because that causes layout jitter in
 * the marquee; a one-frame icon flip is invisible in practice.
 */

import { useEffect, useState } from "react";

type Theme = "light" | "dark";

const SETTINGS_KEY = "ts-settings";

/** Read the stored theme from localStorage, falling back to "light". Safe
 *  to call on the server — returns "light" there. */
function readStoredTheme(): Theme {
  if (typeof window === "undefined") return "light";
  try {
    const raw = localStorage.getItem(SETTINGS_KEY);
    if (!raw) return "light";
    const parsed = JSON.parse(raw) as { theme?: Theme } | null;
    return parsed?.theme === "dark" ? "dark" : "light";
  } catch {
    return "light";
  }
}

/** Write the theme back into the same `ts-settings` blob the workstation
 *  owns, preserving any other fields already there. */
function writeStoredTheme(theme: Theme) {
  if (typeof window === "undefined") return;
  try {
    const raw = localStorage.getItem(SETTINGS_KEY);
    const parsed = raw ? (JSON.parse(raw) as Record<string, unknown>) : {};
    localStorage.setItem(SETTINGS_KEY, JSON.stringify({ ...parsed, theme }));
  } catch {
    // localStorage unavailable (private-mode Safari, disk full) — the
    // toggle still flips the live DOM, just doesn't persist. Silent
    // fallback is fine; the user can always click again.
  }
}

export function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>("light");

  // On mount, read the stored theme AND reflect whatever data-theme the
  // document already has (the workstation may have set it before us).
  useEffect(() => {
    const docTheme = (document.documentElement.getAttribute("data-theme") as Theme | null) ?? null;
    const next = docTheme === "dark" || docTheme === "light" ? docTheme : readStoredTheme();
    setTheme(next);
    // Sync document + body background so a fresh mount with stored dark
    // doesn't flash light for one frame.
    document.documentElement.setAttribute("data-theme", next);
    document.documentElement.style.background = next === "dark" ? "#0e0d0b" : "#faf9f6";
  }, []);

  const toggle = () => {
    const next: Theme = theme === "dark" ? "light" : "dark";
    setTheme(next);
    document.documentElement.setAttribute("data-theme", next);
    document.documentElement.style.background = next === "dark" ? "#0e0d0b" : "#faf9f6";
    writeStoredTheme(next);
  };

  const label = theme === "dark" ? "Switch to light theme" : "Switch to dark theme";

  return (
    <button
      type="button"
      className="nav__iconbtn theme-toggle"
      title={label}
      aria-label={label}
      onClick={toggle}
    >
      {theme === "dark" ? (
        // Sun icon — shown when we're in dark mode so the click affordance
        // suggests "switch to sunlight".
        <svg width="13" height="13" viewBox="0 0 13 13" fill="none" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round">
          <circle cx="6.5" cy="6.5" r="2.4" />
          <line x1="6.5" y1="0.8" x2="6.5" y2="2.4" />
          <line x1="6.5" y1="10.6" x2="6.5" y2="12.2" />
          <line x1="0.8" y1="6.5" x2="2.4" y2="6.5" />
          <line x1="10.6" y1="6.5" x2="12.2" y2="6.5" />
          <line x1="2.5" y1="2.5" x2="3.6" y2="3.6" />
          <line x1="9.4" y1="9.4" x2="10.5" y2="10.5" />
          <line x1="9.4" y1="3.6" x2="10.5" y2="2.5" />
          <line x1="2.5" y1="10.5" x2="3.6" y2="9.4" />
        </svg>
      ) : (
        // Crescent moon — shown in light mode so the affordance suggests
        // "switch to dark".
        <svg width="13" height="13" viewBox="0 0 13 13" fill="none" stroke="currentColor" strokeWidth="1.2" strokeLinejoin="round">
          <path d="M10.5 7.6 A4.5 4.5 0 1 1 5.4 2.5 A3.6 3.6 0 0 0 10.5 7.6 Z" />
        </svg>
      )}
    </button>
  );
}
