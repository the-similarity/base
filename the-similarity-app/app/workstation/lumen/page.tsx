/**
 * The Similarity workstation — Lumen-styled view at `/workstation/lumen`.
 *
 * This route renders the REAL Workstation component (analog retrieval,
 * lightweight-charts price view, top-K analog cards, P10/P90 forecast
 * cone, 9-lens trust radar) wrapped in the Lumen visual chrome
 * (painterly background, white card surface, deep emerald accent,
 * Inter / Instrument Serif / JetBrains Mono fonts).
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
 *   - `tweaks`  — { accent, background, dark } — driven by the tweaks panel
 *   - `settings` — WorkstationSettings forwarded to <Workstation>
 *
 * Tweak side effects:
 *   - `accent` and `accent-2` CSS custom properties are mutated directly
 *     on the `.lumen-app` element (not :root) so they don't leak.
 *   - `dark` toggles a `.dark` class on the same element AND mirrors the
 *     value into `settings.theme` so the embedded Workstation flips its
 *     own internal mode in lockstep.
 *   - `background` swaps the painterly element's `background` style with
 *     one of the four presets (Painterly/Dusk/Char/Paper).
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

import { useEffect, useRef, useState } from "react";

import { LUMEN_CSS } from "./_components/styles";
import { Sidebar } from "./_components/sidebar";
import { CmdK } from "./_components/cmdk";
import { TweaksPanel } from "./_components/tweaks";
import { Topbar } from "./_components/shared";
import type { TweakState } from "./_components/tweaks";

// Embed the real product. The Workstation component is left untouched —
// it picks up the Lumen palette via CSS custom-property cascade (see the
// header comment above and the `.lumen-app { --bg: ... }` block in
// styles.tsx). WorkstationSettings is the same prop shape used by
// `/workstation` (the standalone route).
import {
  Workstation,
  type WorkstationSettings,
} from "../../../components/workstation/workstation";

// Background presets driven by the tweaks panel. The painterly DIV's
// inline background is overwritten with these strings; the page-scoped
// CSS supplies the default Painterly gradient as a fallback so a SSR
// pass with no tweak applied still renders the right look.
const BACKGROUNDS: Record<TweakState["background"], string> = {
  painterly:
    "linear-gradient(160deg, #4a7a5a 0%, #6b9a72 25%, #c4b896 55%, #8a6a4a 80%, #3d2f1f 100%)",
  dusk: "linear-gradient(160deg, #2a3a5c 0%, #6b6a8c 35%, #c89a78 70%, #5c2a3a 100%)",
  paper: "#f4f1ea",
  charcoal: "linear-gradient(160deg, #1a1c1e 0%, #2a2d30 50%, #1a1c1e 100%)",
};

// Default tweak state matches the design's TWEAK_DEFAULTS block.
const TWEAK_DEFAULTS: TweakState = {
  accent: "#0a6b48",
  background: "painterly",
  dark: false,
};

/**
 * Workstation defaults — same shape used by `app/workstation/page.tsx`.
 *
 * - `theme: "light"` — paired with Lumen's painterly-on-paper light
 *   palette by default.
 * - `kAnalogs: 6`    — top-K matches returned by the search.
 * - `horizon: 60`    — forecast horizon in series steps.
 * - `showAnalogs: "all"` — every top-K match draws its own forward line.
 *   This is the product's core loop ("here are K analogs, each drawing
 *   a different possible future"), so we surface all of them.
 * - `showCone: false` — P10–P90 band hidden by default; the analog
 *   lines already convey the range. Users can flip it on inside the
 *   embedded Workstation's tweaks panel.
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
  const [tweaks, setTweaks] = useState<TweakState>(TWEAK_DEFAULTS);
  const [settings, setSettings] = useState<WorkstationSettings>(
    WORKSTATION_DEFAULTS,
  );

  // Refs to mutate accent CSS variables + the painterly element directly.
  // Doing this with refs (instead of inline style on the JSX) keeps the
  // tweak updates O(1) DOM writes per change rather than re-rendering
  // the whole tree just to swap colors.
  const rootRef = useRef<HTMLDivElement>(null);
  const painterlyRef = useRef<HTMLDivElement>(null);

  // Apply tweaks. We deliberately set the custom properties on the
  // .lumen-app root, not on document.documentElement, so the override
  // can't bleed into other routes if the user navigates away.
  useEffect(() => {
    const root = rootRef.current;
    if (root) {
      root.style.setProperty("--accent", tweaks.accent);
      root.style.setProperty("--accent-2", tweaks.accent);
      root.classList.toggle("dark", tweaks.dark);
    }
    const p = painterlyRef.current;
    if (p) {
      // The "paper" preset is a flat color, not a gradient; the
      // underlying CSS handles the noise overlay either way.
      p.style.background = BACKGROUNDS[tweaks.background] || BACKGROUNDS.painterly;
    }
  }, [tweaks]);

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
  const desiredTheme: "dark" | "light" = tweaks.dark ? "dark" : "light";
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
      {/* Google Fonts — Inter / Instrument Serif / JetBrains Mono. We
          inject a <link> here rather than via next/font because the
          Lumen page must not depend on the app's global font setup; if
          this file is ever lifted into another project the link comes
          with it. The crossOrigin attr is required by Chrome to
          actually use the preconnect hint. */}
      <link rel="preconnect" href="https://fonts.googleapis.com" />
      <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
      <link
        rel="stylesheet"
        href="https://fonts.googleapis.com/css2?family=Inter:wght@400;450;500;550;600;700&family=Instrument+Serif:ital@0;1&family=JetBrains+Mono:wght@400;500&display=swap"
      />

      {/* Page-scoped stylesheet. Every selector is prefixed with
          .lumen-app and uses lumen- prefixed class names so it cannot
          affect — or be affected by — other routes. */}
      <style dangerouslySetInnerHTML={{ __html: LUMEN_CSS }} />

      <div ref={rootRef} className="lumen-app">
        {/* Painterly background, contained inside .lumen-app so it
            cannot bleed beyond the route. */}
        <div ref={painterlyRef} className="lumen-painterly" />

        {/* `.lumen-shell` (formerly `.app`) wraps sidebar + main. The
            rename is the bugfix for the empty-main-panel problem: the
            global `.app` selector in app/globals.css set
            `grid-template-rows: 44px 1fr 26px`, which combined with our
            `grid-template-columns: 220px 1fr` to push the main panel
            into a 44px-tall first row. */}
        <div className="lumen-shell">
          <Sidebar
            current="retrieve"
            // The Lumen route hosts a single screen. `onNavigate` is
            // wired but has nowhere to route — calls are accepted as a
            // no-op. Keeping the prop typed means the sidebar stays
            // contract-compatible if a second contained screen lands.
            onNavigate={() => {}}
          />
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
          setTweaks={setTweaks}
        />

        <TweaksPanel tweaks={tweaks} setTweaks={setTweaks} />
      </div>
    </>
  );
}
