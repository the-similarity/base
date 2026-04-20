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
 * Why ComposerModal + TweaksPanel live here (and not in today-view):
 *   These two surfaces are GLOBAL to the /prudent tree — the composer is
 *   opened from the sidebar "+ New entry" button on every page, and from
 *   empty-state CTAs on /prudent/thread, /prudent/rhymes, /prudent/tags,
 *   /prudent/patterns, /prudent/entries, /prudent/engine. When they lived
 *   in today-view.tsx they only mounted at `/prudent`, so clicking
 *   "+ New entry" on any sub-route flipped context state but no modal
 *   rendered. Lifting them to the layout mounts them exactly once and
 *   makes them work from any route. Same rationale for the floating
 *   Tweaks panel: it must be visible from every page so accent/theme/
 *   compare tweaks apply globally.
 *
 * Critical invariant (workstation scroll containment):
 *   `/app/globals.css` pins `body { overflow: hidden }` for the
 *   Bloomberg-terminal layout. The `.prudent-root` class opens its own
 *   scrollable viewport (`height: 100vh; overflow-y: auto`) so the
 *   prudent surface scrolls independently. Do not remove that pair — the
 *   sidebar's `position: sticky` sticks against it, and without it the
 *   prudent page cannot scroll at all.
 */

import {
  useEffect,
  useMemo,
  useRef,
  type ReactNode,
} from "react";
import {
  EngineProvider,
  useEngine,
  ACCENT_HEX,
  type Accent,
  type Tweaks,
} from "./_components/engine-context";
import { Sidebar, TopBar, PageHeader, Footer, fmtLongDate, fmtClockTime } from "./_components/shell";
import { useParsedNarrative } from "./use-parse";
import type { Event } from "./engine";

// Sample narrative — shown as the textarea placeholder only. Actual entry
// state always starts empty so "+ New entry" never pre-fills the composer
// with a stranger's day.
const SAMPLE = `Woke up heavy, kind of anxious about the deadline. The morning was rough — emails piled up before I even had coffee. Slow standup, I barely talked. Around noon I went for a walk in the park and things started to lift. Ran into a friend who'd just moved back; we laughed about something stupid for twenty minutes. The afternoon clicked — I got into a flow and the code finally worked. Dinner was calm, read a little before bed.`;

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
        {/* Global composer + tweaks — mounted once, visible on every route.
            See module docstring for the "why". These MUST remain children
            of <EngineProvider> so they can call useEngine(). */}
        <ComposerHost />
        <TweaksHost />
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

// ═══════════════════════════════════════════════════════════════════════
// ComposerHost — wires engine context + live parse into <ComposerModal>
// ═══════════════════════════════════════════════════════════════════════
//
// Why a host layer:
//   ComposerModal is a dumb presentation component — it receives text,
//   events, onSave, etc. as props. The host is the thin adapter that
//   (a) reads the shared composer state from EngineContext,
//   (b) runs `useParsedNarrative(text)` to derive the live events/series
//       shown in the "parsed" readout,
//   (c) returns null when the composer is closed so no DOM cost is paid
//       while it's idle.
//
// The host MUST mount once, inside <EngineProvider>. It is rendered by
// the layout above rather than by any page component so the modal mounts
// on EVERY /prudent sub-route — previously it only mounted at /prudent
// because today-view.tsx (where it used to live) is only rendered by
// `app/prudent/page.tsx`.
function ComposerHost() {
  const {
    text,
    setText,
    composerOpen,
    readOnlyEntry,
    closeComposer,
    persistEntry,
  } = useEngine();
  // Parse the composer draft live. Runs only while the modal is open
  // (the hook is invoked unconditionally to keep hook order stable, but
  // its API-fetch side effect early-exits on empty text).
  const parsed = useParsedNarrative(text);

  if (!composerOpen) return null;
  return (
    <ComposerModal
      text={readOnlyEntry ? readOnlyEntry.text : text}
      setText={setText}
      onClose={closeComposer}
      events={readOnlyEntry ? readOnlyEntry.events : parsed.events}
      source={readOnlyEntry ? "idle" : parsed.source}
      readOnly={!!readOnlyEntry}
      readOnlyLabel={
        readOnlyEntry
          ? `day −${readOnlyEntry.day} · logged ${readOnlyEntry.createdAt.slice(0, 10)}`
          : undefined
      }
      onSave={() =>
        persistEntry({
          text,
          events: parsed.events,
          series: parsed.series,
          avg: Math.round(
            parsed.series.reduce((a, b) => a + b.v, 0) /
              (parsed.series.length || 1),
          ),
        })
      }
    />
  );
}

// ═══════════════════════════════════════════════════════════════════════
// TweaksHost — wires engine context into <TweaksPanel>
// ═══════════════════════════════════════════════════════════════════════
//
// Same shape as ComposerHost: a tiny adapter that pulls tweaks + setter
// out of the context and renders the floating panel. Lives at layout
// level so the panel is visible (and editable) on every /prudent route
// — e.g. a user on /prudent/thread can still swap accent/theme/compare
// without navigating back to /prudent.
function TweaksHost() {
  const { tweaks, setTweak } = useEngine();
  return <TweaksPanel tweaks={tweaks} setTweak={setTweak} />;
}

// ═══════════════════════════════════════════════════════════════════════
// ComposerModal — narrative input with live-parsed readout
// ═══════════════════════════════════════════════════════════════════════
//
// Presentation-only. Consumes:
//   - `text` / `setText` — the draft. In read-only mode, `text` is the
//     archived entry's narrative and `setText` is never called.
//   - `events` — parsed events rendered as underlined chips in the readout.
//   - `source` — visual hint for the "source:" pill (api / regex / idle).
//   - `onSave` / `onClose` — close/persist callbacks from the host.
//
// Focus rule: on open (non-readonly) we focus the textarea via useEffect
// + ref so the user can start typing immediately.

interface ComposerProps {
  text: string;
  setText: (t: string) => void;
  onClose: () => void;
  events: Event[];
  source?: "api" | "regex" | "idle";
  readOnly?: boolean;
  readOnlyLabel?: string;
  onSave: () => void;
}

function ComposerModal({
  text,
  setText,
  onClose,
  events,
  source = "regex",
  readOnly = false,
  readOnlyLabel,
  onSave,
}: ComposerProps) {
  const ref = useRef<HTMLTextAreaElement>(null);
  useEffect(() => {
    if (!readOnly) ref.current?.focus();
  }, [readOnly]);
  const now = useMemo(() => new Date(), []);
  const composerStamp = `${fmtLongDate(now)} · ${fmtClockTime(now)} · parsing live`;
  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 100,
        background: "rgba(14,15,17,0.45)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
      }}
      onClick={onClose}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          width: 720,
          maxWidth: "92vw",
          maxHeight: "85vh",
          overflow: "auto",
          background: "var(--panel)",
          borderRadius: 12,
          boxShadow: "0 30px 60px -20px rgba(0,0,0,0.4)",
          display: "flex",
          flexDirection: "column",
        }}
      >
        <div
          style={{
            padding: "16px 20px",
            borderBottom: "1px solid var(--line)",
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
          }}
        >
          <div>
            <div style={{ fontSize: 14, fontWeight: 600 }}>
              {readOnly ? "Entry" : "New entry"}
            </div>
            <div style={{ fontSize: 11, color: "var(--muted)" }}>
              {readOnly ? readOnlyLabel ?? "archived entry · read only" : composerStamp}
            </div>
          </div>
          <button
            onClick={onClose}
            style={{ color: "var(--muted)", padding: "4px 8px", borderRadius: 6 }}
            aria-label="Close"
          >
            ✕
          </button>
        </div>
        <div style={{ padding: "18px 22px" }}>
          <textarea
            ref={ref}
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder={readOnly ? "" : SAMPLE}
            rows={8}
            disabled={readOnly}
            readOnly={readOnly}
            style={{
              width: "100%",
              fontFamily: "var(--serif)",
              fontSize: 19,
              lineHeight: 1.6,
              color: "var(--ink)",
              resize: readOnly ? "none" : "vertical",
              minHeight: 200,
              letterSpacing: "-0.005em",
              cursor: readOnly ? "text" : "text",
              opacity: readOnly ? 0.95 : 1,
            }}
          />
          <div
            style={{
              marginTop: 18,
              paddingTop: 16,
              borderTop: "1px solid var(--line)",
            }}
          >
            <div
              className="mono"
              style={{
                fontSize: 10,
                letterSpacing: "0.08em",
                color: "var(--muted)",
                fontWeight: 600,
                marginBottom: 12,
                textTransform: "uppercase",
                display: "flex",
                alignItems: "center",
                gap: 8,
              }}
            >
              <span>Parsed</span>
              <span
                style={{
                  background: "var(--accent-soft)",
                  color: "var(--accent-ink)",
                  padding: "2px 7px",
                  borderRadius: 10,
                  fontSize: 10,
                  fontWeight: 600,
                  letterSpacing: "0.02em",
                }}
              >
                {events.length} events
              </span>
            </div>
            <div
              style={{
                fontSize: 13.5,
                lineHeight: 2.1,
                color: "var(--muted)",
                fontFamily: "var(--serif)",
                fontStyle: "italic",
              }}
            >
              {events.length === 0 && (
                <span style={{ color: "var(--faint)" }}>
                  No anchors detected yet — keep writing, the engine finds them as
                  you type.
                </span>
              )}
              {events.map((ev, i) => {
                const positive = ev.delta > 0;
                const stroke = positive ? "var(--green)" : "var(--warm-strong)";
                const bg = positive
                  ? "rgba(22,163,74,0.10)"
                  : "rgba(234,88,12,0.10)";
                return (
                  <span
                    key={i}
                    style={{
                      marginRight: 8,
                      display: "inline-flex",
                      alignItems: "center",
                      gap: 4,
                    }}
                  >
                    <span
                      style={{
                        borderBottom: `2px solid ${stroke}`,
                        color: "var(--ink)",
                        padding: "0 3px 1px 3px",
                        fontStyle: "normal",
                        fontFamily: "var(--serif)",
                      }}
                    >
                      {ev.text.replace(/[.?!,]+$/, "").slice(0, 40)}
                      {ev.text.length > 40 ? "…" : ""}
                    </span>
                    <span
                      className="mono tnum"
                      style={{
                        fontSize: 10,
                        padding: "2px 6px",
                        borderRadius: 10,
                        background: bg,
                        color: stroke,
                        fontWeight: 600,
                        fontStyle: "normal",
                        letterSpacing: "-0.01em",
                      }}
                    >
                      {positive ? "+" : ""}
                      {ev.delta.toFixed(0)}
                    </span>
                  </span>
                );
              })}
            </div>
          </div>
        </div>
        <div
          style={{
            padding: "14px 22px",
            borderTop: "1px solid var(--line)",
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
          }}
        >
          <div
            className="mono"
            style={{
              fontSize: 10.5,
              color: "var(--faint)",
              letterSpacing: "0.02em",
              display: "inline-flex",
              alignItems: "center",
              gap: 10,
            }}
          >
            <span>
              <span className="tnum">{text.length}</span> chars ·{" "}
              <span className="tnum">{events.length}</span> events
            </span>
            {!readOnly && (
              <span
                style={{
                  display: "inline-flex",
                  alignItems: "center",
                  gap: 4,
                  padding: "2px 6px",
                  background:
                    source === "api" ? "var(--accent-soft)" : "var(--hover)",
                  color:
                    source === "api" ? "var(--accent-ink)" : "var(--muted)",
                  borderRadius: 10,
                  fontWeight: 600,
                  letterSpacing: "0.02em",
                }}
              >
                <span
                  style={{
                    width: 5,
                    height: 5,
                    borderRadius: "50%",
                    background:
                      source === "api"
                        ? "var(--accent)"
                        : source === "regex"
                          ? "var(--warm)"
                          : "var(--faint)",
                  }}
                />
                source: {source}
              </span>
            )}
          </div>
          <div style={{ display: "flex", gap: 8 }}>
            <button
              onClick={onClose}
              style={{
                fontSize: 13,
                padding: "8px 14px",
                borderRadius: 7,
                border: "1px solid var(--line-mid)",
                color: "var(--muted)",
              }}
            >
              {readOnly ? "Close" : "Cancel"}
            </button>
            {!readOnly && (
              <button
                onClick={onSave}
                disabled={!text.trim()}
                style={{
                  fontSize: 13,
                  padding: "8px 16px",
                  borderRadius: 7,
                  background: text.trim() ? "var(--ink)" : "var(--line-mid)",
                  color: "var(--app-bg)",
                  fontWeight: 500,
                  display: "inline-flex",
                  alignItems: "center",
                  gap: 8,
                  cursor: text.trim() ? "pointer" : "not-allowed",
                  opacity: text.trim() ? 1 : 0.65,
                }}
              >
                Log to thread
                <span
                  className="mono"
                  style={{ fontSize: 11, opacity: 0.55, letterSpacing: "0.02em" }}
                >
                  ↵
                </span>
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════
// TweaksPanel — floating accent / theme / compare chooser
// ═══════════════════════════════════════════════════════════════════════
//
// A `position: fixed` panel anchored bottom-right of the viewport. Because
// the layout mounts it once, it appears on every /prudent page. The panel
// only writes tweaks through the context setter; the provider persists to
// localStorage and emits CSS variables on `.prudent-root`.

interface TweaksPanelProps {
  tweaks: Tweaks;
  setTweak: <K extends keyof Tweaks>(k: K, v: Tweaks[K]) => void;
}

function TweaksPanel({ tweaks, setTweak }: TweaksPanelProps) {
  const opts = <K extends keyof Tweaks>(key: K, choices: readonly Tweaks[K][]) => (
    <div style={{ display: "flex", gap: 3, flexWrap: "wrap" }}>
      {choices.map((c) => (
        <button
          key={String(c)}
          onClick={() => setTweak(key, c)}
          className="mono"
          style={{
            fontSize: 10,
            padding: "4px 9px",
            border: `1px solid ${tweaks[key] === c ? "var(--ink)" : "var(--line-mid)"}`,
            background: tweaks[key] === c ? "var(--ink)" : "transparent",
            color: tweaks[key] === c ? "var(--app-bg)" : "var(--muted)",
            borderRadius: 5,
            fontWeight: 500,
            letterSpacing: "0.02em",
            transition: "background 100ms ease, color 100ms ease",
          }}
        >
          {String(c)}
        </button>
      ))}
    </div>
  );

  const accentChoices: Accent[] = ["blue", "ember", "teal", "plum"];
  const accentSwatches = (
    <div style={{ display: "flex", gap: 6 }}>
      {accentChoices.map((c) => {
        const active = tweaks.accent === c;
        return (
          <button
            key={c}
            onClick={() => setTweak("accent", c)}
            aria-label={`accent ${c}`}
            style={{
              width: 22,
              height: 22,
              borderRadius: "50%",
              background: ACCENT_HEX[c],
              border: `2px solid ${active ? "var(--ink)" : "transparent"}`,
              boxShadow: active
                ? "0 0 0 2px var(--panel), 0 0 0 3px rgba(20,22,26,0.25)"
                : "inset 0 0 0 1px rgba(0,0,0,0.08)",
              cursor: "pointer",
              padding: 0,
              transition: "transform 120ms ease",
              transform: active ? "scale(1.05)" : "scale(1)",
            }}
          />
        );
      })}
    </div>
  );

  return (
    <div
      style={{
        position: "fixed",
        bottom: 16,
        right: 16,
        width: 248,
        zIndex: 60,
        background: "var(--panel)",
        border: "1px solid var(--line-mid)",
        borderRadius: 8,
        padding: "12px 14px 14px 14px",
        boxShadow: "0 16px 32px -16px rgba(0,0,0,0.32)",
      }}
    >
      <div
        style={{
          fontSize: 11,
          fontWeight: 600,
          marginBottom: 10,
          letterSpacing: "0.06em",
          textTransform: "uppercase",
          color: "var(--muted)",
        }}
        className="mono"
      >
        Tweaks
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        <TweakRow label="accent">{accentSwatches}</TweakRow>
        <TweakRow label="theme">{opts("theme", ["light", "dark"] as const)}</TweakRow>
        <TweakRow label="compare">{opts("compare", ["rhyme", "yesterday", "none"] as const)}</TweakRow>
      </div>
    </div>
  );
}

function TweakRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        gap: 10,
      }}
    >
      <div
        className="mono"
        style={{
          fontSize: 9.5,
          color: "var(--muted)",
          textTransform: "uppercase",
          letterSpacing: "0.08em",
          fontWeight: 600,
          minWidth: 50,
        }}
      >
        {label}
      </div>
      {children}
    </div>
  );
}
