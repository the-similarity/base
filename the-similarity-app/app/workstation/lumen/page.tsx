/**
 * The Similarity workstation — Lumen-styled view at `/workstation/lumen`.
 *
 * This route renders the REAL Workstation component (analog retrieval,
 * lightweight-charts price view, top-K analog cards, P10/P90 forecast
 * cone, analog detail drawer) wrapped in the Lumen visual chrome
 * (flat white card surface, deep emerald accent, TradingView default /
 * JetBrains Mono fonts).
 *
 * Architectural choice — token cascade theming
 * --------------------------------------------
 * The Workstation component reads all of its colors from CSS custom
 * properties (`--bg`, `--bg-card`, `--ink`, `--accent`, etc.) defined
 * on `:root` by `app/globals.css`. By redefining the SAME variables on
 * the `.lumen-app` element (see styles.tsx), the Lumen palette wins via
 * the cascade for every descendant of this route — without modifying a
 * single line of `components/workstation/*` or `app/globals.css`.
 *
 * That is why this file only mounts <Workstation> and never imports
 * any styles from the workstation subtree. The whole repaint happens
 * via 30 lines of CSS variable overrides.
 *
 * State at this level:
 *   - `cmdOpen` — Cmd+K palette open/closed
 *   - `dark` — Lumen dark mode flag, controlled from Cmd+K
 *   - `settings` — WorkstationSettings forwarded to <Workstation>
 *
 * Theme side effects:
 *   - `dark` toggles a `.dark` class on `.lumen-app` AND mirrors the value
 *     into `settings.theme` so the embedded Workstation flips its own
 *     internal mode in lockstep.
 *
 * Keyboard:
 *   - Cmd/Ctrl + K toggles the palette
 *   - Esc closes the palette
 *
 * IMPORTANT — file scope discipline:
 *   This file MUST NOT modify any other route. Anything visual lives
 *   under `_components/` (Next.js treats `_*` folders as private
 *   non-routable). Every CSS class in styles.tsx is `lumen-` prefixed
 *   to avoid collisions with `app/globals.css`.
 */
"use client";

import { useEffect, useState } from "react";

import { LUMEN_CSS } from "./_components/styles";
import { CmdK } from "./_components/cmdk";
import { Topbar } from "./_components/shared";

// Embed the real product. The Workstation component is left untouched —
// it picks up the Lumen palette via CSS custom-property cascade (see the
// header comment above and the `.lumen-app { --bg: ... }` block in
// styles.tsx). WorkstationSettings is the same prop shape used by
// `/workstation` (the standalone route).
import {
  Workstation,
  type WorkstationSettings,
} from "../../../components/workstation/workstation";

/**
 * Workstation defaults — same shape used by `app/workstation/page.tsx`.
 *
 * - `theme: "light"` — paired with Lumen's flat light palette by default.
 * - `kAnalogs: 6`    — top-K matches returned by the search.
 * - `horizon: 60`    — forecast horizon in series steps.
 * - `showAnalogs: "all"` — every top-K match draws its own forward line.
 *   This is the product's core loop ("here are K analogs, each drawing
 *   a different possible future"), so we surface all of them.
 * - `showCone: false` — P10-P90 band hidden by default; the analog
 *   lines already convey the range.
 */
const WORKSTATION_DEFAULTS: WorkstationSettings = {
  theme: "light",
  kAnalogs: 6,
  horizon: 60,
  showAnalogs: "all",
  showCone: false,
};

export default function LumenPage() {
  const [cmdOpen, setCmdOpen] = useState(false);
  const [dark, setDark] = useState(false);
  const [settings, setSettings] = useState<WorkstationSettings>(
    WORKSTATION_DEFAULTS,
  );

  // Mirror the Lumen dark toggle into the embedded Workstation's
  // `settings.theme`. Without this, dark mode would flip the chrome
  // colors but leave the workstation's own `data-theme` attribute (read
  // by some of its sub-components) on the previous value, producing a
  // half-themed view.
  //
  // We compute the merged settings object DURING RENDER instead of in a
  // useEffect → setState pair. The previous effect-based mirror tripped
  // the `react-hooks/set-state-in-effect` lint rule (the React Compiler
  // treats post-render setState as a cascading-render anti-pattern).
  // Deriving the value here is also cheaper: it avoids the extra render
  // pass and keeps the prop in sync on the very first commit, without
  // an intermediate "wrong theme" frame.
  const desiredTheme: "dark" | "light" = dark ? "dark" : "light";
  const effectiveSettings: WorkstationSettings =
    settings.theme === desiredTheme
      ? settings
      : { ...settings, theme: desiredTheme };

  // Cmd/Ctrl+K toggles the palette; Esc closes it. We attach to window
  // so the shortcut works regardless of focus location within the app.
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setCmdOpen((o) => !o);
      }
      if (e.key === "Escape") setCmdOpen(false);
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);

  return (
    <>
      {/* Google Fonts — JetBrains Mono only. Lumen's UI stack mirrors
          TradingView's Lightweight Charts default system stack, so it
          does not need a downloaded sans/display font. */}
      <link
        rel="stylesheet"
        href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500&display=swap"
      />

      {/* Page-scoped stylesheet. Every selector is prefixed with
          .lumen-app and uses lumen- prefixed class names so it cannot
          affect — or be affected by — other routes. */}
      <style dangerouslySetInnerHTML={{ __html: LUMEN_CSS }} />

      <div className={`lumen-app${dark ? " dark" : ""}`}>
        {/* `.lumen-shell` (formerly `.app`) wraps the main workspace. The
            rename is the bugfix for the empty-main-panel problem: the
            global `.app` selector in app/globals.css set
            `grid-template-rows: 44px 1fr 26px`, which pushed nested
            app shells into the wrong row. */}
        <div className="lumen-shell">
          <div className="lumen-main">
            <Topbar
              crumbs={["Workspace", "Retrieve"]}
              onCmdK={() => setCmdOpen(true)}
            />
            {/*
             * Workstation host — flex container with min-height: 0 so
             * the embedded Workstation can do its own internal
             * scrolling (its left/right drawers + center grid manage
             * their own overflow). Without min-height: 0 the flexbox
             * default of `auto` would push the workstation past the
             * card's bottom edge.
             */}
            <div
              className="lumen-workstation-host"
              style={{
                display: "flex",
                flex: 1,
                minHeight: 0,
                overflow: "hidden",
              }}
            >
              <Workstation settings={effectiveSettings} onSettings={setSettings} />
            </div>
          </div>
        </div>

        <CmdK
          open={cmdOpen}
          onClose={() => setCmdOpen(false)}
          setDark={setDark}
        />
      </div>
    </>
  );
}
