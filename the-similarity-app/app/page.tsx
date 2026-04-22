"use client";

/**
 * Root page — the Bloomberg-terminal workstation app shell.
 *
 * Layout: marquee strip (44px) + nav bar (56px) + page content (fluid)
 * + status bar (26px). Surfaces are routed via in-page state, not URL
 * routes, to maintain the single-page terminal feel.
 *
 * Keyboard shortcuts:
 *   /  or Cmd+K  -> command palette
 *   g r/e/s/v/n/d -> jump to surface (two-key chord: press g, then letter)
 *                   When NEXT_PUBLIC_SHOW_PREVIEW_SURFACES is not "true" only
 *                   `g r` (retrieve) works — the other 5 surfaces are hidden.
 *   t            -> toggle theme
 *   Shift+T      -> toggle tweaks panel
 *
 * Feature flags (build-time, NEXT_PUBLIC_* inlined by Next):
 *   NEXT_PUBLIC_DATA_MODE               -> "live" | "demo" (default "demo")
 *                                          drives the status-bar feed label.
 *   NEXT_PUBLIC_SHOW_PREVIEW_SURFACES   -> "true" | "false" (default "false")
 *                                          shows the 5 preview surfaces when
 *                                          true; clients see only Retrieve
 *                                          when false.
 */

import { useState, useEffect, useCallback } from "react";
import { Workstation, WorkstationSettings } from "../components/workstation/workstation";
import { RepresentSurface, SimulateSurface, EvaluateSurface, RenderSurface, DecideSurface } from "../components/surfaces";
import { CommandPalette } from "../components/command-palette";
import { TweaksPanel } from "../components/tweaks-panel";

/*
 * Feed mode — honest label for the status-bar "feed X" badge.
 *
 * Values: "live" (connected to real market data) | "demo" (synthetic /
 * fallback / canned data). Sourced from NEXT_PUBLIC_DATA_MODE; defaults
 * to "demo" when unset so we never falsely claim to be live.
 *
 * Rationale: the previous label was "feed SPX / synthetic" regardless of
 * actual state — misleading in both directions (says "SPX" even when the
 * backend is offline, says "synthetic" even when a live feed is attached).
 * An explicit env-var-driven label is honest: it says exactly what it is.
 * When we later gain a reliable hook into the workstation's online/offline
 * state, this can become a derived value instead of a deploy-time constant.
 */
const DATA_MODE: "live" | "demo" =
  process.env.NEXT_PUBLIC_DATA_MODE === "live" ? "live" : "demo";

/*
 * Preview-surfaces flag.
 *
 * The 5 non-Retrieve verbs (Represent / Simulate / Evaluate / Render / Decide)
 * are editorial mockups with no real interactivity. Clients clicking them
 * expect working features and find theater. Until each surface has a real
 * backend, it's hidden behind this flag.
 *
 * Default (false): only Retrieve renders, only Retrieve is nav-reachable,
 * only `g r` works as a jump chord, command palette navigates only to
 * retrieve. Clients never see inert mocks.
 *
 * True: the full 6-verb layout is preserved so devs can still preview
 * surfaces in progress. Turn on by setting
 *   NEXT_PUBLIC_SHOW_PREVIEW_SURFACES=true
 *
 * Important: this is a build-time constant (Next inlines NEXT_PUBLIC_*
 * env vars at build time), so toggling requires a rebuild. That's fine —
 * it's a deploy-level switch, not a runtime toggle.
 */
const SHOW_PREVIEW: boolean =
  process.env.NEXT_PUBLIC_SHOW_PREVIEW_SURFACES === "true";

// ── Verb definitions for the 6 surfaces ─────────────────────────────────
// ALL_VERBS is the full editorial roster. VERBS is the filtered view we
// actually render: when SHOW_PREVIEW is false we ship with only Retrieve.
const ALL_VERBS = [
  { k: "retrieve", n: "01", name: "Retrieve", q: "What rhymes?" },
  { k: "represent", n: "02", name: "Represent", q: "Map state" },
  { k: "simulate", n: "03", name: "Simulate", q: "Project futures" },
  { k: "evaluate", n: "04", name: "Evaluate", q: "Did it hold?" },
  { k: "render", n: "05", name: "Render", q: "Walk the space" },
  { k: "decide", n: "06", name: "Decide", q: "From analog to action" },
];
const VERBS = SHOW_PREVIEW ? ALL_VERBS : ALL_VERBS.filter(v => v.k === "retrieve");

const DEFAULTS: WorkstationSettings = {
  theme: "light",
  kAnalogs: 6,
  horizon: 60,
  // Show every top-K match as its own forward projection by default.
  // This is the product's core loop: "here are K analogs, each drawing
  // a different possible future" — gating the chart to only 3 hid most
  // of the signal we just computed.
  showAnalogs: "all",
  showCone: true,
};

export default function Page() {
  // ── State ───────────────────────────────────────────────────────────
  const [settings, setSettings] = useState<WorkstationSettings>(() => {
    if (typeof window === "undefined") return DEFAULTS;
    try {
      const saved = JSON.parse(localStorage.getItem("ts-settings") || "null");
      const merged = { ...DEFAULTS, ...(saved || {}) };
      // One-time migration: the old `"top3"` default silently dropped 3+
      // of the top-K analogs from the chart. Promote it to `"all"` once
      // so returning users see every match as its own forward line.
      if (merged.showAnalogs === "top3") merged.showAnalogs = "all";
      return merged;
    } catch { return DEFAULTS; }
  });

  const [surface, setSurface] = useState(() => {
    if (typeof window === "undefined") return "retrieve";
    return localStorage.getItem("ts-surface") || "retrieve";
  });

  const [tweaksOpen, setTweaksOpen] = useState(false);
  const [cmdOpen, setCmdOpen] = useState(false);

  /*
   * nyClock — the status-bar timestamp rendered in America/New_York time,
   * formatted as "MMM D, YYYY · HH:mm NY" (24h). Initial value is empty so
   * server-rendered HTML and the first client render agree (hydration-safe);
   * the useEffect below fills it in and then ticks every 60s.
   */
  const [nyClock, setNyClock] = useState<string>("");

  // ── Persist theme + settings ────────────────────────────────────────
  useEffect(() => {
    document.documentElement.setAttribute("data-theme", settings.theme);
    document.documentElement.style.background = settings.theme === "dark" ? "#0e0d0b" : "#faf9f6";
    localStorage.setItem("ts-settings", JSON.stringify(settings));
  }, [settings]);

  useEffect(() => { localStorage.setItem("ts-surface", surface); }, [surface]);

  /*
   * Live NY-time clock for the status bar.
   *
   * Invariant: the rendered string is always the current America/New_York
   * wall-clock time at minute resolution. It MUST NOT be a hardcoded literal —
   * a frozen timestamp on the root page silently tells clients "this UI is
   * a mock" and destroys credibility.
   *
   * Lifecycle: populate on mount (after hydration), then tick every 60s.
   * We intentionally don't tick every second: the UI shows minute resolution
   * and we don't want to cause a re-render 60x more often than needed.
   *
   * Format: "MMM D, YYYY · HH:mm NY" (24h), e.g. "Apr 20, 2026 · 09:47 NY".
   * The middle-dot separator matches the surrounding status-bar typography.
   */
  useEffect(() => {
    const formatNY = () => {
      const now = new Date();
      // Intl.DateTimeFormat is the only reliable way to render a Date in a
      // specific IANA timezone without pulling in date-fns-tz or moment-tz.
      const datePart = new Intl.DateTimeFormat("en-US", {
        timeZone: "America/New_York",
        month: "short",
        day: "numeric",
        year: "numeric",
      }).format(now); // e.g. "Apr 20, 2026"
      const timePart = new Intl.DateTimeFormat("en-US", {
        timeZone: "America/New_York",
        hour: "2-digit",
        minute: "2-digit",
        hour12: false,
      }).format(now); // e.g. "09:47"
      return `${datePart} \u00B7 ${timePart} NY`;
    };

    setNyClock(formatNY());
    // 60s tick — matches the minute-resolution format. Clearing the interval
    // on unmount prevents a dangling timer updating state on a dead tree.
    const id = window.setInterval(() => setNyClock(formatNY()), 60_000);
    return () => window.clearInterval(id);
  }, []);

  const updateSettings = useCallback((s: WorkstationSettings) => {
    setSettings(s);
  }, []);

  // ── Keyboard shortcuts ──────────────────────────────────────────────
  useEffect(() => {
    let lastG = 0;
    /*
     * jumpMap — two-key chord destinations. When SHOW_PREVIEW is false we
     * only allow `g r` (retrieve) so a keyboard-savvy client can't shortcut
     * their way into a preview surface that isn't advertised in the nav.
     */
    const jumpMap: Record<string, string> = SHOW_PREVIEW
      ? { r: "retrieve", e: "represent", s: "simulate",
          v: "evaluate", n: "render", d: "decide" }
      : { r: "retrieve" };

    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement).tagName;
      if (tag === "INPUT" || tag === "TEXTAREA") return;

      // Cmd+K or /  -> command palette
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault(); setCmdOpen(true); return;
      }
      if (e.key === "/" && !e.metaKey && !e.ctrlKey) {
        e.preventDefault(); setCmdOpen(true); return;
      }
      if (e.key === "Escape") { setCmdOpen(false); return; }

      // g + letter chord -> jump to surface
      if (e.key.toLowerCase() === "g") { lastG = Date.now(); return; }
      if (Date.now() - lastG < 900 && jumpMap[e.key.toLowerCase()]) {
        setSurface(jumpMap[e.key.toLowerCase()]); lastG = 0; return;
      }

      // Shift+T -> toggle tweaks
      if (e.key === "T" && e.shiftKey) { setTweaksOpen(o => !o); return; }
      // t -> toggle theme
      if (e.key === "t" && !e.shiftKey) {
        setSettings(prev => ({ ...prev, theme: prev.theme === "dark" ? "light" : "dark" }));
        return;
      }
    };

    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const onCmdNav = useCallback((v: string) => {
    if (v === "theme") {
      setSettings(prev => ({ ...prev, theme: prev.theme === "dark" ? "light" : "dark" }));
    } else if (v === "tweaks") {
      setTweaksOpen(o => !o);
    } else {
      /*
       * Surface navigation guard.
       *
       * When preview surfaces are hidden we ignore command-palette nav
       * requests for any verb other than retrieve. The palette itself is
       * a shared component that doesn't know about the flag — this is the
       * enforcement point. Silently dropping the request is fine: the
       * palette closes, the user stays on retrieve, nothing appears to break.
       */
      if (!SHOW_PREVIEW && v !== "retrieve") return;
      setSurface(v);
    }
  }, []);

  const currentVerb = VERBS.find(v => v.k === surface) || VERBS[0];

  return (
    <div className="app">
      {/* ── Marquee strip ──────────────────────────────────────── */}
      <div className="marquee">
        <span className="marquee__brand">THE SIMILARITY</span>
        <div style={{ overflow: "hidden", flex: 1 }}>
          <div className="marquee__track">
            {/*
             * Marquee content — statements that are true without any live backend.
             * Hardcoded ticker prices (SPX/NDX/VIX), "analogs 1,204 runs", and
             * "worlds 42 scenarios active" were removed: frozen numbers that never
             * update destroy credibility instantly with a quant or PM. If we want
             * live market/analog counts in the marquee later, they must come from
             * a real feed, not literals. Keep only tagline-style content here.
             */}
            {Array.from({ length: 2 }).map((_, k) => (
              <span key={k} style={{ display: "contents" }}>
                <span className="marquee__item">Structural intelligence for time, state &amp; simulation</span>
                <span className="marquee__item">Find what rhymes &middot; model what evolves &middot; simulate what comes next</span>
                <span className="marquee__item"><b>engine</b> nine lenses / four layers</span>
              </span>
            ))}
          </div>
        </div>
        <div className="marquee__right">
          <span className="dot" />
          <span>engine live</span>
        </div>
      </div>

      {/* ── Top navigation ─────────────────────────────────────── */}
      <header className="nav">
        <div className="nav__brand">
          <div className="nav__logo">
            <svg width="26" height="26" viewBox="0 0 26 26">
              <circle cx="13" cy="13" r="11" fill="none" stroke="var(--ink)" strokeWidth="1.2" />
              <circle cx="13" cy="13" r="6" fill="none" stroke="var(--ink)" strokeWidth="1.2" />
              <circle cx="13" cy="13" r="1.8" fill="var(--ink)" />
            </svg>
          </div>
          <div className="nav__word">The <em>Similarity</em></div>
        </div>
        <div className="nav__verbs">
          {VERBS.map(v => (
            <button key={v.k} className="nav__verb"
              data-active={surface === v.k ? "true" : undefined}
              onClick={() => setSurface(v.k)}>
              <span className="nav__verb__num">{v.n}</span>
              <span className="nav__verb__name">{v.name}</span>
            </button>
          ))}
        </div>
        <div className="nav__right">
          <button className="nav__search" onClick={() => setCmdOpen(true)}>
            <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.3">
              <circle cx="5" cy="5" r="3.5" />
              <line x1="7.5" y1="7.5" x2="11" y2="11" />
            </svg>
            <span>Search analogs, runs, symbols&hellip;</span>
            <span className="label" style={{ marginLeft: "auto", fontSize: 9 }}>&#8984;K</span>
          </button>
          <button className="nav__iconbtn" title="Tweaks (\u21E7T)" onClick={() => setTweaksOpen(o => !o)}>
            <svg width="13" height="13" viewBox="0 0 13 13" fill="none" stroke="currentColor" strokeWidth="1.2">
              <circle cx="6.5" cy="6.5" r="2" />
              <line x1="6.5" y1="1" x2="6.5" y2="3.5" />
              <line x1="6.5" y1="9.5" x2="6.5" y2="12" />
              <line x1="1" y1="6.5" x2="3.5" y2="6.5" />
              <line x1="9.5" y1="6.5" x2="12" y2="6.5" />
            </svg>
          </button>
          <button className="nav__iconbtn" title="Account">
            <span className="mono" style={{ fontSize: 10, fontWeight: 600 }}>LN</span>
          </button>
        </div>
      </header>

      {/* ── Page content ───────────────────────────────────────── */}
      {/*
       * Surface render guard.
       *
       * Retrieve is always rendered. The 5 preview surfaces only render when
       * NEXT_PUBLIC_SHOW_PREVIEW_SURFACES=true. Because `surface` is also
       * rehydrated from localStorage, a returning client who previously
       * landed on (say) "simulate" while the flag was true and now visits
       * with the flag false would fall through to nothing — we'd show an
       * empty <main>. Guard against that by rendering Workstation as the
       * default when SHOW_PREVIEW is false and surface is anything other
       * than "retrieve".
       */}
      <main className="page">
        {!SHOW_PREVIEW && (
          <Workstation settings={settings} onSettings={updateSettings} />
        )}
        {SHOW_PREVIEW && surface === "retrieve" && <Workstation settings={settings} onSettings={updateSettings} />}
        {SHOW_PREVIEW && surface === "represent" && <RepresentSurface />}
        {SHOW_PREVIEW && surface === "simulate" && <SimulateSurface />}
        {SHOW_PREVIEW && surface === "evaluate" && <EvaluateSurface />}
        {SHOW_PREVIEW && surface === "render" && <RenderSurface />}
        {SHOW_PREVIEW && surface === "decide" && <DecideSurface />}
      </main>

      {/* ── Status bar ─────────────────────────────────────────── */}
      <footer className="statusbar">
        <span className="statusbar__item"><b>engine</b> v4.14 &middot; nine lenses</span>
        <span className="statusbar__sep">&boxv;</span>
        <span className="statusbar__item">feed <b>{DATA_MODE}</b></span>
        <span className="statusbar__sep">&boxv;</span>
        <span className="statusbar__item">window <b>{currentVerb.name}</b></span>
        <div className="statusbar__right">
          <span className="statusbar__item">press <span className="kbd">/</span> to search</span>
          {/*
           * Jump-chord hint. When preview surfaces are hidden there's only
           * one jump target (retrieve), so advertising s/v would be a lie.
           */}
          {SHOW_PREVIEW ? (
            <span className="statusbar__item">press <span className="kbd">g</span> <span className="kbd">r</span> / <span className="kbd">s</span> / <span className="kbd">v</span> to jump</span>
          ) : (
            <span className="statusbar__item">press <span className="kbd">g</span> <span className="kbd">r</span> to jump</span>
          )}
          <span className="statusbar__item"><b>{nyClock}</b></span>
        </div>
      </footer>

      {/* ── Overlays ───────────────────────────────────────────── */}
      <TweaksPanel settings={settings} onSettings={updateSettings} visible={tweaksOpen} />
      <CommandPalette open={cmdOpen} onClose={() => setCmdOpen(false)} onNav={onCmdNav} />
    </div>
  );
}
