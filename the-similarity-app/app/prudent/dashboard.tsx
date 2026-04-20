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

import { useState, useEffect, useMemo, useRef, useCallback, Fragment } from "react";
import {
  parseNarrative,
  buildHistory,
  findRhyme,
  type Event,
  type Point,
  type HistoryDay,
} from "./engine";
import {
  loadEntries,
  saveEntry,
  exportEntriesAsJSON,
  buildHistoryFromEntries,
  type StoredEntry,
} from "./storage";
import { useParsedNarrative } from "./use-parse";

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

// Sample narrative — shown as the textarea placeholder only. Actual entry
// state always starts empty so "+ New entry" never pre-fills the composer
// with a stranger's day.
const SAMPLE = `Woke up heavy, kind of anxious about the deadline. The morning was rough — emails piled up before I even had coffee. Slow standup, I barely talked. Around noon I went for a walk in the park and things started to lift. Ran into a friend who'd just moved back; we laughed about something stupid for twenty minutes. The afternoon clicked — I got into a flow and the code finally worked. Dinner was calm, read a little before bed.`;

// Persisted-tweaks key. Versioned so we can migrate the shape without
// silently breaking an investor's polished layout.
const TWEAKS_KEY = "prudent:tweaks:v1";

// Hydrate tweaks from localStorage. Returns defaults on SSR or when stored
// data is malformed. Never throws — persistence must be best-effort since
// it's not the critical path.
function loadTweaks(): Tweaks {
  if (typeof window === "undefined") return TWEAK_DEFAULTS;
  try {
    const raw = window.localStorage.getItem(TWEAKS_KEY);
    if (!raw) return TWEAK_DEFAULTS;
    const parsed = JSON.parse(raw) as Partial<Tweaks>;
    return {
      accent: (["blue", "ember", "teal", "plum"] as const).includes(
        parsed.accent as Accent,
      )
        ? (parsed.accent as Accent)
        : TWEAK_DEFAULTS.accent,
      density:
        parsed.density === "comfortable" || parsed.density === "compact"
          ? parsed.density
          : TWEAK_DEFAULTS.density,
      theme:
        parsed.theme === "light" || parsed.theme === "dark"
          ? parsed.theme
          : TWEAK_DEFAULTS.theme,
      compare:
        parsed.compare === "rhyme" ||
        parsed.compare === "yesterday" ||
        parsed.compare === "none"
          ? parsed.compare
          : TWEAK_DEFAULTS.compare,
    };
  } catch {
    return TWEAK_DEFAULTS;
  }
}

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
  // `text` is the CURRENT draft shown in the composer. Investors start with
  // an empty draft — the sample narrative lives only as placeholder text so
  // the journal feels personal rather than pre-populated.
  const [text, setText] = useState("");
  // Hydrate tweaks and entries via useState lazy-initializers rather than
  // an effect so the first paint is already correct. `loadTweaks` /
  // `loadEntries` guard `typeof window` so they return defaults under SSR
  // and pick up real values on the client's first render. This avoids the
  // "setState inside useEffect" pattern which the repo's hooks-lint
  // flags as cascading-render.
  const [tweaks, setTweaks] = useState<Tweaks>(() => loadTweaks());
  const [nav, setNav] = useState("today");
  const [composerOpen, setComposerOpen] = useState(false);
  // `readOnlyEntry` is non-null when the composer is open as a viewer (e.g.
  // the user clicked a past day). We still share the modal component so the
  // visual design is consistent between edit and read modes.
  const [readOnlyEntry, setReadOnlyEntry] = useState<StoredEntry | null>(null);
  // Persisted journal. Lazy init to avoid the post-mount setState pattern.
  const [entries, setEntries] = useState<StoredEntry[]>(() => loadEntries());
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

  // Persist tweaks whenever they change. Wrapped in try so a storage quota
  // error can't crash the render tree.
  useEffect(() => {
    if (typeof window === "undefined") return;
    try {
      window.localStorage.setItem(TWEAKS_KEY, JSON.stringify(tweaks));
    } catch {
      /* swallow — persistence is best-effort */
    }
  }, [tweaks]);

  const setTweak = <K extends keyof Tweaks>(k: K, v: Tweaks[K]) => {
    setTweaks((prev) => ({ ...prev, [k]: v }));
  };

  // Keyboard shortcut: ⌘/Ctrl+N opens the composer. Escape closes either
  // the composer or the read-only viewer. Global listener so the modal
  // itself doesn't need to own key handling.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const isNew = (e.metaKey || e.ctrlKey) && (e.key === "n" || e.key === "N");
      if (isNew) {
        e.preventDefault();
        setReadOnlyEntry(null);
        setText("");
        setComposerOpen(true);
      }
      if (e.key === "Escape") {
        setComposerOpen(false);
        setReadOnlyEntry(null);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  // Parse the composer draft with the live hook — regex immediately, Claude
  // upgrade on debounce. We keep the hook outside the composer modal so the
  // dashboard can reflect the same parsed state even when the modal is closed.
  const parsed = useParsedNarrative(text);
  const { events, series } = parsed;
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

  // History source switch: real entries once the user has >= 7 logs, else
  // synthetic. `buildHistoryFromEntries` encapsulates the threshold.
  const history = useMemo(
    () => buildHistoryFromEntries(entries, avg),
    [entries, avg],
  );
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

  // Persist the current draft as a new journal entry and reset the composer.
  // After save we re-read from storage so our in-memory list matches disk
  // exactly — this guards against subtle drift if a second tab also wrote.
  const persistEntry = useCallback(() => {
    if (!text.trim()) {
      setComposerOpen(false);
      return;
    }
    const entry: StoredEntry = {
      id: `entry-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      createdAt: new Date().toISOString(),
      day: 0,
      text,
      events,
      series,
      avg,
    };
    saveEntry(entry);
    setEntries(loadEntries());
    setText("");
    setComposerOpen(false);
    setReadOnlyEntry(null);
  }, [text, events, series, avg]);

  // Open the composer in read-only view with a past entry's content loaded.
  const openReadOnly = useCallback((entry: StoredEntry) => {
    setReadOnlyEntry(entry);
    setComposerOpen(true);
  }, []);

  // Fresh composer — wipes any read-only context and opens empty.
  const openNewComposer = useCallback(() => {
    setReadOnlyEntry(null);
    setText("");
    setComposerOpen(true);
  }, []);

  // Export all entries as a timestamped JSON file. Creates an object URL,
  // simulates a click on an <a download>, and revokes the URL afterward.
  const onExport = useCallback(() => {
    if (typeof window === "undefined") return;
    const json = exportEntriesAsJSON();
    const blob = new Blob([json], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const today = new Date().toISOString().slice(0, 10);
    const a = document.createElement("a");
    a.href = url;
    a.download = `prudent-entries-${today}.json`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  }, []);

  // Delete a single entry by id. Simple read-filter-write against storage.
  const removeEntry = useCallback((id: string) => {
    if (typeof window === "undefined") return;
    try {
      const next = loadEntries().filter((e) => e.id !== id);
      window.localStorage.setItem("prudent:entries:v1", JSON.stringify(next));
      setEntries(next);
    } catch {
      /* swallow */
    }
  }, []);

  // Click handler for ribbon dots — if the dot corresponds to a real stored
  // entry, open its narrative read-only; otherwise show today's draft.
  const onRibbonDotClick = useCallback(
    (day: number) => {
      if (day === 0) {
        // Today — open the current draft (may be empty if nothing logged
        // yet). We use the non-readonly path so user can finish writing.
        setReadOnlyEntry(null);
        setComposerOpen(true);
        return;
      }
      const match = entries.find((e) => e.day === day);
      if (match) openReadOnly(match);
    },
    [entries, openReadOnly],
  );

  return (
    <div ref={rootRef} className="prudent-root">
      <div style={{ display: "flex", minHeight: "100vh", background: "var(--app-bg)" }}>
        <Sidebar
          nav={nav}
          setNav={setNav}
          onCompose={openNewComposer}
          onExport={onExport}
        />
        <main
          // 24px horizontal padding matches the reference grid. We use an
          // inline gap of 18px between cards so the layout feels airy without
          // wasting the canvas on very wide viewports.
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
          <PageHeader events={events} nav={nav} entries={entries} />

          {nav === "today" && (
            <>
              <div className="prudent-grid-top">
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

              <div className="prudent-grid-mid">
                <RhymeHeatmap history={history} rhymeStart={rhyme?.startIdx} />
                <TagDonut events={events} />
              </div>

              <ThreadRibbon
                history={history}
                rhymeStart={rhyme?.startIdx}
                onDotClick={onRibbonDotClick}
              />
            </>
          )}

          {nav === "thread" && (
            <ThreadView entries={entries} onOpen={openReadOnly} />
          )}

          {nav === "rhymes" && <RhymesView history={history} />}

          {nav === "entries" && (
            <EntriesView
              entries={entries}
              onOpen={openReadOnly}
              onRemove={removeEntry}
            />
          )}

          {nav === "tags" && (
            <ComingSoon
              title="Tags"
              description="Auto-extracted themes across your journal will live here."
            />
          )}

          {nav === "patterns" && (
            <ComingSoon
              title="Patterns"
              description="Repeating day-shapes and weekly rhymes at a glance."
            />
          )}

          {nav === "engine" && (
            <EngineLogsView
              source={parsed.source}
              loading={parsed.loading}
              error={parsed.error}
              eventCount={events.length}
            />
          )}

          <Footer />
        </main>

        {composerOpen && (
          <ComposerModal
            text={readOnlyEntry ? readOnlyEntry.text : text}
            setText={setText}
            onClose={() => {
              setComposerOpen(false);
              setReadOnlyEntry(null);
            }}
            events={readOnlyEntry ? readOnlyEntry.events : events}
            source={readOnlyEntry ? "idle" : parsed.source}
            readOnly={!!readOnlyEntry}
            readOnlyLabel={
              readOnlyEntry
                ? `day −${readOnlyEntry.day} · logged ${readOnlyEntry.createdAt.slice(0, 10)}`
                : undefined
            }
            onSave={persistEntry}
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
          /* Own scroll container. The workstation's globals.css pins
             body { overflow: hidden } for the Bloomberg-terminal layout,
             so /prudent needs its own scrollable viewport. The sidebar's
             position: sticky; top: 0 sticks relative to this container. */
          height: 100vh;
          overflow-y: auto;
          overflow-x: hidden;
        }
        .prudent-root.prudent-dark {
          /* Warm near-black dark theme. The panel bg has a hint of
             warmth (#17191C) rather than pure neutral to avoid the cold
             "inverted screenshot" look of naive dark modes. Card borders
             are a tick lighter than card bg so edges stay visible.

             Selection overrides to a soft blue wash (not solid accent) so
             dense numeric tables don't flash blinding when selected. */
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
// Sidebar
// ═══════════════════════════════════════════════════════════════════════

interface SidebarProps {
  nav: string;
  setNav: (id: string) => void;
  onCompose: () => void;
  onExport: () => void;
}

function Sidebar({ nav, setNav, onCompose, onExport }: SidebarProps) {
  const items = [
    { id: "today", label: "Today", hint: "Apr 17" },
    { id: "thread", label: "Thread", hint: "30d" },
    { id: "rhymes", label: "Rhymes", hint: "12", fresh: true },
    { id: "tags", label: "Tags" },
    { id: "patterns", label: "Patterns" },
    { id: "entries", label: "Entries", hint: "142" },
  ];
  const Ext: { id: string; label: string; action: "nav" | "export" }[] = [
    { id: "engine", label: "Engine logs", action: "nav" },
    { id: "export", label: "Export", action: "export" },
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
      {/* Icon rail — dark column hosting the brand mark, a help glyph, and
          the user avatar. The 7 category glyphs from the reference screenshot
          were dead controls with no handlers (pure cargo-cult) and have been
          removed; only presence elements that represent real affordances
          (brand, help, avatar) remain. */}
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
          {"//"}
        </div>
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
        {Ext.map((it) => {
          const isActive = it.action === "nav" && nav === it.id;
          return (
            <button
              key={it.id}
              onClick={() => {
                if (it.action === "export") onExport();
                else setNav(it.id);
              }}
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                gap: 10,
                padding: "9px 10px",
                fontSize: 13,
                color: isActive ? "var(--ink)" : "var(--muted)",
                background: isActive ? "var(--hover)" : "transparent",
                borderRadius: 7,
                textAlign: "left",
                fontWeight: isActive ? 600 : 450,
              }}
            >
              <span style={{ display: "flex", alignItems: "center", gap: 10 }}>
                <NavGlyph id={it.id} />
                {it.label}
              </span>
              {it.action === "export" && (
                <span
                  className="mono"
                  style={{ fontSize: 10, color: "var(--faint)" }}
                  aria-hidden
                >
                  ↓
                </span>
              )}
            </button>
          );
        })}

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

function PageHeader({
  events,
  nav,
  entries,
}: {
  events: Event[];
  nav: string;
  entries: StoredEntry[];
}) {
  // Title + subtitle track the active nav so the page header is never
  // stale while the user pivots to a different view.
  const titleMap: Record<string, { title: string; subtitle: React.ReactNode }> = {
    today: {
      title: "Today",
      subtitle: (
        <>
          Narrative parsed live ·{" "}
          <span className="tnum" style={{ color: "var(--ink)", fontWeight: 500 }}>
            {events.length}
          </span>{" "}
          events · baseline valence{" "}
          <span className="tnum" style={{ color: "var(--ink)", fontWeight: 500 }}>
            50
          </span>
        </>
      ),
    },
    thread: {
      title: "Thread",
      subtitle: (
        <>
          <span className="tnum" style={{ color: "var(--ink)", fontWeight: 500 }}>
            {entries.length}
          </span>{" "}
          entries saved · newest first · click any card to read
        </>
      ),
    },
    rhymes: {
      title: "Rhymes",
      subtitle: "Days whose shape most resembles today.",
    },
    entries: {
      title: "Entries",
      subtitle: (
        <>
          <span className="tnum" style={{ color: "var(--ink)", fontWeight: 500 }}>
            {entries.length}
          </span>{" "}
          logged · export or remove individual entries
        </>
      ),
    },
    tags: { title: "Tags", subtitle: "Coming soon." },
    patterns: { title: "Patterns", subtitle: "Coming soon." },
    engine: { title: "Engine logs", subtitle: "Live view of the parse pipeline." },
  };
  const { title, subtitle } = titleMap[nav] ?? titleMap.today;
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
            {title}
          </h1>
          <div
            style={{
              fontSize: 13,
              color: "var(--muted)",
              marginTop: 6,
              fontWeight: 400,
            }}
          >
            {subtitle}
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
        <DateRangeChip />
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

/**
 * DateRangeChip — functional date-range control with three presets.
 *
 * Click opens a small popover anchored below the chip. Selecting a preset
 * both updates the chip label and persists the choice locally so a reload
 * keeps the view consistent. We do not wire the actual data-window here
 * (that's a follow-up) but the control itself is fully functional and
 * clicks are observable.
 *
 * Presets:
 *   - today   (default) — renders as "Today · 9:47 am"
 *   - 7d                — "Last 7 days"
 *   - 30d               — "Last 30 days"
 *
 * Closing:
 *   - Click-away closes the popover via a document listener installed on
 *     open.
 *   - Selecting a preset auto-closes.
 */
function DateRangeChip() {
  type Preset = "today" | "7d" | "30d";
  // Lazy initializer reads localStorage once on first render. Safe under
  // SSR because `typeof window` guards the access. See Dashboard() for the
  // same pattern reasoning.
  const [preset, setPreset] = useState<Preset>(() => {
    if (typeof window === "undefined") return "today";
    const v = window.localStorage.getItem("prudent:daterange:v1");
    return v === "today" || v === "7d" || v === "30d" ? v : "today";
  });
  const [open, setOpen] = useState(false);
  const anchorRef = useRef<HTMLDivElement>(null);

  // Persist preset changes. Best-effort — swallow storage errors.
  useEffect(() => {
    if (typeof window === "undefined") return;
    try {
      window.localStorage.setItem("prudent:daterange:v1", preset);
    } catch {
      /* swallow */
    }
  }, [preset]);

  // Click-away close. Installed only when open so we're not leaking a
  // document-level listener across every mount.
  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (!anchorRef.current) return;
      if (!anchorRef.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [open]);

  const labelFor = (p: Preset): { from: string; to: string } => {
    if (p === "today") return { from: "Wed, Apr 17", to: "9:47 am" };
    if (p === "7d") return { from: "Apr 11", to: "Apr 17" };
    return { from: "Mar 19", to: "Apr 17" };
  };
  const { from, to } = labelFor(preset);

  return (
    <div ref={anchorRef} style={{ position: "relative", display: "inline-block" }}>
      <button
        onClick={() => setOpen((v) => !v)}
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
        aria-haspopup="listbox"
        aria-expanded={open}
      >
        <svg
          width="13"
          height="13"
          viewBox="0 0 15 15"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.3"
        >
          <rect x="2" y="3" width="11" height="10" rx="1" />
          <path d="M2 6h11M5 1.5v3M10 1.5v3" />
        </svg>
        <span>{from}</span>
        <span style={{ color: "var(--faint)" }}>→</span>
        <span>{to}</span>
        <svg
          width="9"
          height="9"
          viewBox="0 0 9 9"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.3"
          style={{
            opacity: 0.55,
            marginLeft: 2,
            transition: "transform 120ms ease",
            transform: open ? "rotate(180deg)" : "rotate(0)",
          }}
        >
          <path d="M2 3.5L4.5 6 7 3.5" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </button>
      {open && (
        <div
          role="listbox"
          style={{
            position: "absolute",
            top: "calc(100% + 6px)",
            left: 0,
            zIndex: 40,
            background: "var(--panel)",
            border: "1px solid var(--line-mid)",
            borderRadius: 8,
            padding: 4,
            boxShadow: "0 12px 24px -10px rgba(20,22,26,0.25)",
            minWidth: 160,
          }}
        >
          {(
            [
              { id: "today" as const, label: "Today" },
              { id: "7d" as const, label: "Last 7 days" },
              { id: "30d" as const, label: "Last 30 days" },
            ]
          ).map((opt) => (
            <button
              key={opt.id}
              onClick={() => {
                setPreset(opt.id);
                setOpen(false);
              }}
              role="option"
              aria-selected={preset === opt.id}
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                width: "100%",
                padding: "7px 10px",
                fontSize: 12.5,
                color: preset === opt.id ? "var(--ink)" : "var(--muted)",
                background: preset === opt.id ? "var(--hover)" : "transparent",
                borderRadius: 6,
                fontWeight: preset === opt.id ? 600 : 500,
                textAlign: "left",
              }}
            >
              <span>{opt.label}</span>
              {preset === opt.id && (
                <svg
                  width="11"
                  height="11"
                  viewBox="0 0 11 11"
                  fill="none"
                  stroke="var(--accent)"
                  strokeWidth="1.8"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  <path d="M2 5.5L4.5 8l4.5-5" />
                </svg>
              )}
            </button>
          ))}
        </div>
      )}
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

// DateChip removed — DateRangeChip (below PageHeader) is the functional
// replacement with a preset popover.

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
        padding: "16px 18px 18px 18px",
        display: "flex",
        flexDirection: "column",
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          marginBottom: 4,
        }}
      >
        <div style={{ fontSize: 14, fontWeight: 600 }}>Key metrics</div>
        <Chip label="All workspaces" caret />
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
        sparklineCustom={<VolatilitySpark series={series} stroke="var(--accent)" />}
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

// Colored filled triangle glyphs — defined at module scope so React's hooks
// lint doesn't flag them as "component created during render". Replaces the
// unicode ▲/▼ characters which render inconsistently across platforms.
const TriUp = () => (
  <svg width="7" height="7" viewBox="0 0 7 7" fill="currentColor">
    <path d="M3.5 1L6.5 6h-6z" />
  </svg>
);
const TriDown = () => (
  <svg width="7" height="7" viewBox="0 0 7 7" fill="currentColor">
    <path d="M3.5 6L6.5 1h-6z" />
  </svg>
);

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
        padding: "16px 0 14px 0",
        borderBottom: noborder ? "none" : "1px solid var(--line)",
      }}
    >
      <div>
        <div
          style={{
            fontSize: 10.5,
            color: "var(--muted)",
            marginBottom: 8,
            fontWeight: 500,
            letterSpacing: "0.02em",
          }}
        >
          {label}
        </div>
        <div style={{ display: "flex", alignItems: "baseline", gap: 5 }}>
          <div
            className="tnum"
            style={{
              fontSize: 30,
              fontWeight: 600,
              letterSpacing: "-0.03em",
              color: "var(--ink)",
              lineHeight: 1,
            }}
          >
            {value}
          </div>
          <div
            className="mono"
            style={{
              fontSize: 10.5,
              color: "var(--faint)",
              fontWeight: 500,
              letterSpacing: "0.02em",
            }}
          >
            {unit}
          </div>
        </div>
        <div
          className="tnum"
          style={{
            fontSize: 11,
            marginTop: 8,
            color: up === null ? "var(--muted)" : up ? "var(--green)" : "var(--warm-strong)",
            fontWeight: 500,
            display: "inline-flex",
            alignItems: "center",
            gap: 5,
          }}
        >
          {up === null ? (
            <span
              style={{
                width: 5,
                height: 5,
                background: "currentColor",
                borderRadius: "50%",
                display: "inline-block",
                opacity: 0.6,
              }}
            />
          ) : up ? (
            <TriUp />
          ) : (
            <TriDown />
          )}
          <span>{Math.abs(delta).toFixed(delta % 1 === 0 ? 0 : 2)}</span>
          <span style={{ color: "var(--faint)", fontWeight: 400, marginLeft: 2 }}>
            {deltaSuffix}
          </span>
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
      {/* Zero axis — a faint line of the panel line-mid color so bars read
          as discrete +/- pillars rather than floating glyphs. */}
      <line
        x1="0"
        x2={width}
        y1={height / 2}
        y2={height / 2}
        stroke="var(--line-mid)"
        strokeWidth="1"
      />
      {events.map((e, i) => {
        const x = (e.time / maxT) * width;
        const up = e.delta > 0;
        const mag = Math.min(1, Math.abs(e.delta) / 20);
        const h = Math.max(2, mag * (height / 2 - 3));
        return (
          <rect
            key={i}
            x={x - 1.5}
            y={up ? height / 2 - h : height / 2}
            width="3"
            height={h}
            fill={up ? "var(--green)" : "var(--warm-strong)"}
            rx="1.5"
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
  // Smooth-sample to avoid jagged polyline segments. We sample every 5th point
  // and interpolate between them with cubic-Bezier midpoints so the shape
  // reads as a delicate curve.
  const pts = series
    .filter((_, i) => i % 5 === 0)
    .map((p, i, arr) => [
      (i / (arr.length - 1)) * width,
      (1 - (p.v - min) / (max - min)) * height,
    ] as const);
  let d = `M ${pts[0][0]} ${pts[0][1]}`;
  for (let i = 1; i < pts.length; i++) {
    const [x0, y0] = pts[i - 1];
    const [x1, y1] = pts[i];
    const mx = (x0 + x1) / 2;
    d += ` C ${mx} ${y0}, ${mx} ${y1}, ${x1} ${y1}`;
  }
  const maxT = 16 * 60;
  const px = (peak.t / maxT) * width;
  const tx = (trough.t / maxT) * width;
  return (
    <svg width={width} height={height}>
      <path
        d={d}
        fill="none"
        stroke="var(--muted)"
        strokeWidth="1"
        strokeLinecap="round"
        opacity="0.45"
      />
      <circle
        cx={px}
        cy={(1 - peak.v / 100) * height}
        r="3.25"
        fill="var(--green)"
        stroke="var(--panel)"
        strokeWidth="1.5"
      />
      <circle
        cx={tx}
        cy={(1 - trough.v / 100) * height}
        r="3.25"
        fill="var(--warm-strong)"
        stroke="var(--panel)"
        strokeWidth="1.5"
      />
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
        padding: "16px 18px 18px 18px",
        minWidth: 0,
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          marginBottom: 8,
          gap: 12,
        }}
      >
        <div style={{ minWidth: 0 }}>
          <div style={{ fontSize: 14, fontWeight: 600 }}>Valence over time</div>
          <div style={{ fontSize: 11, color: "var(--muted)", marginTop: 3 }}>
            Integrated trajectory · 5-min resolution · today vs comparison
          </div>
        </div>
        <div style={{ display: "flex", gap: 6, flexShrink: 0 }}>
          <button
            onClick={() => setCompare(compareMode === "rhyme" ? "yesterday" : "rhyme")}
            style={{
              display: "flex",
              alignItems: "center",
              gap: 7,
              padding: "6px 11px",
              fontSize: 12,
              background: "var(--panel)",
              border: "1px solid var(--line-mid)",
              borderRadius: 7,
              color: "var(--muted)",
              fontWeight: 500,
            }}
          >
            <svg
              width="12"
              height="12"
              viewBox="0 0 12 12"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.4"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <path d="M2 4h8l-2-2M10 8H2l2 2" />
            </svg>
            <span style={{ color: "var(--muted)" }}>Compare ·</span>
            <span style={{ color: "var(--ink)", fontWeight: 500 }}>
              {compareMode === "yesterday"
                ? "Yesterday"
                : compareMode === "rhyme"
                  ? "Rhyming week"
                  : "None"}
            </span>
            <svg width="8" height="8" viewBox="0 0 9 9" fill="none" stroke="currentColor" strokeWidth="1.3" style={{ opacity: 0.6 }}>
              <path d="M2 3.5L4.5 6 7 3.5" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
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
          <LegendDot color="var(--accent-mid)" label={compareLabel} dashed />
        )}
        <LegendDot color="var(--green)" label="Uplift event" dotOnly />
        <LegendDot color="var(--warm-strong)" label="Downturn event" dotOnly />
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
            stroke="var(--line-mid)"
            strokeWidth="1"
            strokeDasharray={v === 0 || v === 100 ? "" : "1 3"}
            opacity={v === 50 ? 0.7 : 0.45}
          />
          <text
            x={pad.left - 8}
            y={yAt(v) + 3}
            textAnchor="end"
            fontSize="9.5"
            fill="var(--faint)"
            className="tnum mono"
            fontWeight="500"
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
          fontSize="9.5"
          fill="var(--faint)"
          className="mono"
          fontWeight="500"
        >
          {formatHour(t)}
        </text>
      ))}

      <path d={areaPath} fill={`url(#${gradId})`} />

      {compareSeries && (
        // Compare curve — lighter shade of the same accent family (not warm,
        // per reference). Dashed 4-3 stroke keeps it readable under the
        // primary today line when the two cross.
        <path
          d={comparePath}
          fill="none"
          stroke="var(--accent-mid)"
          strokeWidth="1.75"
          strokeDasharray="4 3"
          strokeLinecap="round"
          opacity="0.9"
        />
      )}

      <path
        d={todayPath}
        fill="none"
        stroke="var(--accent)"
        strokeWidth="2.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />

      {/* Event markers live only on the Today line (per reference). Each is
          a small filled dot (accent color, white core) with a tiny magnitude
          label above in tabular mono. The label color matches the sign so a
          glance at the chart tells you the direction. */}
      {events.map((ev, i) => {
        const val = interp(series, ev.time);
        const up = ev.delta > 0;
        const col = up ? "var(--green)" : "var(--warm-strong)";
        const labelY = yAt(val) - 18 - (i % 2) * 8;
        return (
          <g key={i}>
            <line
              x1={xAt(ev.time)}
              x2={xAt(ev.time)}
              y1={yAt(val) - 4}
              y2={labelY + 4}
              stroke={col}
              strokeWidth="0.75"
              opacity="0.35"
            />
            <circle
              cx={xAt(ev.time)}
              cy={yAt(val)}
              r="4"
              fill="var(--accent)"
              stroke="var(--panel)"
              strokeWidth="2"
            />
            <text
              x={xAt(ev.time)}
              y={labelY}
              textAnchor="middle"
              fontSize="9"
              fill={col}
              className="tnum mono"
              fontWeight="600"
              letterSpacing="-0.01em"
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

  // Five intensity steps, mapped from normalized valence-intensity ∈ [0,1].
  // Step 0 is the empty state — a barely-there filled chip (NOT a dashed
  // outline) so the grid still reads as a continuous canvas instead of a
  // ghostly outline on white. Higher steps ramp through tailwind blue-50 →
  // blue-500 so the darkest cells are legible on a white panel.
  //
  // We use rgba(59,130,246,α) rather than `var(--accent) / α` because Safari
  // color-mix() support on older targets is inconsistent. In dark mode the
  // alpha values paint correctly over the dark panel — the blue hue stays
  // recognisable because its saturation is high.
  const STEP_BG = [
    "rgba(59,130,246,0.06)",   // 0 — ghost
    "rgba(59,130,246,0.16)",   // 1 — faint
    "rgba(59,130,246,0.32)",   // 2 — soft
    "rgba(59,130,246,0.58)",   // 3 — medium
    "rgba(59,130,246,1.0)",    // 4 — solid
  ];
  const stepFor = (v: number): number => {
    if (v < 0.15) return 0;
    if (v < 0.35) return 1;
    if (v < 0.55) return 2;
    if (v < 0.75) return 3;
    return 4;
  };
  // At step 3 we switch the label color to white so contrast stays readable.
  const stepText = (step: number): string =>
    step >= 3 ? "#fff" : step === 0 ? "var(--faint)" : "var(--ink)";

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
          marginBottom: 12,
          gap: 12,
        }}
      >
        <div>
          <div style={{ fontSize: 14, fontWeight: 600 }}>Busiest valence</div>
          <div style={{ fontSize: 11, color: "var(--muted)", marginTop: 3 }}>
            Last 7 days · hour-of-day intensity
          </div>
        </div>
        <div
          style={{ display: "flex", alignItems: "center", gap: 10, flexShrink: 0 }}
        >
          {/* Legend — same 5-step swatches as the grid cells, each a tiny
              rounded square so the ramp reads as a mini version of the map. */}
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: 6,
              fontSize: 10.5,
              color: "var(--muted)",
              fontVariantNumeric: "tabular-nums",
            }}
          >
            <span>0</span>
            <div style={{ display: "flex", gap: 2 }}>
              {STEP_BG.map((bg, i) => (
                <div
                  key={i}
                  style={{
                    width: 12,
                    height: 12,
                    background: bg,
                    borderRadius: 3,
                  }}
                />
              ))}
            </div>
            <span>100</span>
          </div>
          <Chip label="All workspaces" caret />
        </div>
      </div>

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "42px repeat(12, 1fr)",
          gap: 5,
          alignItems: "center",
        }}
      >
        <div />
        {cells.map((row, ri) => (
          <Fragment key={ri}>
            <div
              style={{
                fontSize: 11,
                color: isRhymeRow(ri) ? "var(--warm-strong)" : "var(--muted)",
                fontWeight: isRhymeRow(ri) ? 600 : 500,
                textAlign: "right",
                paddingRight: 8,
                letterSpacing: "0.01em",
              }}
            >
              {days[ri]}
            </div>
            {row.map((cell, ci) => {
              const step = stepFor(cell.v);
              const val = Math.round(cell.v * 10);
              return (
                <div
                  key={ci}
                  style={{
                    aspectRatio: "1.3",
                    background: STEP_BG[step],
                    color: stepText(step),
                    borderRadius: 7,
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    fontSize: 11,
                    fontWeight: step >= 3 ? 600 : 500,
                    fontVariantNumeric: "tabular-nums",
                    // Rhyming rows get a soft warm outline — no longer the
                    // dashed inset; this looks like a highlight band rather
                    // than a warning state.
                    boxShadow: isRhymeRow(ri)
                      ? "inset 0 0 0 1.5px rgba(249,115,22,0.45)"
                      : "none",
                    transition: "transform 120ms ease",
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
            className="mono"
            style={{
              fontSize: 9.5,
              color: "var(--faint)",
              textAlign: "center",
              paddingTop: 6,
              fontVariantNumeric: "tabular-nums",
              fontWeight: 500,
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
            gap: 10,
            marginTop: 14,
            padding: "10px 12px",
            borderRadius: 8,
            // Warm ember band — bg is tailwind orange-50, border orange-200.
            background: "rgba(249,115,22,0.07)",
            border: "1px solid rgba(249,115,22,0.22)",
            fontSize: 12,
            color: "var(--ink)",
          }}
        >
          <svg
            width="14"
            height="14"
            viewBox="0 0 16 16"
            fill="none"
            stroke="var(--warm-strong)"
            strokeWidth="1.6"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <path d="M3 8a5 5 0 019-3L13 6M13 8a5 5 0 01-9 3L3 10" />
            <path d="M13 3v3h-3M3 13v-3h3" />
          </svg>
          <span style={{ fontWeight: 500 }}>
            This week rhymes with day −{history[rhymeStart].day} → −
            {history[rhymeStart + 6]?.day}.
          </span>
          <span style={{ color: "var(--muted)", fontWeight: 500 }} className="tnum">
            RMSE 0.41 · cosine 0.88
          </span>
          <span style={{ flex: 1 }} />
          <button
            style={{
              fontSize: 11,
              fontWeight: 600,
              color: "var(--warm-strong)",
              letterSpacing: "0.01em",
            }}
          >
            Explore →
          </button>
        </div>
      )}
    </section>
  );
}

// ═══════════════════════════════════════════════════════════════════════
// Tag donut
// ═══════════════════════════════════════════════════════════════════════

/**
 * Tag mix donut — concentric rounded-arc rendering.
 *
 * We render each segment as a stroked `<circle>` with a `stroke-dasharray`
 * pattern, NOT as SVG pie slices. This buys us:
 *   - a uniform 13px stroke-width so arcs look like ribbons, not wedges;
 *   - stroke-linecap="round" for soft segment ends;
 *   - a true gap between segments (the `gapDeg` below) that a path-based pie
 *     cannot produce because filled sectors always share a seam.
 *
 * Layout invariants:
 *   - dasharray = [arc-length, circumference - arc-length] rotates into place
 *     via transform="rotate(θ)" on the g element.
 *   - angular gap is fixed in degrees (not per-segment percentage), so thin
 *     slices never degenerate into invisible commas.
 */
function TagDonut({ events }: { events: Event[] }) {
  const totals: Record<string, number> = {};
  events.forEach((e) => {
    totals[e.tag] = (totals[e.tag] || 0) + Math.abs(e.delta);
  });
  const entries = Object.entries(totals).sort((a, b) => b[1] - a[1]);
  const total = entries.reduce((a, b) => a + b[1], 0) || 1;

  // Palette tuned so the primary segment is our pure blue (var(--accent)) and
  // remaining segments are tonally harmonized analogs. These are intentional
  // hex values (not CSS vars) so the <svg> exports cleanly for screenshots.
  const palette = [
    "#3B82F6", // accent (blue-500)
    "#F97316", // warm (orange-500)
    "#16A34A", // green-600
    "#8B5CF6", // violet-500
    "#0E7490", // cyan-700
    "#EAB308", // yellow-500
    "#64748B", // slate-500
  ];

  const slices = entries.map((e, i) => ({
    label: e[0],
    value: e[1],
    frac: e[1] / total,
    color: palette[i % palette.length],
  }));

  const size = 220;
  const cx = size / 2;
  const cy = size / 2;
  const r = 82;
  const strokeW = 18;
  const C = 2 * Math.PI * r;
  // Angular gap between segments in degrees. 4deg reads as a crisp breath at
  // this radius without losing any single-segment to the background.
  const gapDeg = 4;
  const gapFrac = gapDeg / 360;

  // Pre-walk the slices once to compute offsets so we can rotate each segment
  // into place. Starting angle = -90deg (12 o'clock), matching UX convention.
  // We compute via reduce() rather than mutating a local to satisfy the
  // react-hooks/immutability lint rule — the lint framework in this repo
  // treats component-scope mutation across `.map()` as a render-time hazard.
  const arcs = slices.reduce<
    { label: string; value: number; frac: number; color: string; arcLen: number; rot: number }[]
  >((acc, s) => {
    const offset = acc.reduce((sum, a) => sum + a.frac * 360, 0);
    const arcFrac = Math.max(0, s.frac - gapFrac);
    const arcLen = arcFrac * C;
    const rot = -90 + offset + gapDeg / 2;
    acc.push({ ...s, arcLen, rot });
    return acc;
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
          marginBottom: 10,
        }}
      >
        <div>
          <div style={{ fontSize: 14, fontWeight: 600 }}>Tag mix</div>
          <div style={{ fontSize: 11, color: "var(--muted)", marginTop: 3 }}>
            Share of today&apos;s weighted events
          </div>
        </div>
        <Chip label="Magnitude" caret />
      </div>

      <div style={{ display: "flex", gap: 18, alignItems: "center" }}>
        <svg width={size} height={size} style={{ flexShrink: 0 }}>
          {/* Background track — very faint ring so the canvas is always
              readable even when there are zero events. */}
          <circle
            cx={cx}
            cy={cy}
            r={r}
            fill="none"
            stroke="var(--line)"
            strokeWidth={strokeW}
            opacity={arcs.length === 0 ? 1 : 0.5}
          />
          {arcs.map((a, i) => (
            <g key={i} transform={`rotate(${a.rot} ${cx} ${cy})`}>
              <circle
                cx={cx}
                cy={cy}
                r={r}
                fill="none"
                stroke={a.color}
                strokeWidth={strokeW}
                strokeLinecap="round"
                strokeDasharray={`${a.arcLen} ${C - a.arcLen}`}
                strokeDashoffset="0"
              />
            </g>
          ))}
          <text
            x={cx}
            y={cy - 10}
            textAnchor="middle"
            fontSize="10"
            fill="var(--muted)"
            letterSpacing="0.06em"
            style={{ textTransform: "uppercase", fontWeight: 500 }}
          >
            Events
          </text>
          <text
            x={cx}
            y={cy + 14}
            textAnchor="middle"
            fontSize="28"
            fontWeight="600"
            fill="var(--ink)"
            className="tnum"
            letterSpacing="-0.02em"
          >
            {events.length}
          </text>
          <text
            x={cx}
            y={cy + 30}
            textAnchor="middle"
            fontSize="10.5"
            fill="var(--green)"
            className="tnum"
            fontWeight={500}
          >
            + {events.filter((e) => e.delta > 0).length} uplift
          </text>
        </svg>
        <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: 9 }}>
          {arcs.map((a, i) => (
            <div
              key={i}
              style={{ display: "flex", alignItems: "center", gap: 10, fontSize: 12 }}
            >
              <span
                style={{
                  width: 9,
                  height: 9,
                  background: a.color,
                  borderRadius: "50%",
                  display: "inline-block",
                  flexShrink: 0,
                }}
              />
              <span
                style={{
                  color: "var(--ink)",
                  textTransform: "capitalize",
                  fontWeight: 500,
                }}
              >
                {a.label}
              </span>
              <span style={{ flex: 1 }} />
              <span
                style={{ color: "var(--muted)", fontWeight: 500 }}
                className="tnum"
              >
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
  onDotClick,
}: {
  history: HistoryDay[];
  rhymeStart: number | undefined;
  onDotClick?: (day: number) => void;
}) {
  const [hoverIdx, setHoverIdx] = useState<number | null>(null);
  return (
    <section
      style={{
        background: "var(--panel)",
        border: "1px solid var(--line)",
        borderRadius: 10,
        padding: "16px 18px 18px 18px",
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          marginBottom: 12,
          gap: 12,
        }}
      >
        <div style={{ minWidth: 0, flex: 1 }}>
          <div style={{ fontSize: 14, fontWeight: 600 }}>Thread · 30 days</div>
          <div style={{ fontSize: 11, color: "var(--muted)", marginTop: 3 }}>
            {hoverIdx !== null ? (
              // Serif italic pull-quote surfaces the hovered day's narrative
              // — tiny but important UX hint that the graph has text under it.
              <span
                className="serif"
                style={{
                  fontFamily: "var(--serif)",
                  fontStyle: "italic",
                  fontSize: 13,
                  color: "var(--ink)",
                  letterSpacing: "-0.005em",
                }}
              >
                day −{history[hoverIdx].day} — &ldquo;{history[hoverIdx].text.slice(0, 70)}…&rdquo;
              </span>
            ) : (
              "Each dot is a day's average valence · hover to read the narrative"
            )}
          </div>
        </div>
        <div style={{ display: "flex", gap: 6, flexShrink: 0 }}>
          <Chip label="30d" active />
          <Chip label="90d" />
          <Chip label="YTD" />
        </div>
      </div>
      <HistorySvg
        history={history}
        rhymeStart={rhymeStart}
        onHover={setHoverIdx}
        hoverIdx={hoverIdx}
        onDotClick={onDotClick}
      />
    </section>
  );
}

function HistorySvg({
  history,
  rhymeStart,
  onHover,
  hoverIdx,
  onDotClick,
}: {
  history: HistoryDay[];
  rhymeStart: number | undefined;
  onHover: (i: number | null) => void;
  hoverIdx: number | null;
  onDotClick?: (day: number) => void;
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
          // Warm-tone highlight band behind the rhyming 7-day window. The
          // outline is a subtle rounded rect (not the dashed stroke used
          // previously) so it reads as a delicate backdrop instead of a
          // warning box.
          <>
            <rect
              x={pad.l + rhymeStart * bw}
              y={pad.t - 6}
              width={bw * 7}
              height={H + 12}
              fill="var(--warm)"
              opacity="0.09"
              rx="6"
            />
            <rect
              x={pad.l + rhymeStart * bw}
              y={pad.t - 6}
              width={bw * 7}
              height={H + 12}
              fill="none"
              stroke="var(--warm-strong)"
              strokeWidth="1"
              opacity="0.28"
              rx="6"
            />
          </>
        )}
        <path d={areaD} fill="url(#prudentThreadGrad)" />
        <path d={d} fill="none" stroke="var(--accent)" strokeWidth="2" strokeLinecap="round" />
        {pts.map((p) => (
          <g
            key={p.i}
            onMouseEnter={() => onHover(p.i)}
            onMouseLeave={() => onHover(null)}
            onClick={() => onDotClick?.(p.d.day)}
            style={{ cursor: onDotClick ? "pointer" : "default" }}
          >
            <rect x={pad.l + p.i * bw} y={pad.t} width={bw} height={H} fill="transparent" />
            <circle
              cx={p.x}
              cy={p.y}
              r={p.d.day === 0 ? 4.5 : hoverIdx === p.i ? 3.5 : 2}
              fill={p.d.day === 0 ? "var(--accent)" : "var(--panel)"}
              stroke="var(--accent)"
              strokeWidth={p.d.day === 0 ? 2 : 1.4}
            />
          </g>
        ))}
        <text
          x={pad.l}
          y={h - 4}
          fontSize="10"
          fill="var(--faint)"
          className="mono"
          fontWeight="500"
        >
          30d
        </text>
        <text
          x={pad.l + W / 2}
          y={h - 4}
          textAnchor="middle"
          fontSize="10"
          fill="var(--faint)"
          className="mono"
          fontWeight="500"
        >
          15d
        </text>
        <text
          x={pad.l + W}
          y={h - 4}
          textAnchor="end"
          fontSize="10"
          fill="var(--faint)"
          className="mono"
          fontWeight="500"
        >
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
    // Only autofocus when the modal is opened for writing. Focusing a
    // read-only textarea steals the keyboard from browser-level nav (arrow
    // keys scrolling, etc.).
    if (!readOnly) ref.current?.focus();
  }, [readOnly]);
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
              {readOnly
                ? readOnlyLabel ?? "archived entry · read only"
                : "Wed · Apr 17 · 7:04 am → now · parsing live"}
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
          {/* Newsreader serif textarea — italic placeholder, generous
              line-height so the journal feels literary, not technical. When
              read-only we disable the textarea (not hide it) so users can
              still select+copy the narrative. */}
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
              // Live source indicator — "regex" while the debounce is
              // pending or Claude is unavailable, "api" once a Claude result
              // has been stitched in. Gives the investor a concrete sense
              // of the pipeline upgrading in real time.
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
// Alternate nav views (thread / rhymes / entries / tags / patterns / engine)
// ═══════════════════════════════════════════════════════════════════════

/**
 * ThreadView — vertical list of every logged entry, newest-first.
 *
 * Each card shows the date, a pull-quote of the narrative (first 80 chars),
 * the event count, and the day's average valence as a small pill. Clicking
 * a card opens the composer as a read-only viewer.
 */
function ThreadView({
  entries,
  onOpen,
}: {
  entries: StoredEntry[];
  onOpen: (entry: StoredEntry) => void;
}) {
  if (entries.length === 0) {
    return (
      <ComingSoon
        title="No entries yet"
        description="Log your first day to see it appear here as a thread of cards."
      />
    );
  }
  return (
    <section
      style={{
        display: "flex",
        flexDirection: "column",
        gap: 10,
        minWidth: 0,
      }}
    >
      {entries.map((e) => {
        const positive = e.avg >= 50;
        return (
          <button
            key={e.id}
            onClick={() => onOpen(e)}
            style={{
              display: "grid",
              gridTemplateColumns: "80px 1fr 64px",
              gap: 16,
              alignItems: "center",
              background: "var(--panel)",
              border: "1px solid var(--line)",
              borderRadius: 10,
              padding: "14px 16px",
              textAlign: "left",
              cursor: "pointer",
              transition: "border-color 120ms ease, transform 120ms ease",
            }}
          >
            <div>
              <div
                className="mono tnum"
                style={{
                  fontSize: 11,
                  color: "var(--ink)",
                  fontWeight: 600,
                  letterSpacing: "0.01em",
                }}
              >
                {e.createdAt.slice(0, 10)}
              </div>
              <div
                className="mono"
                style={{
                  fontSize: 10,
                  color: "var(--faint)",
                  marginTop: 3,
                }}
              >
                day −{e.day}
              </div>
            </div>
            <div
              className="serif"
              style={{
                fontFamily: "var(--serif)",
                fontSize: 14,
                color: "var(--ink)",
                fontStyle: "italic",
                lineHeight: 1.5,
                overflow: "hidden",
                textOverflow: "ellipsis",
                display: "-webkit-box",
                WebkitLineClamp: 2,
                WebkitBoxOrient: "vertical",
                letterSpacing: "-0.005em",
              }}
            >
              &ldquo;{e.text.slice(0, 160)}
              {e.text.length > 160 ? "…" : ""}&rdquo;
            </div>
            <div
              style={{
                display: "flex",
                flexDirection: "column",
                alignItems: "flex-end",
                gap: 4,
              }}
            >
              <span
                className="tnum"
                style={{
                  fontSize: 14,
                  fontWeight: 600,
                  color: positive ? "var(--green)" : "var(--warm-strong)",
                  letterSpacing: "-0.02em",
                }}
              >
                {e.avg}
              </span>
              <span
                className="mono"
                style={{ fontSize: 9.5, color: "var(--faint)" }}
              >
                {e.events.length} events
              </span>
            </div>
          </button>
        );
      })}
    </section>
  );
}

/**
 * RhymesView — top rhyming day-pairs against the current history.
 *
 * Uses `findRhyme` against progressively-shortened history slices so we get
 * multiple distinct windows rather than the same top match over and over.
 */
function RhymesView({ history }: { history: HistoryDay[] }) {
  // Walk the history and compute up to 3 non-overlapping 7-day rhymes by
  // calling findRhyme against shrinking slices of the prefix. Each previous
  // match is excluded from the next search window so we don't repeat.
  const matches: { start: number; avg: number; text: string }[] = [];
  let working = history.slice(0, -1);
  for (let k = 0; k < 3 && working.length >= 14; k++) {
    const today = history.slice(-14, -1).map((d) => ({ t: d.day, v: d.avg }));
    const r = findRhyme(working, today as Point[]);
    if (!r) break;
    const win = working.slice(r.startIdx, r.startIdx + 7);
    const winAvg = Math.round(win.reduce((a, b) => a + b.avg, 0) / win.length);
    matches.push({
      start: r.startIdx,
      avg: winAvg,
      text: win[3]?.text ?? "",
    });
    // Remove the matched window from the working set so the next iteration
    // surfaces a different rhyme.
    working = [...working.slice(0, r.startIdx), ...working.slice(r.startIdx + 7)];
  }

  if (matches.length === 0) {
    return (
      <ComingSoon
        title="No rhymes yet"
        description="Rhymes appear once your history has enough data to compare against."
      />
    );
  }

  return (
    <section style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      {matches.map((m, i) => (
        <div
          key={i}
          style={{
            display: "grid",
            gridTemplateColumns: "80px 1fr 64px",
            gap: 16,
            alignItems: "center",
            background: "var(--panel)",
            border: "1px solid var(--line)",
            borderRadius: 10,
            padding: "14px 16px",
          }}
        >
          <div>
            <div
              style={{
                fontSize: 12,
                fontWeight: 600,
                color: "var(--ink)",
              }}
            >
              Rank {i + 1}
            </div>
            <div
              className="mono"
              style={{ fontSize: 10, color: "var(--faint)", marginTop: 3 }}
            >
              window day −{history[m.start]?.day ?? "?"}
            </div>
          </div>
          <div
            className="serif"
            style={{
              fontSize: 14,
              color: "var(--ink)",
              fontStyle: "italic",
              lineHeight: 1.5,
              fontFamily: "var(--serif)",
            }}
          >
            &ldquo;{m.text.slice(0, 140)}
            {m.text.length > 140 ? "…" : ""}&rdquo;
          </div>
          <div
            className="tnum"
            style={{
              fontSize: 14,
              fontWeight: 600,
              color: "var(--accent-ink)",
              textAlign: "right",
              letterSpacing: "-0.02em",
            }}
          >
            {m.avg}
            <div
              className="mono"
              style={{
                fontSize: 9.5,
                color: "var(--faint)",
                fontWeight: 500,
                marginTop: 2,
              }}
            >
              avg valence
            </div>
          </div>
        </div>
      ))}
    </section>
  );
}

/**
 * EntriesView — tabular list of stored entries with delete per row. Zero
 * pagination for now since the demo bar is "last few dozen entries".
 */
function EntriesView({
  entries,
  onOpen,
  onRemove,
}: {
  entries: StoredEntry[];
  onOpen: (e: StoredEntry) => void;
  onRemove: (id: string) => void;
}) {
  if (entries.length === 0) {
    return (
      <ComingSoon
        title="No entries"
        description="Anything you save shows up here — with delete + export per row."
      />
    );
  }
  return (
    <section
      style={{
        background: "var(--panel)",
        border: "1px solid var(--line)",
        borderRadius: 10,
        overflow: "hidden",
      }}
    >
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "110px 90px 1fr 70px 60px 70px",
          gap: 12,
          padding: "12px 18px",
          borderBottom: "1px solid var(--line)",
          fontSize: 10,
          fontWeight: 600,
          color: "var(--muted)",
          letterSpacing: "0.08em",
          textTransform: "uppercase",
        }}
        className="mono"
      >
        <span>Date</span>
        <span>Day</span>
        <span>Excerpt</span>
        <span style={{ textAlign: "right" }}>Avg</span>
        <span style={{ textAlign: "right" }}>Events</span>
        <span />
      </div>
      {entries.map((e) => (
        <div
          key={e.id}
          style={{
            display: "grid",
            gridTemplateColumns: "110px 90px 1fr 70px 60px 70px",
            gap: 12,
            padding: "12px 18px",
            borderBottom: "1px solid var(--line)",
            alignItems: "center",
            fontSize: 12.5,
          }}
        >
          <span className="tnum mono" style={{ color: "var(--ink)" }}>
            {e.createdAt.slice(0, 10)}
          </span>
          <span className="mono" style={{ color: "var(--muted)" }}>
            day −{e.day}
          </span>
          <button
            onClick={() => onOpen(e)}
            style={{
              textAlign: "left",
              color: "var(--ink)",
              fontStyle: "italic",
              fontFamily: "var(--serif)",
              fontSize: 13,
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
            }}
          >
            &ldquo;{e.text.slice(0, 120)}
            {e.text.length > 120 ? "…" : ""}&rdquo;
          </button>
          <span
            className="tnum"
            style={{
              textAlign: "right",
              fontWeight: 600,
              color: e.avg >= 50 ? "var(--green)" : "var(--warm-strong)",
            }}
          >
            {e.avg}
          </span>
          <span
            className="tnum"
            style={{ textAlign: "right", color: "var(--muted)" }}
          >
            {e.events.length}
          </span>
          <div style={{ textAlign: "right" }}>
            <button
              onClick={() => onRemove(e.id)}
              style={{
                fontSize: 11,
                padding: "5px 9px",
                border: "1px solid var(--line-mid)",
                borderRadius: 6,
                color: "var(--warm-strong)",
                fontWeight: 500,
                background: "var(--panel)",
              }}
            >
              Delete
            </button>
          </div>
        </div>
      ))}
    </section>
  );
}

/**
 * EngineLogsView — read-only snapshot of the live parse pipeline.
 *
 * Surfaces the last parser source (regex / api / idle), event count, and
 * error status. Gives investors a concrete hook to ask "how does the
 * NL-to-TS pipeline actually work?" without opening devtools.
 */
function EngineLogsView({
  source,
  loading,
  error,
  eventCount,
}: {
  source: "api" | "regex" | "idle";
  loading: boolean;
  error: string | null;
  eventCount: number;
}) {
  const rows: { label: string; value: React.ReactNode }[] = [
    { label: "source", value: source },
    { label: "loading", value: loading ? "true" : "false" },
    { label: "event count", value: eventCount },
    { label: "error", value: error ?? "none" },
    { label: "route", value: "POST /api/prudent/parse" },
    { label: "debounce", value: "350ms" },
  ];
  return (
    <section
      style={{
        background: "var(--panel)",
        border: "1px solid var(--line)",
        borderRadius: 10,
        padding: "18px 20px",
      }}
    >
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          gap: 10,
        }}
      >
        {rows.map((r) => (
          <div
            key={r.label}
            style={{
              display: "grid",
              gridTemplateColumns: "140px 1fr",
              alignItems: "center",
              fontSize: 13,
              padding: "6px 0",
              borderBottom: "1px solid var(--line)",
            }}
          >
            <span
              className="mono"
              style={{
                fontSize: 10,
                color: "var(--muted)",
                letterSpacing: "0.08em",
                textTransform: "uppercase",
                fontWeight: 600,
              }}
            >
              {r.label}
            </span>
            <span
              className="mono tnum"
              style={{ color: "var(--ink)", fontWeight: 500 }}
            >
              {r.value}
            </span>
          </div>
        ))}
      </div>
    </section>
  );
}

/**
 * ComingSoon — thin empty-state card used by `tags`, `patterns`, and the
 * no-entries fallbacks.
 */
function ComingSoon({
  title,
  description,
}: {
  title: string;
  description: string;
}) {
  return (
    <section
      style={{
        background: "var(--panel)",
        border: "1px solid var(--line)",
        borderRadius: 10,
        padding: "56px 24px",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        textAlign: "center",
        gap: 10,
      }}
    >
      <div
        style={{
          width: 36,
          height: 36,
          borderRadius: 10,
          background: "var(--accent-soft)",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          color: "var(--accent-ink)",
        }}
      >
        <svg
          width="18"
          height="18"
          viewBox="0 0 16 16"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.5"
        >
          <circle cx="8" cy="8" r="5.5" />
          <path d="M8 5v3l2 1.5" />
        </svg>
      </div>
      <div style={{ fontSize: 15, fontWeight: 600, color: "var(--ink)" }}>
        {title}
      </div>
      <div
        style={{
          fontSize: 12.5,
          color: "var(--muted)",
          maxWidth: 340,
          lineHeight: 1.5,
        }}
      >
        {description}
      </div>
    </section>
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
        padding: "14px 2px 0 2px",
        borderTop: "1px solid var(--line)",
        fontSize: 11,
        color: "var(--faint)",
        marginTop: 4,
      }}
    >
      <div style={{ display: "flex", gap: 18 }}>
        <span>Privacy</span>
        <span>Terms</span>
        <span>Help Center</span>
        <span>Feedback</span>
      </div>
      <div className="mono" style={{ letterSpacing: "0.02em" }}>
        © 2026 The Similarity · engine v0.3
      </div>
    </div>
  );
}

interface TweaksPanelProps {
  tweaks: Tweaks;
  setTweak: <K extends keyof Tweaks>(k: K, v: Tweaks[K]) => void;
}

function TweaksPanel({ tweaks, setTweak }: TweaksPanelProps) {
  // Generic text-label option group (theme / compare). Accent is rendered
  // separately as color swatches because a HEX chip reads faster than a word.
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

  // Accent-specific chooser — each option is a small filled color chip rather
  // than the accent name. Reads at a glance when you're A/B-ing palettes.
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

// A single row in the Tweaks panel: left-aligned label, right-aligned control.
// Kept compact (justified-between) so the panel stays visually calm.
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
