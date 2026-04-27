/**
 * The Similarity workstation — Lumen-styled view at `/workstation/lumen`.
 *
 * This route wraps OUR product (analog retrieval, finance runs, etc.) in
 * the Lumen visual design (painterly background, white card surface,
 * deep emerald accent, Inter / Instrument Serif / JetBrains Mono fonts,
 * sidebar + topbar + main shell). The content inside the chrome is The
 * Similarity's own data — Retrieve, Finance Runs, Compare, Reviews,
 * Dashboard, Strategy, Cadence, Case Studies, Reports.
 *
 * The page is fully self-contained client-side. The visual chrome and
 * eight sub-screens live under `app/workstation/lumen/_components/*` and
 * are page-scoped via the `.lumen-app` CSS root + `lumen-` prefixed
 * class names.
 *
 * State at this level:
 *   - `screen`: which of the 8 sub-screens is mounted in the main panel
 *   - `cmdOpen`: command palette open/closed
 *   - `tweaks`: { accent, background, dark } — driven by the tweaks panel
 *
 * Tweak side effects:
 *   - `accent` and `accent-2` CSS custom properties are mutated directly
 *     on the `.lumen-app` element (not :root) so they don't leak.
 *   - `dark` toggles a `.dark` class on the same element.
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
 *   non-routable). Every CSS class here is `lumen-` prefixed to avoid
 *   collisions with `app/globals.css`.
 */
"use client";

import { useEffect, useRef, useState } from "react";

import { LUMEN_CSS } from "./_components/styles";
import { Sidebar } from "./_components/sidebar";
import { CmdK } from "./_components/cmdk";
import { TweaksPanel } from "./_components/tweaks";
import type { TweakState } from "./_components/tweaks";
import type { ScreenId } from "./_components/screen-types";

import { ScreenRetrieve } from "./_components/screens/retrieve";
import { ScreenRuns } from "./_components/screens/runs";
import { ScreenCompare } from "./_components/screens/compare";
import { ScreenReviews } from "./_components/screens/reviews";
import { ScreenDashboard } from "./_components/screens/dashboard";
import { ScreenStrategy } from "./_components/screens/strategy";
import { ScreenCadence } from "./_components/screens/cadence";
import { ScreenCaseStudies } from "./_components/screens/case-studies";
import { ScreenReports } from "./_components/screens/reports";

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

export default function LumenPage() {
  // Default to "retrieve" — that's the headline workstation view.
  const [screen, setScreen] = useState<ScreenId>("retrieve");
  const [cmdOpen, setCmdOpen] = useState(false);
  const [tweaks, setTweaks] = useState<TweakState>(TWEAK_DEFAULTS);

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

  const screenProps = {
    onCmdK: () => setCmdOpen(true),
    onNavigate: setScreen,
    setTweaks,
  };

  // Screen switch — each branch is a separate component so React
  // reconciles a fresh tree per route, getting the screen-fade
  // animation for free.
  let content: React.ReactNode;
  switch (screen) {
    case "retrieve":
      content = <ScreenRetrieve {...screenProps} />;
      break;
    case "runs":
      content = <ScreenRuns {...screenProps} />;
      break;
    case "compare":
      content = <ScreenCompare {...screenProps} />;
      break;
    case "reviews":
      content = <ScreenReviews {...screenProps} />;
      break;
    case "dashboard":
      content = <ScreenDashboard {...screenProps} />;
      break;
    case "strategy":
      content = <ScreenStrategy {...screenProps} />;
      break;
    case "cadence":
      content = <ScreenCadence {...screenProps} />;
      break;
    case "case-studies":
      content = <ScreenCaseStudies {...screenProps} />;
      break;
    case "reports":
      content = <ScreenReports {...screenProps} />;
      break;
    default:
      content = <ScreenRetrieve {...screenProps} />;
  }

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
          <Sidebar current={screen} onNavigate={setScreen} />
          <div className="lumen-main">{content}</div>
        </div>

        <CmdK
          open={cmdOpen}
          onClose={() => setCmdOpen(false)}
          onNavigate={setScreen}
          setTweaks={setTweaks}
        />

        <TweaksPanel tweaks={tweaks} setTweaks={setTweaks} />
      </div>
    </>
  );
}
