/**
 * Cadence — personal health workstation at `/cadence`.
 *
 * The health-domain sibling of `/prudent` (which does self-similarity over
 * trader narratives) and inherits the visual design language of
 * `/workstation/lumen` (sidebar + 9 screens + Cmd+K + tweaks panel + the
 * painterly background).
 *
 * Crucial mission framing: Cadence runs self-similarity over the USER'S
 * OWN longitudinal data (mock 365-day biomarker history for a fictional
 * Buba), not against any cohort. The pitch is "your body has rhymed
 * before — here's what came next." No HIPAA cohort acquisition, no
 * privacy rabbit hole.
 *
 * State at this level:
 *   - `screen`: which of the 9 sub-screens is mounted in the main panel
 *   - `cmdOpen`: command palette open/closed
 *   - `tweaks`: { accent, background, dark } — driven by the tweaks panel
 *
 * Tweak side effects:
 *   - `accent` and `accent-2` CSS custom properties are mutated directly
 *     on the `.cadence-app` element (not :root) so they don't leak.
 *   - `dark` toggles a `.dark` class on the same element.
 *   - `background` swaps the painterly element's `background` style with
 *     one of the four presets (Bloom/Dawn/Paper/Slate).
 *
 * Keyboard:
 *   - Cmd/Ctrl + K toggles the palette
 *   - Esc closes the palette
 *
 * Why no localStorage persistence: v1 ships pure-session state per spec.
 * Adding persistence later is a one-liner: read defaults from localStorage
 * in the useState initializer and write back in the same useEffect that
 * syncs CSS vars.
 *
 * IMPORTANT — file scope discipline:
 *   This file MUST NOT modify any other route. Anything visual lives under
 *   `_components/` (Next.js treats `_*` folders as private/non-routable).
 */
"use client";

import { useEffect, useRef, useState } from "react";

import { CADENCE_CSS } from "./_components/styles";
import { Sidebar } from "./_components/sidebar";
import { CmdK } from "./_components/cmdk";
import { TweaksPanel } from "./_components/tweaks";
import type { TweakState } from "./_components/tweaks";
import type { ScreenId } from "./_components/screen-types";

import { ScreenToday } from "./_components/screens/today";
import { ScreenFlow } from "./_components/screens/flow";
import { ScreenRhymes } from "./_components/screens/rhymes";
import { ScreenCycles } from "./_components/screens/cycles";
import { ScreenLog } from "./_components/screens/log";
import { ScreenTargets } from "./_components/screens/targets";
import { ScreenGoals } from "./_components/screens/goals";
import { ScreenSources } from "./_components/screens/sources";
import { ScreenLabs } from "./_components/screens/labs";

// Background presets driven by the tweaks panel. The painterly DIV's
// inline background is overwritten with these strings; the page-scoped CSS
// supplies the default Bloom gradient as a fallback so a SSR pass with
// no tweak applied still renders the right look.
//
// Palette rationale:
//   bloom = sunrise coral → sage (the body's morning light)
//   dawn  = warmer sunrise → twilight indigo (the early hour)
//   paper = clinical white (chart-of-the-day reading mode)
//   slate = dark-mode bias (night reading / sleep tracking)
const BACKGROUNDS: Record<TweakState["background"], string> = {
  bloom:
    "linear-gradient(160deg, #d4a3a3 0%, #e8c4b0 30%, #b8c9a8 60%, #5b8a72 100%)",
  dawn: "linear-gradient(160deg, #f4d4b8 0%, #d4a3a3 40%, #8a6a8a 80%, #2a3a5c 100%)",
  paper: "#f4f1ea",
  slate: "linear-gradient(160deg, #1f2326 0%, #2a3030 50%, #1f2326 100%)",
};

// Default tweak state matches the design's TWEAK_DEFAULTS block.
// Sage accent + Bloom background = the "morning vitals" intro look.
const TWEAK_DEFAULTS: TweakState = {
  accent: "#5b8a72",
  background: "bloom",
  dark: false,
};

export default function CadencePage() {
  const [screen, setScreen] = useState<ScreenId>("today");
  const [cmdOpen, setCmdOpen] = useState(false);
  const [tweaks, setTweaks] = useState<TweakState>(TWEAK_DEFAULTS);

  // Refs to mutate accent CSS variables + the painterly element directly.
  // Doing this with refs (instead of inline style on the JSX) keeps the
  // tweak updates O(1) DOM writes per change rather than re-rendering the
  // whole tree just to swap colors.
  const rootRef = useRef<HTMLDivElement>(null);
  const painterlyRef = useRef<HTMLDivElement>(null);

  // Apply tweaks. We deliberately set the custom properties on the
  // .cadence-app root, not on document.documentElement, so the override
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
      // The "paper" preset is a flat color, not a gradient; the underlying
      // CSS handles the noise overlay either way.
      p.style.background = BACKGROUNDS[tweaks.background] || BACKGROUNDS.bloom;
    }
  }, [tweaks]);

  // Cmd/Ctrl+K toggles the palette; Esc closes it. We attach to window so
  // the shortcut works regardless of focus location within the app.
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

  const screenProps = {
    onCmdK: () => setCmdOpen(true),
    onNavigate: setScreen,
  };

  // Screen switch — each branch is a separate component so React reconciles
  // a fresh tree per route, getting the screen-fade animation for free.
  let content: React.ReactNode;
  switch (screen) {
    case "today":
      content = <ScreenToday {...screenProps} />;
      break;
    case "flow":
      content = <ScreenFlow {...screenProps} />;
      break;
    case "rhymes":
      content = <ScreenRhymes {...screenProps} />;
      break;
    case "cycles":
      content = <ScreenCycles {...screenProps} />;
      break;
    case "log":
      content = <ScreenLog {...screenProps} />;
      break;
    case "targets":
      content = <ScreenTargets {...screenProps} />;
      break;
    case "goals":
      content = <ScreenGoals {...screenProps} />;
      break;
    case "sources":
      content = <ScreenSources {...screenProps} />;
      break;
    case "labs":
      content = <ScreenLabs {...screenProps} />;
      break;
    default:
      content = <ScreenToday {...screenProps} />;
  }

  return (
    <>
      {/* Google Fonts — Inter / Instrument Serif / JetBrains Mono. We
          inject a <link> here rather than via next/font because the
          Cadence page must not depend on the app's global font setup; if
          this file is ever lifted into another project the link comes
          with it. The crossOrigin attr is required by Chrome to actually
          use the preconnect hint. */}
      <link rel="preconnect" href="https://fonts.googleapis.com" />
      <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
      <link
        rel="stylesheet"
        href="https://fonts.googleapis.com/css2?family=Inter:wght@400;450;500;550;600;700&family=Instrument+Serif:ital@0;1&family=JetBrains+Mono:wght@400;500&display=swap"
      />

      {/* Page-scoped stylesheet. Every selector is prefixed with .cadence-app
          so it cannot affect other routes. */}
      <style dangerouslySetInnerHTML={{ __html: CADENCE_CSS }} />

      <div ref={rootRef} className="cadence-app">
        {/* Painterly background, contained inside .cadence-app so it cannot
            bleed beyond the route. */}
        <div ref={painterlyRef} className="cadence-painterly" />

        {/* `.cadence-app-shell` (formerly `.app`) wraps sidebar + main.
            The rename is THE bugfix for the empty-main-panel problem:
            the global `.app` selector in app/globals.css set
            `grid-template-rows: 44px 1fr 26px`, which combined with our
            `grid-template-columns: 220px 1fr` to push the main panel
            into a 44px-tall first row. See styles.tsx for the full
            collision rationale. */}
        <div className="cadence-app-shell">
          <Sidebar current={screen} onNavigate={setScreen} />
          <div className="cadence-main">{content}</div>
        </div>

        <CmdK
          open={cmdOpen}
          onClose={() => setCmdOpen(false)}
          onNavigate={setScreen}
        />

        <TweaksPanel tweaks={tweaks} setTweaks={setTweaks} />
      </div>
    </>
  );
}
