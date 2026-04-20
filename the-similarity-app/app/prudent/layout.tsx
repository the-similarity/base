"use client";

/**
 * Prudent route layout.
 *
 * Owns the visual shell — `.prudent-root` CSS scope, the scoped <style>
 * block, the sidebar, the top bar, and the page header. Every /prudent/*
 * route renders its body inside this layout so the chrome never flashes
 * when the user navigates between pages.
 *
 * Why a client component:
 *   The layout hosts <EngineProvider> (localStorage read, keyboard
 *   shortcuts, composer open/close state) and the sidebar needs
 *   `usePathname()` to highlight the active nav. Both require the
 *   client runtime.
 *
 * Critical invariant (workstation scroll containment):
 *   `/app/globals.css` pins `body { overflow: hidden }` for the
 *   Bloomberg-terminal layout. The `.prudent-root` class opens its own
 *   scrollable viewport (`height: 100vh; overflow-y: auto`) so the
 *   prudent surface scrolls independently. Do not remove that pair — the
 *   sidebar's `position: sticky` sticks against it, and without it the
 *   prudent page cannot scroll at all.
 */

import { useRef, type ReactNode } from "react";
import { EngineProvider } from "./_components/engine-context";
import { Sidebar, TopBar, PageHeader, Footer } from "./_components/shell";

export default function PrudentLayout({ children }: { children: ReactNode }) {
  // Ref passed to EngineProvider so it can set accent/theme CSS variables
  // on THIS element without touching globals. Scoped to /prudent so the
  // workstation theme can't leak and vice versa.
  const rootRef = useRef<HTMLDivElement>(null);

  return (
    <div ref={rootRef} className="prudent-root">
      <EngineProvider rootRef={rootRef}>
        <div style={{ display: "flex", minHeight: "100vh", background: "var(--app-bg)" }}>
          <Sidebar />
          <main
            // 24px horizontal padding matches the reference grid; 18px gap
            // between child cards keeps the layout airy without wasting
            // canvas on ultra-wide displays.
            style={{
              flex: 1,
              padding: "18px 24px 28px 24px",
              display: "flex",
              flexDirection: "column",
              gap: 18,
              minWidth: 0,
            }}
          >
            <TopBar />
            <PageHeader />
            {children}
            <Footer />
          </main>
        </div>
      </EngineProvider>

      <style>{`
        .prudent-root {
          /* Airy warm-white canvas. 4-point delta between --app-bg and --panel
             (FAFAFA → FFFFFF) is enough to read as a lifted card in daylight
             but stays invisible under color-deficient rendering. */
          --app-bg: #FAFAFA;
          --sidebar: #FFFFFF;
          --panel: #FFFFFF;
          --text: #14161A;
          --muted: #6B7280;
          --faint: #9CA3AF;
          --line: #ECEEF1;
          --line-mid: #E3E6EA;
          --hover: #F3F4F6;
          --ink: #14161A;
          --accent: #3B82F6;
          --accent-mid: #93C5FD;
          --accent-soft: #DBEAFE;
          --accent-ink: #1D4ED8;
          --warm: #F97316;
          --warm-strong: #EA580C;
          --warm-soft: #FED7AA;
          --cool: #0E7490;
          --green: #16A34A;
          --rail: #1F2328;
          --rail-ink: #9CA3AF;
          --rail-active: #2A2F36;
          --mono: 'JetBrains Mono', 'SF Mono', Consolas, monospace;
          --serif: 'Newsreader', Georgia, serif;
          font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
          background: var(--app-bg);
          color: var(--text);
          -webkit-font-smoothing: antialiased;
          font-feature-settings: 'cv11','ss01','cv03';
          /* Own scroll container — workstation globals.css pins
             body { overflow: hidden } for the Bloomberg terminal layout.
             Without these two rules /prudent cannot scroll. */
          height: 100vh;
          overflow-y: auto;
          overflow-x: hidden;
        }
        .prudent-root.prudent-dark {
          --app-bg: #0E0F11;
          --sidebar: #131518;
          --panel: #17191C;
          --text: #EDEEF0;
          --muted: #9AA0A8;
          --faint: #636771;
          --line: #23262B;
          --line-mid: #2C3036;
          --hover: #1D2024;
          --ink: #F5F6F8;
          --accent-soft: #1E3A8A;
          --accent-mid: #60A5FA;
          --accent-ink: #93C5FD;
          --warm-soft: #7C2D12;
          --rail: #0A0B0D;
          --rail-ink: #6B7280;
          --rail-active: #1F2328;
          --green: #22C55E;
        }
        .prudent-root.prudent-dark ::selection {
          background: var(--accent-soft);
          color: var(--ink);
        }
        .prudent-root *, .prudent-root *::before, .prudent-root *::after {
          box-sizing: border-box;
        }
        .prudent-root button {
          font: inherit;
          color: inherit;
          background: none;
          border: none;
          cursor: pointer;
          padding: 0;
        }
        .prudent-root input,
        .prudent-root textarea {
          font: inherit;
          color: inherit;
          background: none;
          border: none;
          outline: none;
        }
        .prudent-root .mono { font-family: var(--mono); }
        .prudent-root .serif { font-family: var(--serif); }
        .prudent-root .tnum { font-variant-numeric: tabular-nums; }
        .prudent-root ::selection { background: var(--accent); color: #fff; }

        /* Top grid: metrics column + chart. 340px left column works above
           1280px; below that we stack so the chart isn't squeezed into a
           sliver. The heatmap/donut mid grid follows the same principle. */
        .prudent-root .prudent-grid-top {
          display: grid;
          grid-template-columns: 340px 1fr;
          gap: 18px;
        }
        .prudent-root .prudent-grid-mid {
          display: grid;
          grid-template-columns: 1.4fr 1fr;
          gap: 18px;
        }
        @media (max-width: 1280px) {
          .prudent-root .prudent-grid-top {
            grid-template-columns: 1fr;
          }
          .prudent-root .prudent-grid-mid {
            grid-template-columns: 1fr;
          }
        }

        /* Subtle hover affordance on all nav-ish buttons so the cursor never
           feels stuck on a dead label. */
        .prudent-root button:hover:not(:disabled) {
          filter: brightness(0.98);
        }
      `}</style>
    </div>
  );
}
