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
 *   t            -> toggle theme
 *   Shift+T      -> toggle tweaks panel
 */

import { useState, useEffect, useCallback } from "react";
import { Workstation, WorkstationSettings } from "../components/workstation/workstation";
import { RepresentSurface, SimulateSurface, EvaluateSurface, RenderSurface, DecideSurface } from "../components/surfaces";
import { CommandPalette } from "../components/command-palette";
import { TweaksPanel } from "../components/tweaks-panel";

// ── Verb definitions for the 6 surfaces ─────────────────────────────────
const VERBS = [
  { k: "retrieve", n: "01", name: "Retrieve", q: "What rhymes?" },
  { k: "represent", n: "02", name: "Represent", q: "Map state" },
  { k: "simulate", n: "03", name: "Simulate", q: "Project futures" },
  { k: "evaluate", n: "04", name: "Evaluate", q: "Did it hold?" },
  { k: "render", n: "05", name: "Render", q: "Walk the space" },
  { k: "decide", n: "06", name: "Decide", q: "From analog to action" },
];

const DEFAULTS: WorkstationSettings = {
  theme: "light",
  kAnalogs: 6,
  horizon: 60,
  showAnalogs: "top3",
  showCone: true,
};

export default function Page() {
  // ── State ───────────────────────────────────────────────────────────
  const [settings, setSettings] = useState<WorkstationSettings>(() => {
    if (typeof window === "undefined") return DEFAULTS;
    try {
      const saved = JSON.parse(localStorage.getItem("ts-settings") || "null");
      return { ...DEFAULTS, ...(saved || {}) };
    } catch { return DEFAULTS; }
  });

  const [surface, setSurface] = useState(() => {
    if (typeof window === "undefined") return "retrieve";
    return localStorage.getItem("ts-surface") || "retrieve";
  });

  const [tweaksOpen, setTweaksOpen] = useState(false);
  const [cmdOpen, setCmdOpen] = useState(false);

  // ── Persist theme + settings ────────────────────────────────────────
  useEffect(() => {
    document.documentElement.setAttribute("data-theme", settings.theme);
    document.documentElement.style.background = settings.theme === "dark" ? "#0e0d0b" : "#faf9f6";
    localStorage.setItem("ts-settings", JSON.stringify(settings));
  }, [settings]);

  useEffect(() => { localStorage.setItem("ts-surface", surface); }, [surface]);

  const updateSettings = useCallback((s: WorkstationSettings) => {
    setSettings(s);
  }, []);

  // ── Keyboard shortcuts ──────────────────────────────────────────────
  useEffect(() => {
    let lastG = 0;
    const jumpMap: Record<string, string> = {
      r: "retrieve", e: "represent", s: "simulate",
      v: "evaluate", n: "render", d: "decide"
    };

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
            {Array.from({ length: 2 }).map((_, k) => (
              <span key={k} style={{ display: "contents" }}>
                <span className="marquee__item">Structural intelligence for time, state &amp; simulation</span>
                <span className="marquee__item"><b>SPX</b> 5284.12 <span style={{ color: "#6fb88e" }}>+0.38%</span></span>
                <span className="marquee__item"><b>NDX</b> 18442.50 <span style={{ color: "#6fb88e" }}>+0.52%</span></span>
                <span className="marquee__item"><b>VIX</b> 13.88 <span style={{ color: "#c77272" }}>&minus;2.14%</span></span>
                <span className="marquee__item"><b>analogs</b> 1,204 runs &middot; calibration B+</span>
                <span className="marquee__item">Find what rhymes &middot; model what evolves &middot; simulate what comes next</span>
                <span className="marquee__item"><b>worlds</b> 42 scenarios active</span>
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
      <main className="page">
        {surface === "retrieve" && <Workstation settings={settings} onSettings={updateSettings} />}
        {surface === "represent" && <RepresentSurface />}
        {surface === "simulate" && <SimulateSurface />}
        {surface === "evaluate" && <EvaluateSurface />}
        {surface === "render" && <RenderSurface />}
        {surface === "decide" && <DecideSurface />}
      </main>

      {/* ── Status bar ─────────────────────────────────────────── */}
      <footer className="statusbar">
        <span className="statusbar__item"><b>engine</b> v4.14 &middot; nine lenses</span>
        <span className="statusbar__sep">&boxv;</span>
        <span className="statusbar__item">feed <b>SPX / synthetic</b></span>
        <span className="statusbar__sep">&boxv;</span>
        <span className="statusbar__item">window <b>{currentVerb.name}</b></span>
        <div className="statusbar__right">
          <span className="statusbar__item">press <span className="kbd">/</span> to search</span>
          <span className="statusbar__item">press <span className="kbd">g</span> <span className="kbd">r</span> / <span className="kbd">s</span> / <span className="kbd">v</span> to jump</span>
          <span className="statusbar__item"><b>Apr 17, 2026 &middot; 14:22 NY</b></span>
        </div>
      </footer>

      {/* ── Overlays ───────────────────────────────────────────── */}
      <TweaksPanel settings={settings} onSettings={updateSettings} visible={tweaksOpen} />
      <CommandPalette open={cmdOpen} onClose={() => setCmdOpen(false)} onNav={onCmdNav} />
    </div>
  );
}
