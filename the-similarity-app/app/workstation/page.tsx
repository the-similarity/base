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
 *   ?            -> keyboard-shortcuts help modal (toggle)
 *   Esc          -> close any open overlay (palette / help)
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
// Route moved from `/` to `/workstation`: imports climb one extra level
// because the file now lives at app/workstation/page.tsx instead of
// app/page.tsx. Behavior unchanged.
import { Workstation, WorkstationSettings } from "../../components/workstation/workstation";
import { RepresentSurface, SimulateSurface, EvaluateSurface, RenderSurface, DecideSurface } from "../../components/surfaces";
import { CommandPalette } from "../../components/command-palette";
import { TweaksPanel } from "../../components/tweaks-panel";
import { ShortcutsHelp } from "../../components/shortcuts-help";
import { parseUrlState } from "../../lib/url-state";

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
  // P10-P90 cone hidden by default — the individual analog lines already
  // show the range of possible futures and the cone adds visual clutter
  // on top of them. Users can toggle it on from the tweaks panel when
  // they want the band back.
  showCone: false,
};

export default function Page() {
  /*
   * Settings hydration priority: defaults < localStorage < URL.
   *
   * On first mount we compose the settings object in three layers:
   *   1. DEFAULTS  — hardcoded baseline.
   *   2. `ts-settings` in localStorage — the user's saved preferences.
   *   3. URL params — the share-link override; wins when present.
   *
   * Only the URL fields that map onto WorkstationSettings (theme, k,
   * horizon, chartMode, showAnalogs) participate here; the workstation
   * handles the rest (dataset, window, viewRange, pinned) internally.
   *
   * This order is WHY URL state works for "send a link to a colleague":
   * their localStorage is irrelevant for the fields the link pins.
   * Fields not in the link still fall back to their saved preferences,
   * so a link that only pins `?h=180` doesn't wipe their theme.
   */
  const [settings, setSettings] = useState<WorkstationSettings>(() => {
    if (typeof window === "undefined") return DEFAULTS;
    let saved: Partial<WorkstationSettings> = {};
    try {
      saved = JSON.parse(localStorage.getItem("ts-settings") || "null") || {};
    } catch {
      // localStorage parse failed — carry on with empty saved.
    }
    // One-time migration: the old `"top3"` default silently dropped 3+
    // of the top-K analogs from the chart. Promote it to `"all"` once
    // so returning users see every match as its own forward line.
    if (saved.showAnalogs === "top3") saved.showAnalogs = "all";
    // Force-hide the P10-P90 cone ONCE for returning users. Anyone who
    // loaded the app before the default flip has `showCone: true`
    // baked into localStorage and keeps seeing the band no matter
    // what we change in DEFAULTS. A one-shot migration flag stops us
    // from clobbering a user who later turns the cone back on via
    // the tweaks panel — we only flip to false if we haven't already
    // run this migration on their machine.
    try {
      if (!localStorage.getItem("ts-migration-hide-cone")) {
        if (saved.showCone === true) saved.showCone = false;
        localStorage.setItem("ts-migration-hide-cone", "1");
      }
    } catch {
      // localStorage unavailable — no-op; fall back to the raw saved value.
    }
    // `"pro"` chart mode was replaced by `"candle"` (which still uses
    // lightweight-charts, but renders OHLC candlesticks when available).
    // Cast the saved value loosely since stale localStorage may carry
    // a mode that's no longer in the union.
    if ((saved as { chartMode?: string }).chartMode === "pro") {
      (saved as { chartMode?: string }).chartMode = "candle";
    }
    // URL takes priority per-key over both defaults and saved.
    const u = parseUrlState(window.location.search);
    const fromUrl: Partial<WorkstationSettings> = {};
    if (u.theme !== undefined) fromUrl.theme = u.theme;
    if (u.k !== undefined) fromUrl.kAnalogs = u.k;
    if (u.horizon !== undefined) fromUrl.horizon = u.horizon;
    if (u.chartMode !== undefined) {
      // URL may still carry a legacy "pro" token; promote to "candle"
      // on the way into settings, same rule as the localStorage migration
      // a few lines above.
      fromUrl.chartMode = u.chartMode === "pro" ? "candle" : u.chartMode;
    }
    if (u.showAnalogs !== undefined) fromUrl.showAnalogs = u.showAnalogs;
    return { ...DEFAULTS, ...saved, ...fromUrl };
  });

  const [surface, setSurface] = useState(() => {
    if (typeof window === "undefined") return "retrieve";
    // URL `sr` param wins over localStorage so a share-link to a specific
    // surface (when preview surfaces are enabled) restores correctly.
    const u = parseUrlState(window.location.search);
    if (u.surface) return u.surface;
    return localStorage.getItem("ts-surface") || "retrieve";
  });

  const [tweaksOpen, setTweaksOpen] = useState(false);
  const [cmdOpen, setCmdOpen] = useState(false);
  /*
   * helpOpen — controls the ShortcutsHelp overlay (`?` key).
   *
   * Kept as a separate flag from cmdOpen so both overlays can coexist
   * in the DOM but only one renders at a time (we close the other when
   * one opens — see the key handler below). Initial state is false on
   * both server and client, so this is hydration-safe with no need for
   * lazy initialization.
   */
  const [helpOpen, setHelpOpen] = useState(false);

  /*
   * nyClock — the status-bar timestamp rendered in America/Los_Angeles
   * (Pacific) time, formatted as "MMM D, YYYY · HH:mm SF" (24h). Founder
   * is in SF so the live timestamp reads "SF" - mirrors the home-page
   * clock. Variable name is kept as `nyClock` for legacy reasons; the
   * rendered content is the authoritative thing, not the identifier.
   * Initial value is empty so server-rendered HTML and the first client
   * render agree (hydration-safe); the useEffect below fills it in and
   * then ticks every 60s.
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
   * Live SF-time clock for the status bar.
   *
   * Invariant: the rendered string is always the current
   * America/Los_Angeles wall-clock time at minute resolution. It MUST
   * NOT be a hardcoded literal - a frozen timestamp on the root page
   * silently tells clients "this UI is a mock" and destroys credibility.
   *
   * Lifecycle: populate on mount (after hydration), then tick every 60s.
   * We intentionally don't tick every second: the UI shows minute
   * resolution and we don't want to cause a re-render 60x more often
   * than needed.
   *
   * Format: "MMM D, YYYY · HH:mm SF" (24h), e.g. "Apr 20, 2026 · 09:47 SF".
   * The middle-dot separator matches the surrounding status-bar
   * typography.
   */
  useEffect(() => {
    const formatNY = () => {
      const now = new Date();
      // Intl.DateTimeFormat is the only reliable way to render a Date in a
      // specific IANA timezone without pulling in date-fns-tz or moment-tz.
      const datePart = new Intl.DateTimeFormat("en-US", {
        timeZone: "America/Los_Angeles",
        month: "short",
        day: "numeric",
        year: "numeric",
      }).format(now); // e.g. "Apr 20, 2026"
      const timePart = new Intl.DateTimeFormat("en-US", {
        timeZone: "America/Los_Angeles",
        hour: "2-digit",
        minute: "2-digit",
        hour12: false,
      }).format(now); // e.g. "09:47"
      return `${datePart} \u00B7 ${timePart} SF`;
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
        e.preventDefault(); setHelpOpen(false); setCmdOpen(true); return;
      }
      if (e.key === "/" && !e.metaKey && !e.ctrlKey) {
        e.preventDefault(); setHelpOpen(false); setCmdOpen(true); return;
      }
      /*
       * `?` -> shortcuts-help modal.
       *
       * On US keyboards `?` is Shift+/ — matching `e.key === "?"`
       * catches the rendered character regardless of layout, so this
       * also works for AZERTY and other layouts where `?` does NOT
       * require Shift. We check !metaKey/!ctrlKey to avoid stealing
       * OS-level shortcuts that also produce `?`.
       *
       * Closes the command palette if open so the two overlays never
       * stack — single-overlay invariant keeps Esc handling simple.
       */
      if (e.key === "?" && !e.metaKey && !e.ctrlKey) {
        e.preventDefault();
        setCmdOpen(false);
        setHelpOpen(o => !o);
        return;
      }
      /*
       * Escape closes any open overlay. We close all three flags
       * unconditionally — closing an already-closed overlay is a
       * no-op, so there's no reason to branch.
       */
      if (e.key === "Escape") {
        setCmdOpen(false);
        setHelpOpen(false);
        return;
      }

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
      {/* ── Marquee strip ──────────────────────────────────────────
          The only top-of-page chrome now. Holds the brand wordmark,
          the rolling tagline, and the moved-over search/tweaks/account
          cluster. The old `header.nav` was deleted — single-surface
          product, no verbs to gate, no second row of chrome needed. */}
      <div className="marquee">
        {/* Brand: the circle-in-circle icon + italic wordmark. Lives in
            the marquee now since the header row was removed. The
            `.brand` wrapper opts out of the marquee's uppercase-mono
            treatment so the wordmark renders in its own serif. */}
        <div className="brand">
          <div className="brand__logo" aria-hidden="true">
            <svg width="22" height="22" viewBox="0 0 26 26">
              <circle cx="13" cy="13" r="11" fill="none" stroke="var(--ink)" strokeWidth="1.2" />
              <circle cx="13" cy="13" r="6" fill="none" stroke="var(--ink)" strokeWidth="1.2" />
              <circle cx="13" cy="13" r="1.8" fill="var(--ink)" />
            </svg>
          </div>
          <div className="brand__word">The <em>Similarity</em></div>
        </div>
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
        {/* Reused verbatim from the old `.nav__right` — same classes,
            same handlers, same markup. The nav row no longer renders
            this block. */}
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
        {/* The "engine live" status pill was removed — it was decorative,
            not wired to a real health check, so leaving it on-screen was
            theater. The account/tools cluster above ends the bar now. */}
      </div>

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
          {/*
           * `?` hint — discoverability anchor for the shortcuts-help modal.
           * Deliberately placed just before the NY timestamp so it's the
           * last thing the user's eye lands on in the status bar. ink-3
           * (muted) + mono-font kbd keeps it quiet: power-user affordance
           * for those who scan the status bar, not a visual shout.
           */}
          <span className="statusbar__item">press <span className="kbd">?</span> for shortcuts</span>
          <span className="statusbar__item"><b>{nyClock}</b></span>
        </div>
      </footer>

      {/* ── Overlays ───────────────────────────────────────────── */}
      <TweaksPanel settings={settings} onSettings={updateSettings} visible={tweaksOpen} />
      <CommandPalette
        open={cmdOpen}
        onClose={() => setCmdOpen(false)}
        onNav={onCmdNav}
        onOpenHelp={() => { setCmdOpen(false); setHelpOpen(true); }}
      />
      <ShortcutsHelp
        open={helpOpen}
        onClose={() => setHelpOpen(false)}
        showPreviewChords={SHOW_PREVIEW}
      />
    </div>
  );
}
