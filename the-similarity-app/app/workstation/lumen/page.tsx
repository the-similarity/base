/**
 * Lumen Finance — workstation route at `/workstation/lumen`.
 *
 * This is a fully self-contained client-side page. The entire visual design
 * (sidebar + main panel + 9 screens + Cmd+K palette + tweaks panel + the
 * painterly background) lives under `app/workstation/lumen/_components/*`
 * and is page-scoped via the `.lumen-app` CSS root.
 *
 * State at this level:
 *   - `screen`: which of the 9 sub-screens is mounted in the main panel
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

import { LUMEN_CSS } from "./_components/styles";
import { Sidebar } from "./_components/sidebar";
import { CmdK } from "./_components/cmdk";
import { TweaksPanel } from "./_components/tweaks";
import type { TweakState } from "./_components/tweaks";
import type { ScreenId } from "./_components/screen-types";

import { ScreenDashboard } from "./_components/screens/dashboard";
import { ScreenCashflow } from "./_components/screens/cashflow";
import { ScreenInsights } from "./_components/screens/insights";
import { ScreenAccounts } from "./_components/screens/accounts";
import { ScreenTransactions } from "./_components/screens/transactions";
import { ScreenRecurring } from "./_components/screens/recurring";
import { ScreenBudgets } from "./_components/screens/budgets";
import { ScreenGoals } from "./_components/screens/goals";
import { ScreenInvestments } from "./_components/screens/investments";

// Background presets driven by the tweaks panel. The painterly DIV's
// inline background is overwritten with these strings; the page-scoped CSS
// supplies the default Painterly gradient as a fallback so a SSR pass with
// no tweak applied still renders the right look.
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
  const [screen, setScreen] = useState<ScreenId>("dashboard");
  const [cmdOpen, setCmdOpen] = useState(false);
  const [tweaks, setTweaks] = useState<TweakState>(TWEAK_DEFAULTS);

  // Refs to mutate accent CSS variables + the painterly element directly.
  // Doing this with refs (instead of inline style on the JSX) keeps the
  // tweak updates O(1) DOM writes per change rather than re-rendering the
  // whole tree just to swap colors.
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
      // The "paper" preset is a flat color, not a gradient; the underlying
      // CSS handles the noise overlay either way.
      p.style.background = BACKGROUNDS[tweaks.background] || BACKGROUNDS.painterly;
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
    case "dashboard":
      content = <ScreenDashboard {...screenProps} />;
      break;
    case "cashflow":
      content = <ScreenCashflow {...screenProps} />;
      break;
    case "insights":
      content = <ScreenInsights {...screenProps} />;
      break;
    case "accounts":
      content = <ScreenAccounts {...screenProps} />;
      break;
    case "transactions":
      content = <ScreenTransactions {...screenProps} />;
      break;
    case "recurring":
      content = <ScreenRecurring {...screenProps} />;
      break;
    case "budgets":
      content = <ScreenBudgets {...screenProps} />;
      break;
    case "goals":
      content = <ScreenGoals {...screenProps} />;
      break;
    case "investments":
      content = <ScreenInvestments {...screenProps} />;
      break;
    default:
      content = <ScreenDashboard {...screenProps} />;
  }

  return (
    <>
      {/* Google Fonts — Inter / Instrument Serif / JetBrains Mono. We
          inject a <link> here rather than via next/font because the
          Lumen page must not depend on the app's global font setup; if
          this file is ever lifted into another project the link comes
          with it. The crossOrigin attr is required by Chrome to actually
          use the preconnect hint. */}
      <link rel="preconnect" href="https://fonts.googleapis.com" />
      <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
      <link
        rel="stylesheet"
        href="https://fonts.googleapis.com/css2?family=Inter:wght@400;450;500;550;600;700&family=Instrument+Serif:ital@0;1&family=JetBrains+Mono:wght@400;500&display=swap"
      />

      {/* Page-scoped stylesheet. Every selector is prefixed with .lumen-app
          so it cannot affect other routes. */}
      <style dangerouslySetInnerHTML={{ __html: LUMEN_CSS }} />

      <div ref={rootRef} className="lumen-app">
        {/* Painterly background, contained inside .lumen-app so it cannot
            bleed beyond the route. */}
        <div ref={painterlyRef} className="lumen-painterly" />

        <div className="app">
          <Sidebar current={screen} onNavigate={setScreen} />
          <div className="main">{content}</div>
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
