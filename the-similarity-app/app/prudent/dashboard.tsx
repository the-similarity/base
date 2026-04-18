"use client";

/**
 * Prudent dashboard — Natural Language → Time Series analytics surface.
 *
 * The design is a handoff from Claude Design (see /tmp/prudent-design).
 * It is a full-bleed analytics surface composed of:
 *   - Left sidebar (icon rail + labeled nav with sections)
 *   - Top bar (breadcrumb + avatar)
 *   - Page header (title + filter chips)
 *   - Key metrics column (avg valence, uplift events, volatility, peak/trough)
 *   - Main chart (integrated day trajectory with compare overlay)
 *   - Busiest-valence heatmap (7-day × 12-hour grid)
 *   - Tag donut (share of weighted events)
 *   - Thread ribbon (30-day history strip)
 *   - Composer modal (narrative input with live parse readout)
 *
 * The design uses its own CSS-variable palette (--app-bg, --accent, …).
 * These variables are declared on the `.prudent-root` wrapper so the
 * dashboard is fully self-contained and does not collide with the rest of
 * the workstation app's theme.
 */

import { useState, useEffect, useMemo, useRef, Fragment } from "react";
import {
  parseNarrative,
  buildHistory,
  findRhyme,
  type Event,
  type Point,
  type HistoryDay,
} from "./engine";

type Accent = "blue" | "ember" | "teal" | "plum";
type Theme = "light" | "dark";
type CompareMode = "rhyme" | "yesterday" | "none";

interface Tweaks {
  accent: Accent;
  density: "comfortable" | "compact";
  theme: Theme;
  compare: CompareMode;
}

const TWEAK_DEFAULTS: Tweaks = {
  accent: "blue",
  density: "comfortable",
  theme: "light",
  compare: "rhyme",
};

const SAMPLE = `Woke up heavy, kind of anxious about the deadline. The morning was rough — emails piled up before I even had coffee. Slow standup, I barely talked. Around noon I went for a walk in the park and things started to lift. Ran into a friend who'd just moved back; we laughed about something stupid for twenty minutes. The afternoon clicked — I got into a flow and the code finally worked. Dinner was calm, read a little before bed.`;

// Accent palette. Pure blue (#3B82F6) is the investor-ready default; the
// remaining three are warm-minded alternates, each chosen so their light-variant
// (70% mix with white) reads as a plausible "compare" shade in the chart.
const ACCENT_HEX: Record<Accent, string> = {
  blue: "#3B82F6",
  ember: "#EA580C",
  teal: "#0E7490",
  plum: "#7C3AED",
};

// Lighter companion hue (~45% value above the base) used for compare curves
// and the concentric donut secondary ring. Derived from ACCENT_HEX by mixing
// with white in the HSL space — we precompute so the renderer stays fast and
// the chart can't drift from the palette.
const ACCENT_SOFT_HEX: Record<Accent, string> = {
  blue: "#93C5FD",
  ember: "#FDBA74",
  teal: "#67E8F9",
  plum: "#C4B5FD",
};

// ═══════════════════════════════════════════════════════════════════════
// Root
// ═══════════════════════════════════════════════════════════════════════

export default function Dashboard() {
  const [text, setText] = useState(SAMPLE);
  const [tweaks, setTweaks] = useState<Tweaks>(TWEAK_DEFAULTS);
  const [nav, setNav] = useState("today");
  const [composerOpen, setComposerOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    // Scope accent + theme to the dashboard root, never mutate global <html>.
    // We propagate both the base hue and its soft companion so the donut, the
    // heatmap, and the compare-curve can derive a two-tone family without
    // having to import the HEX table at the call site.
    const el = rootRef.current;
    if (!el) return;
    el.style.setProperty("--accent", ACCENT_HEX[tweaks.accent]);
    el.style.setProperty("--accent-mid", ACCENT_SOFT_HEX[tweaks.accent]);
    el.classList.toggle("prudent-dark", tweaks.theme === "dark");
  }, [tweaks.accent, tweaks.theme]);

  const setTweak = <K extends keyof Tweaks>(k: K, v: Tweaks[K]) => {
    setTweaks((prev) => ({ ...prev, [k]: v }));
  };

  const { events, series } = useMemo(() => parseNarrative(text), [text]);
  const avg = useMemo(
    () => Math.round(series.reduce((a, b) => a + b.v, 0) / series.length),
    [series]
  );
  const peak = useMemo(
    () => series.reduce((a, b) => (b.v > a.v ? b : a), series[0] ?? { v: 50, t: 0 }),
    [series]
  );
  const trough = useMemo(
    () => series.reduce((a, b) => (b.v < a.v ? b : a), series[0] ?? { v: 50, t: 0 }),
    [series]
  );
  const history = useMemo(() => buildHistory(avg), [avg]);
  const rhyme = useMemo(() => findRhyme(history.slice(0, -1), series), [history, series]);

  const yesterday = useMemo(() => {
    const y = history[history.length - 2];
    if (!y) return null;
    return parseNarrative(y.text).series;
  }, [history]);

  const rhymeSeries = useMemo<Point[] | null>(() => {
    if (!rhyme) return null;
    const w = history.slice(rhyme.startIdx, rhyme.startIdx + 7);
    const targetAvg = w.reduce((a, d) => a + d.avg, 0) / w.length;
    const base = parseNarrative(w[3]?.text || "").series;
    const baseAvg = base.reduce((a, b) => a + b.v, 0) / base.length;
    return base.map((p) => ({ t: p.t, v: p.v - baseAvg + targetAvg }));
  }, [rhyme, history]);

  const compareSeries =
    tweaks.compare === "yesterday" ? yesterday : tweaks.compare === "rhyme" ? rhymeSeries : null;
  const compareLabel =
    tweaks.compare === "yesterday"
      ? "Yesterday"
      : tweaks.compare === "rhyme"
        ? "Rhyming week (day −" + (history[rhyme?.startIdx ?? 0]?.day ?? "?") + ")"
        : null;

  return (
    <div ref={rootRef} className="prudent-root">
      <div style={{ display: "flex", minHeight: "100vh", background: "var(--app-bg)" }}>
        <Sidebar nav={nav} setNav={setNav} onCompose={() => setComposerOpen(true)} />
        <main
          style={{
            flex: 1,
            padding: "16px 20px 24px 20px",
            display: "flex",
            flexDirection: "column",
            gap: 16,
            minWidth: 0,
          }}
        >
          <TopBar />
          <PageHeader events={events} />

          <div style={{ display: "grid", gridTemplateColumns: "340px 1fr", gap: 14 }}>
            <KeyMetrics
              series={series}
              events={events}
              history={history}
              avg={avg}
              peak={peak}
              trough={trough}
            />
            <DayTrajectory
              series={series}
              events={events}
              compareSeries={compareSeries}
              compareLabel={compareLabel}
              setCompare={(v) => setTweak("compare", v)}
              compareMode={tweaks.compare}
            />
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "1.4fr 1fr", gap: 14 }}>
            <RhymeHeatmap history={history} rhymeStart={rhyme?.startIdx} />
            <TagDonut events={events} />
          </div>

          <ThreadRibbon history={history} rhymeStart={rhyme?.startIdx} />

          <Footer />
        </main>

        {composerOpen && (
          <ComposerModal
            text={text}
            setText={setText}
            onClose={() => setComposerOpen(false)}
            events={events}
          />
        )}
        <TweaksPanel tweaks={tweaks} setTweak={setTweak} />
      </div>

      <style>{`
        .prudent-root {
          /* Airy warm-white canvas. The 4-point delta between --app-bg and
             --panel (FAFAFA → FFFFFF) is enough to read as a lifted card in
             daylight but stays invisible under color-deficient rendering. */
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
          /* Pure blue primary — replaces the old muted indigo. Keep both the
             saturated stroke (#3B82F6) and its soft pair (#93C5FD) so charts
             with two series can stay in-family rather than bleeding into
             secondary hues. */
          --accent: #3B82F6;
          --accent-mid: #93C5FD;
          --accent-soft: #DBEAFE;
          --accent-ink: #1D4ED8;
          /* Orange CTA (tailwind orange-500/600). Reserved for primary-action
             surfaces and "New" badges. Never applied to analytical strokes. */
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
          min-height: 100vh;
        }
        .prudent-root.prudent-dark {
          /* Warm near-black dark theme. The panel bg has a hint of
             warmth (#17191C) rather than pure neutral to avoid the cold
             "inverted screenshot" look of naive dark modes. */
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
          --warm-soft: #7C2D12;
          --rail: #0A0B0D;
          --rail-ink: #6B7280;
          --rail-active: #1F2328;
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
      `}</style>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════
// Sidebar
// ═══════════════════════════════════════════════════════════════════════

interface SidebarProps {
  nav: string;
  setNav: (id: string) => void;
  onCompose: () => void;
}

function Sidebar({ nav, setNav, onCompose }: SidebarProps) {
  const items = [
    { id: "today", label: "Today", hint: "Apr 17" },
    { id: "thread", label: "Thread", hint: "30d" },
    { id: "rhymes", label: "Rhymes", hint: "12", fresh: true },
    { id: "tags", label: "Tags" },
    { id: "patterns", label: "Patterns" },
    { id: "entries", label: "Entries", hint: "142" },
  ];
  const Ext = [
    { id: "engine", label: "Engine logs" },
    { id: "export", label: "Export" },
  ];

  return (
    <aside
      style={{
        display: "flex",
        height: "100vh",
        position: "sticky",
        top: 0,
        background: "var(--sidebar)",
        borderRight: "1px solid var(--line)",
      }}
    >
      {/* Icon rail — intentionally very dark (#1F2328) so the secondary nav
          reads as an airy white column next to it. The active glyph gets a
          filled square background in accent blue to match the reference. */}
      <div
        style={{
          width: 56,
          background: "var(--rail)",
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          padding: "14px 0 14px 0",
          gap: 4,
        }}
      >
        <div
          style={{
            width: 28,
            height: 28,
            background: "var(--accent)",
            borderRadius: 7,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            color: "#fff",
            fontWeight: 700,
            fontSize: 12,
            fontFamily: "var(--mono)",
            marginBottom: 10,
          }}
        >
          //
        </div>
        {[
          { id: "home", active: false },
          { id: "pulse", active: false },
          { id: "thread", active: true },
          { id: "tags", active: false },
          { id: "grid", active: false },
          { id: "people", active: false },
          { id: "library", active: false },
        ].map((g) => (
          <button
            key={g.id}
            style={{
              width: 32,
              height: 32,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              color: g.active ? "#fff" : "var(--rail-ink)",
              background: g.active ? "var(--accent)" : "transparent",
              borderRadius: 6,
              transition: "background 120ms ease",
            }}
          >
            <RailGlyph id={g.id} />
          </button>
        ))}
        <div style={{ flex: 1 }} />
        <button
          style={{
            width: 28,
            height: 28,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            color: "var(--rail-ink)",
            borderRadius: 6,
          }}
          title="Help"
        >
          <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
            <circle cx="8" cy="8" r="5.5" />
            <path d="M6.5 7a1.5 1.5 0 113 0c0 1-1.5 1-1.5 2M8 11.2v.1" />
          </svg>
        </button>
        <div
          style={{
            width: 26,
            height: 26,
            background: "linear-gradient(135deg, #F97316, #3B82F6)",
            borderRadius: "50%",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            color: "#fff",
            fontSize: 11,
            fontWeight: 700,
            marginTop: 4,
            border: "1px solid rgba(255,255,255,0.12)",
          }}
        >
          K
        </div>
      </div>
      <div style={{ width: 280, padding: "16px 14px", display: "flex", flexDirection: "column" }}>
        {/* 3-way segmented tab control (live / book / person). Modeled on the
            reference screenshot: pill track with one active icon. */}
        <div
          style={{
            display: "flex",
            background: "var(--hover)",
            borderRadius: 8,
            padding: 3,
            marginBottom: 16,
          }}
        >
          {[
            { id: "live", icon: "live" },
            { id: "book", icon: "book" },
            { id: "person", icon: "person" },
          ].map((t, i) => (
            <button
              key={t.id}
              style={{
                flex: 1,
                padding: "7px 0",
                borderRadius: 6,
                background: i === 0 ? "var(--panel)" : "transparent",
                color: i === 0 ? "var(--ink)" : "var(--muted)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                boxShadow: i === 0 ? "0 1px 2px rgba(20,22,26,0.08)" : "none",
                transition: "background 120ms ease",
              }}
              aria-label={t.id}
            >
              <SegIcon id={t.icon} />
            </button>
          ))}
        </div>

        <button
          onClick={onCompose}
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            background: "var(--ink)",
            color: "var(--app-bg)",
            padding: "10px 13px",
            borderRadius: 8,
            fontSize: 13,
            fontWeight: 500,
            marginBottom: 18,
          }}
        >
          <span style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <span style={{ fontSize: 14, lineHeight: 1 }}>＋</span> New entry
          </span>
          <span style={{ fontSize: 10, opacity: 0.55, fontFamily: "var(--mono)" }}>⌘N</span>
        </button>

        <SectionLabel>Spaces</SectionLabel>
        {items.map((it) => (
          <button
            key={it.id}
            onClick={() => setNav(it.id)}
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              padding: "9px 10px",
              borderRadius: 7,
              fontSize: 13,
              background: nav === it.id ? "var(--hover)" : "transparent",
              color: nav === it.id ? "var(--ink)" : "var(--muted)",
              fontWeight: nav === it.id ? 600 : 450,
              textAlign: "left",
              marginBottom: 1,
              transition: "background 100ms ease, color 100ms ease",
            }}
          >
            <span style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <NavGlyph id={it.id} active={nav === it.id} />
              {it.label}
            </span>
            {it.fresh ? (
              <span
                style={{
                  fontSize: 9,
                  background: "var(--warm)",
                  color: "#fff",
                  padding: "2px 7px",
                  borderRadius: 10,
                  fontWeight: 600,
                  letterSpacing: "0.02em",
                }}
              >
                New
              </span>
            ) : it.hint ? (
              <span className="mono" style={{ fontSize: 10, color: "var(--faint)" }}>
                {it.hint}
              </span>
            ) : null}
          </button>
        ))}

        <SectionLabel top={18}>Self services</SectionLabel>
        <NavLink label="Favourites" hint="4" />
        <NavLink label="Bookmarks" hint="12" />
        <NavLink label="Drafts" fresh />

        <SectionLabel top={18}>External</SectionLabel>
        {Ext.map((it) => (
          <button
            key={it.id}
            style={{
              display: "flex",
              alignItems: "center",
              gap: 10,
              padding: "9px 10px",
              fontSize: 13,
              color: "var(--muted)",
              textAlign: "left",
              fontWeight: 450,
            }}
          >
            <NavGlyph id={it.id} />
            {it.label}
          </button>
        ))}

        <div style={{ flex: 1 }} />
        <div
          style={{
            padding: "8px 0 2px 0",
            borderTop: "1px solid var(--line)",
            display: "flex",
            flexDirection: "column",
            gap: 2,
            marginTop: 10,
          }}
        >
          <button
            style={{
              display: "flex",
              alignItems: "center",
              gap: 10,
              padding: "8px 10px",
              fontSize: 13,
              color: "var(--muted)",
              textAlign: "left",
              fontWeight: 450,
            }}
          >
            <NavGlyph id="support" /> Support
          </button>
          <button
            style={{
              display: "flex",
              alignItems: "center",
              gap: 10,
              padding: "8px 10px",
              fontSize: 13,
              color: "var(--muted)",
              textAlign: "left",
              fontWeight: 450,
            }}
          >
            <NavGlyph id="settings" /> Settings
          </button>
        </div>
      </div>
    </aside>
  );
}

// Reusable uppercase section label. Section headers in the reference sit
// with 10px uppercase, 0.08em tracking, bold weight; we enforce that here so
// every group stays visually consistent even as the nav grows.
function SectionLabel({ children, top = 10 }: { children: React.ReactNode; top?: number }) {
  return (
    <div
      className="mono"
      style={{
        fontSize: 10,
        color: "var(--faint)",
        letterSpacing: "0.08em",
        padding: `${top}px 10px 8px 10px`,
        textTransform: "uppercase",
        fontWeight: 600,
      }}
    >
      {children}
    </div>
  );
}

// A small, auxiliary nav link used in Self-services / External sections. Kept
// inline rather than re-using the main `items` loop so the "fresh" badge and
// the hint shape can stay purely presentational.
function NavLink({ label, hint, fresh }: { label: string; hint?: string; fresh?: boolean }) {
  return (
    <button
      style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        padding: "9px 10px",
        borderRadius: 7,
        fontSize: 13,
        color: "var(--muted)",
        textAlign: "left",
        fontWeight: 450,
      }}
    >
      <span style={{ display: "flex", alignItems: "center", gap: 10 }}>
        <NavGlyph id={label.toLowerCase()} />
        {label}
      </span>
      {fresh ? (
        <span
          style={{
            fontSize: 9,
            background: "var(--warm)",
            color: "#fff",
            padding: "2px 7px",
            borderRadius: 10,
            fontWeight: 600,
            letterSpacing: "0.02em",
          }}
        >
          New
        </span>
      ) : hint ? (
        <span className="mono" style={{ fontSize: 10, color: "var(--faint)" }}>
          {hint}
        </span>
      ) : null}
    </button>
  );
}

// Thin stroked glyphs for the outer rail. Kept visually simple so they read
// as a single monochrome family against the dark rail.
function RailGlyph({ id }: { id: string }) {
  const common = { width: 16, height: 16, fill: "none", stroke: "currentColor", strokeWidth: 1.4 };
  const glyphs: Record<string, React.ReactElement> = {
    home: (
      <svg {...common} viewBox="0 0 16 16">
        <path d="M2.5 7.5L8 3l5.5 4.5V13H2.5z" />
        <path d="M6.5 13V9h3v4" />
      </svg>
    ),
    pulse: (
      <svg {...common} viewBox="0 0 16 16">
        <path d="M2 8h3l1.5-3 2 6 1.5-3H14" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    ),
    thread: (
      <svg {...common} viewBox="0 0 16 16">
        <path d="M3 3h10v4H3zM3 9h10v4H3z" />
        <path d="M5 5h1M5 11h1" />
      </svg>
    ),
    tags: (
      <svg {...common} viewBox="0 0 16 16">
        <path d="M3 3h5l5 5-5 5-5-5V3z" />
        <circle cx="5.5" cy="5.5" r="0.8" fill="currentColor" />
      </svg>
    ),
    grid: (
      <svg {...common} viewBox="0 0 16 16">
        <rect x="2.5" y="2.5" width="4.5" height="4.5" />
        <rect x="9" y="2.5" width="4.5" height="4.5" />
        <rect x="2.5" y="9" width="4.5" height="4.5" />
        <rect x="9" y="9" width="4.5" height="4.5" />
      </svg>
    ),
    people: (
      <svg {...common} viewBox="0 0 16 16">
        <circle cx="6" cy="6" r="2.2" />
        <path d="M2.5 13c.5-2 1.8-3 3.5-3s3 1 3.5 3" />
        <circle cx="11.5" cy="5.5" r="1.8" />
      </svg>
    ),
    library: (
      <svg {...common} viewBox="0 0 16 16">
        <path d="M3 3v10M6 3v10M9 3v10M12 3v10" />
      </svg>
    ),
  };
  return glyphs[id] ?? glyphs.grid;
}

// Segmented tab icons (live / book / person).
function SegIcon({ id }: { id: string }) {
  const common = { width: 14, height: 14, fill: "none", stroke: "currentColor", strokeWidth: 1.4 };
  const g: Record<string, React.ReactElement> = {
    live: (
      <svg {...common} viewBox="0 0 16 16">
        <circle cx="8" cy="8" r="1.5" fill="currentColor" stroke="none" />
        <path d="M4.5 11.5a5 5 0 010-7M11.5 11.5a5 5 0 000-7" />
      </svg>
    ),
    book: (
      <svg {...common} viewBox="0 0 16 16">
        <path d="M3 3h4a2 2 0 012 2v8a2 2 0 00-2-2H3zM13 3H9a2 2 0 00-2 2v8a2 2 0 012-2h4z" />
      </svg>
    ),
    person: (
      <svg {...common} viewBox="0 0 16 16">
        <circle cx="8" cy="5.5" r="2.2" />
        <path d="M3 13c.5-2.5 2.4-4 5-4s4.5 1.5 5 4" />
      </svg>
    ),
  };
  return g[id] ?? g.live;
}

function NavGlyph({ id, active }: { id: string; active?: boolean }) {
  const color = active ? "var(--ink)" : "var(--muted)";
  const common = { width: 14, height: 14, color };
  const m: Record<string, React.ReactElement> = {
    today: (
      <svg {...common} viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
        <circle cx="8" cy="8" r="5.5" />
        <path d="M8 4.5v3.5l2.2 1.5" />
      </svg>
    ),
    thread: (
      <svg {...common} viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
        <path d="M2 11l3-2 3 2 3-4 3 3" />
      </svg>
    ),
    rhymes: (
      <svg {...common} viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
        <path d="M3 6c1.5-2 4-2 5 0s3.5 2 5 0M3 11c1.5-2 4-2 5 0s3.5 2 5 0" />
      </svg>
    ),
    tags: (
      <svg {...common} viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
        <path d="M3 3h5l5 5-5 5-5-5V3z" />
        <circle cx="5.5" cy="5.5" r="0.8" fill="currentColor" />
      </svg>
    ),
    patterns: (
      <svg {...common} viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
        <rect x="2.5" y="2.5" width="4" height="4" />
        <rect x="9.5" y="2.5" width="4" height="4" />
        <rect x="2.5" y="9.5" width="4" height="4" />
        <rect x="9.5" y="9.5" width="4" height="4" />
      </svg>
    ),
    entries: (
      <svg {...common} viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
        <path d="M3 2.5h8l2 2v9H3z" />
        <path d="M5.5 7h5M5.5 10h5M5.5 4.5h3" />
      </svg>
    ),
    engine: (
      <svg {...common} viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
        <circle cx="8" cy="8" r="2" />
        <path d="M8 2.5v2M8 11.5v2M13.5 8h-2M4.5 8h-2" />
      </svg>
    ),
    export: (
      <svg {...common} viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
        <path d="M8 10V2m0 0l-3 3m3-3l3 3M3 12v2h10v-2" />
      </svg>
    ),
    support: (
      <svg {...common} viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
        <circle cx="8" cy="8" r="5.5" />
        <path d="M6.5 7a1.5 1.5 0 113 0c0 1-1.5 1-1.5 2M8 11.2v.1" />
      </svg>
    ),
    settings: (
      <svg {...common} viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
        <circle cx="8" cy="8" r="2" />
        <path d="M8 1.5v2M8 12.5v2M1.5 8h2M12.5 8h2" />
      </svg>
    ),
  };
  return m[id] || <span style={{ width: 14 }} />;
}

// ═══════════════════════════════════════════════════════════════════════
// Top bar
// ═══════════════════════════════════════════════════════════════════════

function TopBar() {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        fontSize: 13,
        paddingBottom: 2,
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 6, color: "var(--muted)" }}>
        <button
          style={{ color: "var(--faint)", padding: "4px 6px", borderRadius: 5 }}
          aria-label="Back"
        >
          <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
            <path d="M10 3.5L5.5 8l4.5 4.5" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </button>
        <button
          style={{ color: "var(--faint)", padding: "4px 6px", borderRadius: 5 }}
          aria-label="Forward"
        >
          <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
            <path d="M6 3.5L10.5 8 6 12.5" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </button>
        {/* Breadcrumb: "Analytics" chip › current page chip. Matching the
            reference where the current page chip has an icon + bold label. */}
        <span
          style={{
            marginLeft: 4,
            padding: "4px 10px",
            borderRadius: 6,
            background: "var(--hover)",
            color: "var(--muted)",
            fontWeight: 500,
          }}
        >
          Analytics
        </span>
        <span style={{ color: "var(--faint)", fontSize: 14, lineHeight: 1 }}>›</span>
        <span
          style={{
            color: "var(--ink)",
            fontWeight: 500,
            display: "inline-flex",
            alignItems: "center",
            gap: 7,
            padding: "4px 10px 4px 8px",
            borderRadius: 6,
            background: "var(--hover)",
          }}
        >
          <span
            style={{
              display: "inline-block",
              width: 8,
              height: 8,
              background: "var(--accent)",
              borderRadius: 2,
            }}
          />
          Today · Wed Apr 17
        </span>
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 4, color: "var(--muted)" }}>
        <button
          style={{
            padding: "6px 8px",
            borderRadius: 6,
          }}
          title="Search"
        >
          <SvgIcon path="M7 3a4 4 0 014 4 4 4 0 01-4 4 4 4 0 01-4-4 4 4 0 014-4zm3 7l3 3" />
        </button>
        <button
          style={{ padding: "6px 8px", position: "relative", borderRadius: 6 }}
          title="Notifications"
        >
          <SvgIcon path="M3.5 11h9l-1-2V6a3.5 3.5 0 00-7 0v3l-1 2zM6 12a2 2 0 004 0" />
          <span
            style={{
              position: "absolute",
              top: 3,
              right: 4,
              width: 7,
              height: 7,
              background: "var(--warm)",
              borderRadius: "50%",
              border: "1.5px solid var(--panel)",
            }}
          />
        </button>
        <div
          style={{
            width: 28,
            height: 28,
            borderRadius: "50%",
            background: "linear-gradient(135deg, #F97316 0%, #3B82F6 100%)",
            border: "1px solid var(--line-mid)",
            marginLeft: 4,
          }}
        />
      </div>
    </div>
  );
}

function SvgIcon({ path }: { path: string }) {
  return (
    <svg
      width="15"
      height="15"
      viewBox="0 0 15 15"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.3"
      strokeLinecap="round"
    >
      <path d={path} />
    </svg>
  );
}

// ═══════════════════════════════════════════════════════════════════════
// Page header (title + filters row)
// ═══════════════════════════════════════════════════════════════════════

function PageHeader({ events }: { events: Event[] }) {
  return (
    <div>
      <div
        style={{
          display: "flex",
          alignItems: "flex-end",
          justifyContent: "space-between",
          marginBottom: 16,
          gap: 12,
        }}
      >
        <div style={{ minWidth: 0 }}>
          <h1
            style={{
              fontSize: 30,
              fontWeight: 600,
              letterSpacing: "-0.02em",
              color: "var(--ink)",
              margin: 0,
              lineHeight: 1.1,
            }}
          >
            Today
          </h1>
          <div
            style={{
              fontSize: 13,
              color: "var(--muted)",
              marginTop: 6,
              fontWeight: 400,
            }}
          >
            Narrative parsed at 9:47 am ·{" "}
            <span className="tnum" style={{ color: "var(--ink)", fontWeight: 500 }}>
              {events.length}
            </span>{" "}
            events · baseline valence{" "}
            <span className="tnum" style={{ color: "var(--ink)", fontWeight: 500 }}>
              50
            </span>
          </div>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <Chip label="Default" caret />
          {/* Primary CTA — orange #F97316 per reference. Hover darkens to the
              strong variant; keep the plus sign as a crisp glyph rather than
              an emoji to avoid platform-specific rendering. */}
          <button
            style={{
              display: "flex",
              alignItems: "center",
              gap: 6,
              background: "var(--warm)",
              color: "#fff",
              padding: "9px 14px",
              borderRadius: 8,
              fontSize: 13,
              fontWeight: 500,
              boxShadow: "0 1px 2px rgba(234,88,12,0.20), inset 0 -1px 0 rgba(0,0,0,0.08)",
            }}
          >
            <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M6 2v8M2 6h8" strokeLinecap="round" />
            </svg>
            Add view
          </button>
        </div>
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
        <DateChip from="Wed, Apr 17" to="9:47 am" />
        <Chip label="All entries" caret />
        <Chip label="All tags" caret />
        <Chip label="All people" caret />
        <Chip label="More" caret />
        <div style={{ flex: 1 }} />
        <Chip label="···" />
      </div>
    </div>
  );
}

// A small filter/control chip. Size, radius and weight are intentionally
// smaller than the primary CTA so the chips recede visually while still being
// interactive. 7px radius matches the reference's softer chip corners.
function Chip({ label, caret, active }: { label: string; caret?: boolean; active?: boolean }) {
  return (
    <button
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 6,
        padding: "6px 11px",
        fontSize: 12,
        background: active ? "var(--hover)" : "var(--panel)",
        border: "1px solid var(--line-mid)",
        borderRadius: 7,
        color: active ? "var(--ink)" : "var(--muted)",
        fontWeight: 500,
        lineHeight: 1.2,
      }}
    >
      {label}
      {caret && (
        <svg width="9" height="9" viewBox="0 0 9 9" fill="none" stroke="currentColor" strokeWidth="1.3" style={{ opacity: 0.7 }}>
          <path d="M2 3.5L4.5 6 7 3.5" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      )}
    </button>
  );
}

function DateChip({ from, to }: { from: string; to: string }) {
  return (
    <div
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 8,
        padding: "6px 11px",
        fontSize: 12,
        background: "var(--panel)",
        border: "1px solid var(--line-mid)",
        borderRadius: 7,
        color: "var(--ink)",
        fontWeight: 500,
      }}
    >
      <svg width="13" height="13" viewBox="0 0 15 15" fill="none" stroke="currentColor" strokeWidth="1.3">
        <rect x="2" y="3" width="11" height="10" rx="1" />
        <path d="M2 6h11M5 1.5v3M10 1.5v3" />
      </svg>
      <span>{from}</span>
      <span style={{ color: "var(--faint)" }}>→</span>
      <span>{to}</span>
      <svg width="9" height="9" viewBox="0 0 9 9" fill="none" stroke="currentColor" strokeWidth="1.3" style={{ opacity: 0.55, marginLeft: 2 }}>
        <path d="M2 3.5L4.5 6 7 3.5" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════
// Key metrics column
// ═══════════════════════════════════════════════════════════════════════

interface KeyMetricsProps {
  series: Point[];
  events: Event[];
  history: HistoryDay[];
  avg: number;
  peak: Point;
  trough: Point;
}

function KeyMetrics({ series, events, history, avg, peak, trough }: KeyMetricsProps) {
  const lastN = history.slice(-14).map((d) => d.avg);
  const upliftCount = events.filter((e) => e.delta > 0).length;
  const downCount = events.filter((e) => e.delta < 0).length;
  const avgCompare = Math.round(history.slice(-8, -1).reduce((a, b) => a + b.avg, 0) / 7);
  const variance = Math.round(
    Math.sqrt(series.reduce((a, b) => a + (b.v - avg) ** 2, 0) / series.length)
  );

  return (
    <section
      style={{
        background: "var(--panel)",
        border: "1px solid var(--line)",
        borderRadius: 10,
        padding: "14px 16px 18px 16px",
        display: "flex",
        flexDirection: "column",
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          marginBottom: 14,
        }}
      >
        <div style={{ fontSize: 14, fontWeight: 600 }}>Key metrics</div>
        <Chip label="All entries" caret />
      </div>

      <Metric
        label="Avg valence"
        value={avg}
        unit="/100"
        delta={avg - avgCompare}
        deltaSuffix="% vs 7d"
        sparkline={lastN}
        stroke="var(--accent)"
        fill
      />
      <Metric
        label="Uplift events"
        value={upliftCount}
        unit="ev"
        delta={upliftCount - downCount}
        deltaSuffix="net"
        sparklineCustom={<EventsSpark events={events} />}
      />
      <Metric
        label="Volatility"
        value={variance}
        unit="σ"
        delta={-1.58}
        deltaSuffix="% vs wk"
        sparklineCustom={<VolatilitySpark series={series} stroke="var(--warm)" />}
      />
      <Metric
        label="Peak · trough"
        value={`${Math.round(peak.v)} · ${Math.round(trough.v)}`}
        unit="span"
        delta={Math.round(peak.v - trough.v)}
        deltaSuffix="range"
        deltaKind="neutral"
        sparklineCustom={<PeakTroughSpark series={series} peak={peak} trough={trough} />}
        noborder
      />
    </section>
  );
}

interface MetricProps {
  label: string;
  value: number | string;
  unit: string;
  delta: number;
  deltaSuffix: string;
  sparkline?: number[];
  sparklineCustom?: React.ReactNode;
  stroke?: string;
  fill?: boolean;
  deltaKind?: "neutral";
  noborder?: boolean;
}

function Metric({
  label,
  value,
  unit,
  delta,
  deltaSuffix,
  sparkline,
  sparklineCustom,
  stroke = "var(--accent)",
  fill = false,
  deltaKind,
  noborder,
}: MetricProps) {
  const up: boolean | null = deltaKind === "neutral" ? null : delta >= 0;
  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "1fr 120px",
        gap: 14,
        alignItems: "center",
        padding: "14px 0",
        borderBottom: noborder ? "none" : "1px solid var(--line)",
      }}
    >
      <div>
        <div style={{ fontSize: 11, color: "var(--muted)", marginBottom: 6, fontWeight: 500 }}>
          {label}
        </div>
        <div style={{ display: "flex", alignItems: "baseline", gap: 6 }}>
          <div
            className="tnum"
            style={{
              fontSize: 28,
              fontWeight: 600,
              letterSpacing: "-0.02em",
              color: "var(--ink)",
            }}
          >
            {value}
          </div>
          <div style={{ fontSize: 11, color: "var(--faint)" }}>{unit}</div>
        </div>
        <div
          className="tnum"
          style={{
            fontSize: 11,
            marginTop: 4,
            color: up === null ? "var(--muted)" : up ? "var(--green)" : "var(--warm)",
            fontWeight: 500,
          }}
        >
          {up === null ? "◦" : up ? "▲" : "▼"}{" "}
          {Math.abs(delta).toFixed(delta % 1 === 0 ? 0 : 2)}{" "}
          <span style={{ color: "var(--faint)", fontWeight: 400 }}>{deltaSuffix}</span>
        </div>
      </div>
      <div style={{ width: 120, height: 52, display: "flex", alignItems: "center" }}>
        {sparklineCustom || (
          <Sparkline data={sparkline ?? []} stroke={stroke} fill={fill} width={120} height={48} />
        )}
      </div>
    </div>
  );
}

interface SparklineProps {
  data: number[];
  stroke?: string;
  fill?: boolean;
  width?: number;
  height?: number;
}

function Sparkline({
  data,
  stroke = "var(--accent)",
  fill = false,
  width = 120,
  height = 40,
}: SparklineProps) {
  if (!data || data.length < 2) return null;
  const min = Math.min(...data);
  const max = Math.max(...data);
  const pad = 4;
  const W = width;
  const H = height - pad * 2;
  const step = W / (data.length - 1);
  const y = (v: number) => pad + (1 - (v - min) / (max - min || 1)) * H;
  const pts = data.map((v, i) => [i * step, y(v)] as const);
  let d = `M ${pts[0][0]} ${pts[0][1]}`;
  for (let i = 1; i < pts.length; i++) {
    const [x0, y0] = pts[i - 1];
    const [x1, y1] = pts[i];
    const mx = (x0 + x1) / 2;
    d += ` C ${mx} ${y0}, ${mx} ${y1}, ${x1} ${y1}`;
  }
  const fillPath = `${d} L ${W} ${height} L 0 ${height} Z`;
  const last = pts[pts.length - 1];
  return (
    <svg width={width} height={height} style={{ display: "block" }}>
      {fill && <path d={fillPath} fill={stroke} opacity="0.12" />}
      <path d={d} fill="none" stroke={stroke} strokeWidth="1.5" strokeLinecap="round" />
      <circle cx={last[0]} cy={last[1]} r="2.5" fill={stroke} />
    </svg>
  );
}

function EventsSpark({ events }: { events: Event[] }) {
  const maxT = 16 * 60;
  const width = 120;
  const height = 48;
  return (
    <svg width={width} height={height}>
      <line x1="0" x2={width} y1={height / 2} y2={height / 2} stroke="currentColor" opacity="0.08" />
      {events.map((e, i) => {
        const x = (e.time / maxT) * width;
        const up = e.delta > 0;
        const mag = Math.min(1, Math.abs(e.delta) / 20);
        const h = mag * (height / 2 - 2);
        return (
          <rect
            key={i}
            x={x - 1.5}
            y={up ? height / 2 - h : height / 2}
            width="3"
            height={h}
            fill={up ? "var(--green)" : "var(--warm)"}
            rx="1"
          />
        );
      })}
    </svg>
  );
}

function VolatilitySpark({ series, stroke }: { series: Point[]; stroke: string }) {
  const data: number[] = [];
  const w = 12;
  for (let i = w; i < series.length; i += Math.floor(series.length / 12)) {
    const slice = series.slice(i - w, i).map((p) => p.v);
    const mean = slice.reduce((a, b) => a + b, 0) / slice.length;
    const std = Math.sqrt(slice.reduce((a, b) => a + (b - mean) ** 2, 0) / slice.length);
    data.push(std);
  }
  return <Sparkline data={data} stroke={stroke} fill width={120} height={48} />;
}

function PeakTroughSpark({
  series,
  peak,
  trough,
}: {
  series: Point[];
  peak: Point;
  trough: Point;
}) {
  const width = 120;
  const height = 48;
  const min = 0;
  const max = 100;
  const pts = series
    .filter((_, i) => i % 5 === 0)
    .map((p, i, arr) => [
      (i / (arr.length - 1)) * width,
      (1 - (p.v - min) / (max - min)) * height,
    ] as const);
  let d = `M ${pts[0][0]} ${pts[0][1]}`;
  for (let i = 1; i < pts.length; i++) d += ` L ${pts[i][0]} ${pts[i][1]}`;
  const maxT = 16 * 60;
  const px = (peak.t / maxT) * width;
  const tx = (trough.t / maxT) * width;
  return (
    <svg width={width} height={height}>
      <path d={d} fill="none" stroke="var(--muted)" strokeWidth="1" opacity="0.6" />
      <circle cx={px} cy={(1 - peak.v / 100) * height} r="3" fill="var(--green)" />
      <circle cx={tx} cy={(1 - trough.v / 100) * height} r="3" fill="var(--warm)" />
    </svg>
  );
}

// ═══════════════════════════════════════════════════════════════════════
// Day Trajectory — main chart
// ═══════════════════════════════════════════════════════════════════════

interface DayTrajectoryProps {
  series: Point[];
  events: Event[];
  compareSeries: Point[] | null;
  compareLabel: string | null;
  setCompare: (v: CompareMode) => void;
  compareMode: CompareMode;
}

function DayTrajectory({
  series,
  events,
  compareSeries,
  compareLabel,
  setCompare,
  compareMode,
}: DayTrajectoryProps) {
  const [hover, setHover] = useState<{ t: number; v: number; x: number; y: number } | null>(null);
  const wrapRef = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(780);
  useEffect(() => {
    if (!wrapRef.current) return;
    const ro = new ResizeObserver((entries) => {
      for (const e of entries) setWidth(Math.max(500, e.contentRect.width));
    });
    ro.observe(wrapRef.current);
    return () => ro.disconnect();
  }, []);

  return (
    <section
      style={{
        background: "var(--panel)",
        border: "1px solid var(--line)",
        borderRadius: 10,
        padding: "14px 16px 16px 16px",
        minWidth: 0,
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          marginBottom: 6,
        }}
      >
        <div>
          <div style={{ fontSize: 14, fontWeight: 600 }}>Valence over time</div>
          <div style={{ fontSize: 11, color: "var(--muted)", marginTop: 2 }}>
            Integrated trajectory · 5-min resolution · narrative + comparison
          </div>
        </div>
        <div style={{ display: "flex", gap: 6 }}>
          <button
            onClick={() => setCompare(compareMode === "rhyme" ? "yesterday" : "rhyme")}
            style={{
              display: "flex",
              alignItems: "center",
              gap: 6,
              padding: "6px 10px",
              fontSize: 12,
              background: "var(--panel)",
              border: "1px solid var(--line-mid)",
              borderRadius: 7,
              color: "var(--muted)",
              fontWeight: 500,
            }}
          >
            <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.3">
              <path d="M2 4h8l-2-2M10 8H2l2 2" />
            </svg>
            Compare ·{" "}
            {compareMode === "yesterday"
              ? "Yesterday"
              : compareMode === "rhyme"
                ? "Rhyming week"
                : "None"}
          </button>
          <Chip label="Share" />
        </div>
      </div>

      <div ref={wrapRef} style={{ position: "relative", marginTop: 8 }}>
        <TrajectoryChart
          series={series}
          events={events}
          compareSeries={compareSeries}
          width={width}
          height={280}
          hover={hover}
          setHover={setHover}
        />
      </div>

      <div
        style={{
          display: "flex",
          gap: 18,
          paddingTop: 6,
          borderTop: "1px solid var(--line)",
          marginTop: 4,
          fontSize: 12,
          color: "var(--muted)",
        }}
      >
        <LegendDot color="var(--accent)" label="Today · narrative" />
        {compareSeries && compareLabel && (
          <LegendDot color="var(--warm)" label={compareLabel} dashed />
        )}
        <LegendDot color="var(--green)" label="Uplift event" dotOnly />
        <LegendDot color="var(--warm)" label="Downturn event" dotOnly />
      </div>
    </section>
  );
}

function LegendDot({
  color,
  label,
  dashed,
  dotOnly,
}: {
  color: string;
  label: string;
  dashed?: boolean;
  dotOnly?: boolean;
}) {
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
      {dotOnly ? (
        <span
          style={{
            width: 6,
            height: 6,
            background: color,
            borderRadius: "50%",
            display: "inline-block",
          }}
        />
      ) : (
        <svg width="18" height="6">
          <line
            x1="0"
            x2="18"
            y1="3"
            y2="3"
            stroke={color}
            strokeWidth="2"
            strokeDasharray={dashed ? "3 2" : ""}
          />
        </svg>
      )}
      <span>{label}</span>
    </span>
  );
}

interface TrajectoryChartProps {
  series: Point[];
  events: Event[];
  compareSeries: Point[] | null;
  width: number;
  height: number;
  hover: { t: number; v: number; x: number; y: number } | null;
  setHover: (h: { t: number; v: number; x: number; y: number } | null) => void;
}

function TrajectoryChart({
  series,
  events,
  compareSeries,
  width,
  height,
  hover,
  setHover,
}: TrajectoryChartProps) {
  const pad = { top: 14, right: 18, bottom: 28, left: 30 };
  const W = width - pad.left - pad.right;
  const H = height - pad.top - pad.bottom;
  const maxT = 16 * 60;
  const xAt = (t: number) => pad.left + (t / maxT) * W;
  const yAt = (v: number) => pad.top + (1 - v / 100) * H;

  const gridY = [0, 25, 50, 75, 100];
  const gridX = [0, 3 * 60, 6 * 60, 9 * 60, 12 * 60, 15 * 60];

  const smooth = (pts: Point[]) => {
    if (pts.length < 2) return "";
    let d = `M ${xAt(pts[0].t)} ${yAt(pts[0].v)}`;
    for (let i = 1; i < pts.length; i++) {
      const x0 = xAt(pts[i - 1].t);
      const y0 = yAt(pts[i - 1].v);
      const x1 = xAt(pts[i].t);
      const y1 = yAt(pts[i].v);
      const mx = (x0 + x1) / 2;
      d += ` C ${mx} ${y0}, ${mx} ${y1}, ${x1} ${y1}`;
    }
    return d;
  };

  const todayPath = smooth(series);
  const comparePath = compareSeries ? smooth(compareSeries) : "";
  const areaPath = series.length
    ? `${todayPath} L ${xAt(series[series.length - 1].t)} ${yAt(0)} L ${xAt(series[0].t)} ${yAt(0)} Z`
    : "";

  const gradId = "prudentTodayGrad";

  const onMove = (e: React.MouseEvent<SVGSVGElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const t = ((x - pad.left) / W) * maxT;
    if (t < 0 || t > maxT) {
      setHover(null);
      return;
    }
    let best = series[0];
    let bestD = Infinity;
    for (const p of series) {
      const d = Math.abs(p.t - t);
      if (d < bestD) {
        bestD = d;
        best = p;
      }
    }
    setHover({ t: best.t, v: best.v, x: xAt(best.t), y: yAt(best.v) });
  };

  return (
    <svg
      width={width}
      height={height}
      onMouseMove={onMove}
      onMouseLeave={() => setHover(null)}
      style={{ display: "block", cursor: "crosshair" }}
    >
      <defs>
        <linearGradient id={gradId} x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stopColor="var(--accent)" stopOpacity="0.18" />
          <stop offset="100%" stopColor="var(--accent)" stopOpacity="0" />
        </linearGradient>
      </defs>

      {gridY.map((v) => (
        <g key={v}>
          <line
            x1={pad.left}
            x2={pad.left + W}
            y1={yAt(v)}
            y2={yAt(v)}
            stroke="var(--line)"
            strokeWidth="1"
            strokeDasharray={v === 0 || v === 100 ? "" : "3 3"}
            opacity={v === 50 ? 0.9 : 0.6}
          />
          <text
            x={pad.left - 8}
            y={yAt(v) + 3}
            textAnchor="end"
            fontSize="10"
            fill="var(--faint)"
            className="tnum"
          >
            {v}
          </text>
        </g>
      ))}

      {gridX.map((t) => (
        <text
          key={t}
          x={xAt(t)}
          y={pad.top + H + 16}
          textAnchor="middle"
          fontSize="10"
          fill="var(--faint)"
        >
          {formatHour(t)}
        </text>
      ))}

      <path d={areaPath} fill={`url(#${gradId})`} />

      {compareSeries && (
        <path
          d={comparePath}
          fill="none"
          stroke="var(--warm)"
          strokeWidth="1.5"
          strokeDasharray="4 3"
          opacity="0.85"
        />
      )}

      <path d={todayPath} fill="none" stroke="var(--accent)" strokeWidth="2" strokeLinecap="round" />

      {events.map((ev, i) => {
        const val = interp(series, ev.time);
        const up = ev.delta > 0;
        const col = up ? "var(--green)" : "var(--warm)";
        return (
          <g key={i}>
            <line
              x1={xAt(ev.time)}
              x2={xAt(ev.time)}
              y1={yAt(val)}
              y2={yAt(val) - 14 - (i % 2) * 6}
              stroke={col}
              strokeWidth="0.8"
              opacity="0.5"
            />
            <circle
              cx={xAt(ev.time)}
              cy={yAt(val)}
              r="3.5"
              fill="var(--panel)"
              stroke={col}
              strokeWidth="1.5"
            />
            <text
              x={xAt(ev.time)}
              y={yAt(val) - 18 - (i % 2) * 6}
              textAnchor="middle"
              fontSize="9"
              fill={col}
              className="tnum"
              fontWeight="600"
            >
              {up ? "+" : ""}
              {ev.delta.toFixed(0)}
            </text>
          </g>
        );
      })}

      {hover && (
        <g>
          <line
            x1={hover.x}
            x2={hover.x}
            y1={pad.top}
            y2={pad.top + H}
            stroke="var(--ink)"
            strokeWidth="1"
            opacity="0.18"
            strokeDasharray="2 2"
          />
          <circle cx={hover.x} cy={hover.y} r="5" fill="var(--accent)" stroke="var(--panel)" strokeWidth="2" />
          <g>
            <rect
              x={Math.min(width - 100, hover.x + 8)}
              y={Math.max(pad.top, hover.y - 32)}
              width="92"
              height="26"
              rx="4"
              fill="var(--ink)"
            />
            <text
              x={Math.min(width - 100, hover.x + 8) + 46}
              y={Math.max(pad.top, hover.y - 32) + 11}
              textAnchor="middle"
              fontSize="10"
              fill="var(--app-bg)"
              className="tnum"
              fontWeight="600"
            >
              {formatHour(hover.t, true)}
            </text>
            <text
              x={Math.min(width - 100, hover.x + 8) + 46}
              y={Math.max(pad.top, hover.y - 32) + 22}
              textAnchor="middle"
              fontSize="10"
              fill="var(--faint)"
              className="tnum"
            >
              valence {Math.round(hover.v)}
            </text>
          </g>
        </g>
      )}
    </svg>
  );
}

function interp(pts: Point[], t: number): number {
  if (!pts.length) return 50;
  if (t <= pts[0].t) return pts[0].v;
  if (t >= pts[pts.length - 1].t) return pts[pts.length - 1].v;
  for (let i = 1; i < pts.length; i++) {
    if (pts[i].t >= t) {
      const a = pts[i - 1];
      const b = pts[i];
      const k = (t - a.t) / (b.t - a.t || 1);
      return a.v + k * (b.v - a.v);
    }
  }
  return 50;
}

function formatHour(minutes: number, full = false): string {
  const totalMin = 7 * 60 + minutes;
  const h24 = Math.floor(totalMin / 60) % 24;
  const m = totalMin % 60;
  const ampm = h24 >= 12 ? "PM" : "AM";
  const h12 = ((h24 + 11) % 12) + 1;
  if (full) return `${h12}:${m.toString().padStart(2, "0")} ${ampm}`;
  return `${h12} ${ampm}`;
}

// ═══════════════════════════════════════════════════════════════════════
// Rhyme heatmap
// ═══════════════════════════════════════════════════════════════════════

function RhymeHeatmap({
  history,
  rhymeStart,
}: {
  history: HistoryDay[];
  rhymeStart: number | undefined;
}) {
  const days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
  const week = history.slice(-7);

  const cells = week.map((d) => {
    let seed = (d.day + 17) * 37;
    const rand = () => {
      seed = (seed * 9301 + 49297) % 233280;
      return seed / 233280;
    };
    const base = d.avg / 100;
    return Array.from({ length: 12 }, (_, col) => {
      const tn = col / 11;
      const shape = 0.35 * Math.sin(tn * Math.PI - 0.4) + 0.15 * Math.cos(tn * Math.PI * 2);
      const v = base * 0.6 + shape * 0.35 + (rand() - 0.5) * 0.15;
      return { v: Math.max(0, Math.min(1, v)), day: d.day };
    });
  });

  const isRhymeRow = (row: number): boolean => {
    if (rhymeStart === null || rhymeStart === undefined) return false;
    const histIdx = history.length - 7 + row;
    return histIdx >= rhymeStart && histIdx < rhymeStart + 7;
  };

  const hours = Array.from({ length: 12 }, (_, i) => {
    const hr = (8 + i) % 12 === 0 ? 12 : (8 + i) % 12;
    const suf = i + 8 < 12 ? "AM" : "PM";
    return `${hr}${suf}`;
  });

  const accent = "#4c63d9";
  const colorFor = (v: number) => {
    if (v < 0.15) return { bg: "transparent", border: "var(--line-mid)", text: "var(--faint)" };
    if (v < 0.35) return { bg: "rgba(76,99,217,0.12)", border: "transparent", text: "var(--ink)" };
    if (v < 0.55) return { bg: "rgba(76,99,217,0.30)", border: "transparent", text: "var(--ink)" };
    if (v < 0.75) return { bg: "rgba(76,99,217,0.55)", border: "transparent", text: "#fff" };
    return { bg: accent, border: "transparent", text: "#fff" };
  };

  return (
    <section
      style={{
        background: "var(--panel)",
        border: "1px solid var(--line)",
        borderRadius: 10,
        padding: "14px 16px 14px 16px",
        minWidth: 0,
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          marginBottom: 10,
        }}
      >
        <div>
          <div style={{ fontSize: 14, fontWeight: 600 }}>Busiest valence</div>
          <div style={{ fontSize: 11, color: "var(--muted)", marginTop: 2 }}>
            Last 7 days · hour-of-day intensity
          </div>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 11, color: "var(--muted)" }}>
            <span>0</span>
            <div style={{ display: "flex" }}>
              {[0.08, 0.2, 0.4, 0.65, 1].map((s, i) => (
                <div key={i} style={{ width: 14, height: 10, background: `rgba(76,99,217,${s})` }} />
              ))}
            </div>
            <span>100</span>
          </div>
          <Chip label="New chats" caret />
        </div>
      </div>

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "36px repeat(12, 1fr)",
          gap: 4,
          alignItems: "center",
        }}
      >
        <div />
        {cells.map((row, ri) => (
          <Fragment key={ri}>
            <div
              style={{
                fontSize: 11,
                color: isRhymeRow(ri) ? "var(--warm)" : "var(--muted)",
                fontWeight: isRhymeRow(ri) ? 600 : 500,
                textAlign: "right",
                paddingRight: 6,
              }}
            >
              {days[ri]}
            </div>
            {row.map((cell, ci) => {
              const c = colorFor(cell.v);
              const val = Math.round(cell.v * 10);
              return (
                <div
                  key={ci}
                  style={{
                    aspectRatio: "1.4",
                    background: c.bg,
                    border:
                      c.border === "transparent" ? "1px solid transparent" : `1px dashed ${c.border}`,
                    color: c.text,
                    borderRadius: 5,
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    fontSize: 11,
                    fontWeight: 500,
                    fontVariantNumeric: "tabular-nums",
                    boxShadow: isRhymeRow(ri) ? "inset 0 0 0 1px var(--warm-soft)" : "none",
                  }}
                >
                  {val}
                </div>
              );
            })}
          </Fragment>
        ))}
        <div />
        {hours.map((h, i) => (
          <div
            key={i}
            style={{
              fontSize: 9.5,
              color: "var(--faint)",
              textAlign: "center",
              paddingTop: 4,
              fontVariantNumeric: "tabular-nums",
            }}
          >
            {h}
          </div>
        ))}
      </div>

      {rhymeStart !== null && rhymeStart !== undefined && (
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 8,
            marginTop: 12,
            padding: "8px 10px",
            borderRadius: 7,
            background: "rgba(208,115,43,0.08)",
            border: "1px solid rgba(208,115,43,0.25)",
            fontSize: 12,
            color: "var(--ink)",
          }}
        >
          <span style={{ fontSize: 14 }}>↻</span>
          <span style={{ fontWeight: 500 }}>
            This week rhymes with day −{history[rhymeStart].day} → −{history[rhymeStart + 6]?.day}.
          </span>
          <span style={{ color: "var(--muted)" }} className="tnum">
            RMSE 0.41 · cosine 0.88
          </span>
          <span style={{ flex: 1 }} />
          <button style={{ fontSize: 11, fontWeight: 600, color: "var(--warm)" }}>Explore →</button>
        </div>
      )}
    </section>
  );
}

// ═══════════════════════════════════════════════════════════════════════
// Tag donut
// ═══════════════════════════════════════════════════════════════════════

function TagDonut({ events }: { events: Event[] }) {
  const totals: Record<string, number> = {};
  events.forEach((e) => {
    totals[e.tag] = (totals[e.tag] || 0) + Math.abs(e.delta);
  });
  const entries = Object.entries(totals).sort((a, b) => b[1] - a[1]);
  const total = entries.reduce((a, b) => a + b[1], 0) || 1;
  const palette = ["#4c63d9", "#d0732b", "#3d8a5f", "#7a4789", "#3d7b87", "#b6a13a", "#8a8f96"];

  let angle = -Math.PI / 2;
  const arcs = entries.map((e, i) => {
    const frac = e[1] / total;
    const a0 = angle;
    const a1 = angle + frac * Math.PI * 2;
    angle = a1;
    return { label: e[0], value: e[1], frac, a0, a1, color: palette[i % palette.length] };
  });

  const cx = 110;
  const cy = 110;
  const rO = 82;
  const rI = 56;
  const arcPath = (a0: number, a1: number): string => {
    const large = a1 - a0 > Math.PI ? 1 : 0;
    const x0o = cx + rO * Math.cos(a0);
    const y0o = cy + rO * Math.sin(a0);
    const x1o = cx + rO * Math.cos(a1);
    const y1o = cy + rO * Math.sin(a1);
    const x0i = cx + rI * Math.cos(a1);
    const y0i = cy + rI * Math.sin(a1);
    const x1i = cx + rI * Math.cos(a0);
    const y1i = cy + rI * Math.sin(a0);
    return `M ${x0o} ${y0o} A ${rO} ${rO} 0 ${large} 1 ${x1o} ${y1o} L ${x0i} ${y0i} A ${rI} ${rI} 0 ${large} 0 ${x1i} ${y1i} Z`;
  };

  return (
    <section
      style={{
        background: "var(--panel)",
        border: "1px solid var(--line)",
        borderRadius: 10,
        padding: "14px 16px",
        minWidth: 0,
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          marginBottom: 10,
        }}
      >
        <div>
          <div style={{ fontSize: 14, fontWeight: 600 }}>Tag mix</div>
          <div style={{ fontSize: 11, color: "var(--muted)", marginTop: 2 }}>
            Share of today&apos;s weighted events
          </div>
        </div>
        <Chip label="Magnitude" caret />
      </div>

      <div style={{ display: "flex", gap: 16, alignItems: "center" }}>
        <svg width="220" height="220" style={{ flexShrink: 0 }}>
          {arcs.length === 0 && <circle cx={cx} cy={cy} r={rO} fill="var(--line)" />}
          {arcs.map((a, i) => (
            <path key={i} d={arcPath(a.a0, a.a1)} fill={a.color} opacity="0.88" />
          ))}
          <text x={cx} y={cy - 4} textAnchor="middle" fontSize="11" fill="var(--muted)">
            Events weighted
          </text>
          <text
            x={cx}
            y={cy + 18}
            textAnchor="middle"
            fontSize="24"
            fontWeight="600"
            fill="var(--ink)"
            className="tnum"
          >
            {events.length}
          </text>
          <text x={cx} y={cy + 32} textAnchor="middle" fontSize="11" fill="var(--green)" className="tnum">
            + {events.filter((e) => e.delta > 0).length} uplift
          </text>
        </svg>
        <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: 6 }}>
          {arcs.map((a, i) => (
            <div key={i} style={{ display: "flex", alignItems: "center", gap: 10, fontSize: 12 }}>
              <span
                style={{
                  width: 10,
                  height: 10,
                  background: a.color,
                  borderRadius: 2,
                  display: "inline-block",
                }}
              />
              <span style={{ color: "var(--ink)", textTransform: "capitalize", fontWeight: 500 }}>
                {a.label}
              </span>
              <span style={{ flex: 1 }} />
              <span style={{ color: "var(--muted)" }} className="tnum">
                {Math.round(a.frac * 100)}%
              </span>
            </div>
          ))}
          {arcs.length === 0 && (
            <div style={{ fontSize: 12, color: "var(--faint)" }}>
              No tags yet — write an entry to populate.
            </div>
          )}
        </div>
      </div>
    </section>
  );
}

// ═══════════════════════════════════════════════════════════════════════
// Thread ribbon
// ═══════════════════════════════════════════════════════════════════════

function ThreadRibbon({
  history,
  rhymeStart,
}: {
  history: HistoryDay[];
  rhymeStart: number | undefined;
}) {
  const [hoverIdx, setHoverIdx] = useState<number | null>(null);
  return (
    <section
      style={{
        background: "var(--panel)",
        border: "1px solid var(--line)",
        borderRadius: 10,
        padding: "14px 16px",
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          marginBottom: 10,
        }}
      >
        <div>
          <div style={{ fontSize: 14, fontWeight: 600 }}>Thread · 30 days</div>
          <div style={{ fontSize: 11, color: "var(--muted)", marginTop: 2 }}>
            {hoverIdx !== null ? (
              <span
                className="serif"
                style={{
                  fontFamily: "var(--serif)",
                  fontStyle: "italic",
                  fontSize: 13,
                  color: "var(--ink)",
                }}
              >
                day −{history[hoverIdx].day} — &ldquo;{history[hoverIdx].text.slice(0, 70)}…&rdquo;
              </span>
            ) : (
              "Each dot is a day's average valence · hover to read the narrative"
            )}
          </div>
        </div>
        <div style={{ display: "flex", gap: 6 }}>
          <Chip label="30d" active />
          <Chip label="90d" />
          <Chip label="YTD" />
        </div>
      </div>
      <HistorySvg history={history} rhymeStart={rhymeStart} onHover={setHoverIdx} hoverIdx={hoverIdx} />
    </section>
  );
}

function HistorySvg({
  history,
  rhymeStart,
  onHover,
  hoverIdx,
}: {
  history: HistoryDay[];
  rhymeStart: number | undefined;
  onHover: (i: number | null) => void;
  hoverIdx: number | null;
}) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(1000);
  useEffect(() => {
    if (!wrapRef.current) return;
    const ro = new ResizeObserver((entries) => {
      for (const e of entries) setWidth(Math.max(600, e.contentRect.width));
    });
    ro.observe(wrapRef.current);
    return () => ro.disconnect();
  }, []);
  const h = 100;
  const pad = { l: 20, r: 20, t: 16, b: 20 };
  const W = width - pad.l - pad.r;
  const H = h - pad.t - pad.b;
  const bw = W / history.length;
  const xAt = (i: number) => pad.l + i * bw + bw / 2;
  const yAt = (v: number) => pad.t + (1 - v / 100) * H;

  const pts = history.map((d, i) => ({ x: xAt(i), y: yAt(d.avg), d, i }));
  let d = `M ${pts[0].x} ${pts[0].y}`;
  for (let i = 1; i < pts.length; i++) {
    const p0 = pts[i - 1];
    const p1 = pts[i];
    const mx = (p0.x + p1.x) / 2;
    d += ` C ${mx} ${p0.y}, ${mx} ${p1.y}, ${p1.x} ${p1.y}`;
  }
  const areaD = `${d} L ${pts[pts.length - 1].x} ${yAt(0)} L ${pts[0].x} ${yAt(0)} Z`;

  return (
    <div ref={wrapRef}>
      <svg width={width} height={h} style={{ display: "block" }}>
        <defs>
          <linearGradient id="prudentThreadGrad" x1="0" x2="0" y1="0" y2="1">
            <stop offset="0%" stopColor="var(--accent)" stopOpacity="0.18" />
            <stop offset="100%" stopColor="var(--accent)" stopOpacity="0" />
          </linearGradient>
        </defs>
        <line
          x1={pad.l}
          x2={pad.l + W}
          y1={yAt(50)}
          y2={yAt(50)}
          stroke="var(--line)"
          strokeDasharray="3 3"
        />
        {rhymeStart !== null && rhymeStart !== undefined && (
          <rect
            x={pad.l + rhymeStart * bw}
            y={pad.t - 4}
            width={bw * 7}
            height={H + 8}
            fill="var(--warm)"
            opacity="0.08"
          />
        )}
        {rhymeStart !== null && rhymeStart !== undefined && (
          <rect
            x={pad.l + rhymeStart * bw}
            y={pad.t - 4}
            width={bw * 7}
            height={H + 8}
            fill="none"
            stroke="var(--warm)"
            strokeWidth="1"
            strokeDasharray="3 2"
            opacity="0.6"
          />
        )}
        <path d={areaD} fill="url(#prudentThreadGrad)" />
        <path d={d} fill="none" stroke="var(--accent)" strokeWidth="1.5" />
        {pts.map((p) => (
          <g key={p.i} onMouseEnter={() => onHover(p.i)} onMouseLeave={() => onHover(null)}>
            <rect x={pad.l + p.i * bw} y={pad.t} width={bw} height={H} fill="transparent" />
            <circle
              cx={p.x}
              cy={p.y}
              r={p.d.day === 0 ? 4 : hoverIdx === p.i ? 3.5 : 2}
              fill={p.d.day === 0 ? "var(--accent)" : "var(--panel)"}
              stroke="var(--accent)"
              strokeWidth="1.3"
            />
          </g>
        ))}
        <text x={pad.l} y={h - 4} fontSize="10" fill="var(--faint)">
          30d
        </text>
        <text x={pad.l + W / 2} y={h - 4} textAnchor="middle" fontSize="10" fill="var(--faint)">
          15d
        </text>
        <text x={pad.l + W} y={h - 4} textAnchor="end" fontSize="10" fill="var(--faint)">
          today
        </text>
      </svg>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════
// Composer modal
// ═══════════════════════════════════════════════════════════════════════

interface ComposerProps {
  text: string;
  setText: (t: string) => void;
  onClose: () => void;
  events: Event[];
}

function ComposerModal({ text, setText, onClose, events }: ComposerProps) {
  const ref = useRef<HTMLTextAreaElement>(null);
  useEffect(() => {
    ref.current?.focus();
  }, []);
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
            <div style={{ fontSize: 14, fontWeight: 600 }}>New entry</div>
            <div style={{ fontSize: 11, color: "var(--muted)" }}>
              Wed · Apr 17 · 7:04 am → now · parsing live
            </div>
          </div>
          <button onClick={onClose} style={{ color: "var(--muted)" }}>
            ✕
          </button>
        </div>
        <div style={{ padding: "16px 20px" }}>
          <textarea
            ref={ref}
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="How did today go, minute by minute?"
            rows={8}
            style={{
              width: "100%",
              fontFamily: "var(--serif)",
              fontSize: 18,
              lineHeight: 1.55,
              color: "var(--ink)",
              resize: "vertical",
              minHeight: 180,
            }}
          />
          <div style={{ marginTop: 14, paddingTop: 14, borderTop: "1px dashed var(--line)" }}>
            <div
              className="mono"
              style={{
                fontSize: 10,
                letterSpacing: "0.1em",
                color: "var(--muted)",
                fontWeight: 600,
                marginBottom: 8,
                textTransform: "uppercase",
              }}
            >
              Parsed · {events.length} events
            </div>
            <div style={{ fontSize: 13, lineHeight: 2, color: "var(--muted)" }}>
              {events.length === 0 && (
                <span style={{ color: "var(--faint)" }}>No anchors detected yet.</span>
              )}
              {events.map((ev, i) => (
                <span key={i} style={{ marginRight: 6 }}>
                  <span
                    style={{
                      borderBottom: `2px solid ${ev.delta > 0 ? "var(--green)" : "var(--warm)"}`,
                      color: "var(--ink)",
                      padding: "0 2px",
                    }}
                  >
                    {ev.text.replace(/[.?!,]+$/, "").slice(0, 36)}
                    {ev.text.length > 36 ? "…" : ""}
                  </span>
                  <span
                    className="mono"
                    style={{
                      fontSize: 10,
                      padding: "1px 5px",
                      borderRadius: 3,
                      background: ev.delta > 0 ? "rgba(61,138,95,0.12)" : "rgba(208,115,43,0.12)",
                      color: ev.delta > 0 ? "var(--green)" : "var(--warm)",
                      marginLeft: 4,
                      fontWeight: 600,
                    }}
                  >
                    {ev.delta > 0 ? "+" : ""}
                    {ev.delta.toFixed(0)}
                  </span>
                </span>
              ))}
            </div>
          </div>
        </div>
        <div
          style={{
            padding: "12px 20px",
            borderTop: "1px solid var(--line)",
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
          }}
        >
          <div className="mono" style={{ fontSize: 10, color: "var(--faint)" }}>
            {text.length} chars · {events.length} events
          </div>
          <div style={{ display: "flex", gap: 8 }}>
            <button
              onClick={onClose}
              style={{
                fontSize: 13,
                padding: "7px 14px",
                borderRadius: 7,
                border: "1px solid var(--line-mid)",
                color: "var(--muted)",
              }}
            >
              Cancel
            </button>
            <button
              onClick={onClose}
              style={{
                fontSize: 13,
                padding: "7px 14px",
                borderRadius: 7,
                background: "var(--ink)",
                color: "var(--app-bg)",
                fontWeight: 500,
              }}
            >
              Log to thread ↵
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════
// Footer + Tweaks panel
// ═══════════════════════════════════════════════════════════════════════

function Footer() {
  return (
    <div
      style={{
        display: "flex",
        justifyContent: "space-between",
        padding: "10px 4px 0 4px",
        borderTop: "1px solid var(--line)",
        fontSize: 11,
        color: "var(--faint)",
      }}
    >
      <div style={{ display: "flex", gap: 16 }}>
        <span>Privacy</span>
        <span>Terms</span>
        <span>Help Center</span>
        <span>Feedback</span>
      </div>
      <div>© 2026 The Similarity · engine v0.3</div>
    </div>
  );
}

interface TweaksPanelProps {
  tweaks: Tweaks;
  setTweak: <K extends keyof Tweaks>(k: K, v: Tweaks[K]) => void;
}

function TweaksPanel({ tweaks, setTweak }: TweaksPanelProps) {
  const opts = <K extends keyof Tweaks>(key: K, choices: readonly Tweaks[K][]) => (
    <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
      {choices.map((c) => (
        <button
          key={String(c)}
          onClick={() => setTweak(key, c)}
          className="mono"
          style={{
            fontSize: 10,
            padding: "4px 8px",
            border: `1px solid ${tweaks[key] === c ? "var(--ink)" : "var(--line-mid)"}`,
            background: tweaks[key] === c ? "var(--ink)" : "transparent",
            color: tweaks[key] === c ? "var(--app-bg)" : "var(--muted)",
            borderRadius: 5,
          }}
        >
          {String(c)}
        </button>
      ))}
    </div>
  );
  return (
    <div
      style={{
        position: "fixed",
        bottom: 18,
        right: 18,
        width: 268,
        zIndex: 60,
        background: "var(--panel)",
        border: "1px solid var(--line-mid)",
        borderRadius: 10,
        padding: 14,
        boxShadow: "0 20px 40px -18px rgba(0,0,0,0.35)",
      }}
    >
      <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 12 }}>Tweaks</div>
      <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        <div>
          <div
            className="mono"
            style={{
              fontSize: 10,
              color: "var(--muted)",
              marginBottom: 5,
              textTransform: "uppercase",
              letterSpacing: "0.08em",
            }}
          >
            accent
          </div>
          {opts("accent", ["blue", "ember", "teal", "plum"] as const)}
        </div>
        <div>
          <div
            className="mono"
            style={{
              fontSize: 10,
              color: "var(--muted)",
              marginBottom: 5,
              textTransform: "uppercase",
              letterSpacing: "0.08em",
            }}
          >
            theme
          </div>
          {opts("theme", ["light", "dark"] as const)}
        </div>
        <div>
          <div
            className="mono"
            style={{
              fontSize: 10,
              color: "var(--muted)",
              marginBottom: 5,
              textTransform: "uppercase",
              letterSpacing: "0.08em",
            }}
          >
            compare
          </div>
          {opts("compare", ["rhyme", "yesterday", "none"] as const)}
        </div>
      </div>
    </div>
  );
}
