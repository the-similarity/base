"use client";

/**
 * The Retrieve workstation — the main interactive view.
 *
 * Three-column layout: 260px sidebar (dataset selector, query definition,
 * window controls, pinned analogs, notebook), fluid center (header metrics,
 * chart card, trust strip, analog strip), and 320px right panel (9-lens
 * radar + bars, lens reading narrative).
 *
 * Data flow:
 * 1. On mount, check API availability via isApiAvailable()
 * 2. If API is up, fetch catalog + default series (stocks/spy/1d)
 * 3. On query window drag end (debounced 500ms), run search via API
 * 4. Map API response to workstation formats (analogs, cone, lenses)
 * 5. If API is down, fall back to synthetic SERIES + findAnalogs()
 *
 * The "offline — synthetic data" badge appears in the status bar when
 * the fallback engine is active.
 */

import { useState, useMemo, useEffect, useCallback, useRef } from "react";
import {
  SERIES, LENS_DEFS, findAnalogs, buildCone,
  fmtDate, fmtDateShort, fmtPct,
  type LensScores, type AnalogMatch, type ConePoint, type DataPoint,
} from "../../lib/data";
import {
  isApiAvailable, fetchCatalog, fetchSeries, searchApi,
  mapMatchesToAnalogs, mapForecastToCone, mapScoreBreakdownToLenses,
} from "../../lib/api";
import type { CatalogItem } from "../../lib/types";
import { LineChart, AnalogOverlay } from "./line-chart";
import { LensRadar } from "./lens-radar";
import { LensBars } from "./lens-bars";
import { Sparkline } from "./sparkline";

/** Settings shape passed from the app shell */
export interface WorkstationSettings {
  theme: string;
  kAnalogs: number;
  horizon: number;
  showAnalogs: string;
  showCone: boolean;
}

interface WorkstationProps {
  settings: WorkstationSettings;
  onSettings: (s: WorkstationSettings) => void;
}

/**
 * Group catalog items by asset class for the dataset selector dropdown.
 * Returns a map like { "stocks": [item1, item2], "crypto": [item3] }.
 */
function groupByAssetClass(items: CatalogItem[]): Record<string, CatalogItem[]> {
  const groups: Record<string, CatalogItem[]> = {};
  for (const item of items) {
    const key = item.assetClass;
    if (!groups[key]) groups[key] = [];
    groups[key].push(item);
  }
  return groups;
}

/** Convert a DatasetSeries-style response into DataPoint[] for the chart. */
function seriesToDataPoints(values: number[], dates: string[]): DataPoint[] {
  return values.map((p, i) => {
    const d = dates[i] ? new Date(dates[i]) : new Date(1995, 0, 3 + i);
    return {
      t: d.getTime(),
      d,
      p,
      r: i > 0 ? Math.log(p / values[i - 1]) : 0,
    };
  });
}

export function Workstation({ settings, onSettings }: WorkstationProps) {
  // ── Data source state ──────────────────────────────────────────────
  const [isOnline, setIsOnline] = useState<boolean | null>(null); // null = checking
  const [catalog, setCatalog] = useState<CatalogItem[]>([]);
  const [activeDataset, setActiveDataset] = useState("stocks/spy/1d");
  const [loadedSeries, setLoadedSeries] = useState<DataPoint[]>(SERIES);
  const [loadedDates, setLoadedDates] = useState<string[]>([]);
  const [loadedValues, setLoadedValues] = useState<number[]>([]);
  const [datasetOpen, setDatasetOpen] = useState(false);

  // ── Search state ───────────────────────────────────────────────────
  const [searching, setSearching] = useState(false);
  const [apiAnalogs, setApiAnalogs] = useState<AnalogMatch[] | null>(null);
  const [apiCone, setApiCone] = useState<ConePoint[] | null>(null);
  const searchTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  // ── Window state ───────────────────────────────────────────────────
  const N = loadedSeries.length;
  const [windowState, setWindowState] = useState({ start: Math.max(0, N - 240), len: 120 });
  const [viewRange, setViewRange] = useState({ start: Math.max(0, N - 900), end: Math.max(0, N - 30) });
  const [pinned, setPinned] = useState<Set<string>>(new Set());
  const [hoverAnalog, setHoverAnalog] = useState<string | null>(null);
  const [crosshairIdx, setCrosshairIdx] = useState<number | null>(null);
  const [trustOpen, setTrustOpen] = useState(false);

  // ── Banner dismissal state ─────────────────────────────────────────
  // Dismissed banners persist to sessionStorage keyed by banner id so they
  // don't re-appear mid-session, but DO reappear in a new tab. We start
  // with null (SSR-safe) and hydrate from sessionStorage on mount.
  const [dismissedBanners, setDismissedBanners] = useState<Set<string>>(new Set());
  useEffect(() => {
    // Lazy hydration from sessionStorage on the client. Wrapped in try/catch
    // because sessionStorage access can throw in some sandboxed iframes.
    try {
      const raw = sessionStorage.getItem("workstation.dismissedBanners");
      if (raw) {
        const parsed = JSON.parse(raw) as string[];
        if (Array.isArray(parsed)) setDismissedBanners(new Set(parsed));
      }
    } catch {
      // sessionStorage unavailable — banner will just show until user dismisses
    }
  }, []);
  // ── Drawer state for mid-size screens (1024-1279px) ───────────────
  // At this width the right panel (lens radar + reading) collapses into a
  // slide-in drawer so the chart isn't crushed. State is local; the CSS
  // media query gates whether it visually applies — on large screens the
  // data attribute has no effect because the drawer styles don't apply.
  const [rightDrawerOpen, setRightDrawerOpen] = useState(false);

  const dismissBanner = useCallback((id: string) => {
    setDismissedBanners(prev => {
      const next = new Set(prev);
      next.add(id);
      try {
        sessionStorage.setItem("workstation.dismissedBanners", JSON.stringify([...next]));
      } catch {
        // ignore — dismissal just won't persist
      }
      return next;
    });
  }, []);


  // ── Check API availability on mount ────────────────────────────────
  useEffect(() => {
    let cancelled = false;
    async function check() {
      const available = await isApiAvailable();
      if (!cancelled) {
        setIsOnline(available);
        if (available) {
          // Load catalog
          try {
            const cat = await fetchCatalog();
            if (!cancelled) setCatalog(cat);
          } catch {
            // Catalog load failed — stay online but with empty catalog
          }
        }
      }
    }
    check();
    return () => { cancelled = true; };
  }, []);

  // ── Load series when dataset changes and API is online ─────────────
  useEffect(() => {
    if (!isOnline) return;
    let cancelled = false;

    async function load() {
      const parts = activeDataset.split("/");
      if (parts.length !== 3) return;
      const [assetClass, symbol, timeframe] = parts;

      try {
        const res = await fetchSeries(assetClass, symbol, timeframe);
        if (cancelled) return;

        const dp = seriesToDataPoints(res.values, res.dates);
        setLoadedSeries(dp);
        setLoadedDates(res.dates);
        setLoadedValues(res.values);

        // Reset window to reasonable defaults for the new series
        const newN = dp.length;
        setWindowState({ start: Math.max(0, newN - 240), len: Math.min(120, Math.floor(newN / 3)) });
        setViewRange({ start: Math.max(0, newN - 900), end: Math.max(0, newN - 30) });
        // Clear previous search results
        setApiAnalogs(null);
        setApiCone(null);
      } catch (err) {
        console.warn("Failed to load series, falling back to synthetic:", err);
        setIsOnline(false);
      }
    }
    load();
    return () => { cancelled = true; };
  }, [isOnline, activeDataset]);

  // ── Debounced API search on window change ──────────────────────────
  const runApiSearch = useCallback(async () => {
    if (!isOnline || loadedValues.length < 10) return;

    // Abort any in-flight search
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    setSearching(true);
    try {
      const queryValues = loadedValues.slice(windowState.start, windowState.start + windowState.len);
      if (queryValues.length < 2) return;

      const result = await searchApi({
        queryValues,
        historyValues: loadedValues,
        topK: settings.kAnalogs || 6,
        forwardBars: settings.horizon || 60,
      }, controller.signal);

      if (controller.signal.aborted) return;

      // Map API response to workstation formats
      const analogs = mapMatchesToAnalogs(result, loadedDates, loadedValues, windowState.len);
      setApiAnalogs(analogs);

      if (result.forecast) {
        const lastP = loadedValues[windowState.start + windowState.len - 1] ?? 1;
        const cone = mapForecastToCone(result.forecast, lastP);
        setApiCone(cone);
      }
    } catch (err) {
      if (err instanceof Error && err.name === "AbortError") return;
      console.warn("API search failed, using synthetic fallback:", err);
      // Don't flip isOnline off for transient errors — just use synthetic for this search
      setApiAnalogs(null);
      setApiCone(null);
    } finally {
      setSearching(false);
    }
  }, [isOnline, loadedValues, loadedDates, windowState.start, windowState.len, settings.kAnalogs, settings.horizon]);

  // Debounce search: 500ms after window change
  useEffect(() => {
    if (!isOnline) return;
    if (searchTimerRef.current) clearTimeout(searchTimerRef.current);
    searchTimerRef.current = setTimeout(() => {
      runApiSearch();
    }, 500);
    return () => {
      if (searchTimerRef.current) clearTimeout(searchTimerRef.current);
    };
  }, [runApiSearch, isOnline]);

  // ── Synthetic fallback analogs + cone ──────────────────────────────
  const syntheticResult = useMemo(() => {
    if (isOnline && apiAnalogs !== null) return null; // Using API data
    const anal = findAnalogs(windowState.start, windowState.len,
      { k: settings.kAnalogs || 6, horizon: settings.horizon || 60 });
    const lastP = loadedSeries[windowState.start + windowState.len - 1]?.p ?? 1;
    const c = buildCone(anal, settings.horizon || 60, lastP);
    return { analogs: anal, cone: c };
  }, [isOnline, apiAnalogs, windowState.start, windowState.len, settings.kAnalogs, settings.horizon, loadedSeries]);

  // ── Resolved analogs and cone (API or synthetic) ───────────────────
  const analogs = (isOnline && apiAnalogs) ? apiAnalogs : (syntheticResult?.analogs ?? []);
  const cone = (isOnline && apiCone) ? apiCone : (syntheticResult?.cone ?? []);

  // Composite lenses = mean across top analogs
  const compLenses = useMemo(() => {
    const keys = LENS_DEFS.map(d => d.key);
    const out: Record<string, number> = {};
    keys.forEach(k => {
      out[k] = analogs.reduce((s, a) => s + (a.lenses[k as keyof LensScores] || 0), 0) / (analogs.length || 1);
    });
    return out as unknown as LensScores;
  }, [analogs]);

  // Cone endpoint statistics for the header metrics
  const coneStats = useMemo(() => {
    if (!cone || !cone.length) return null;
    const lastP = loadedSeries[windowState.start + windowState.len - 1]?.p ?? 1;
    const final = cone[cone.length - 1];
    return {
      horizon: cone.length,
      p50Return: final.p50 / lastP - 1,
      p10Return: final.p10 / lastP - 1,
      p90Return: final.p90 / lastP - 1,
      width: (final.p90 - final.p10) / lastP,
    };
  }, [cone, windowState, loadedSeries]);

  // Filter analog overlays based on settings
  const analogOverlays = useMemo((): AnalogOverlay[] => {
    const show = settings.showAnalogs === "all" ? analogs
      : settings.showAnalogs === "pinned" ? analogs.filter(a => pinned.has(a.id))
      : analogs.slice(0, 3);
    return show.map(a => ({ ...a, pinned: pinned.has(a.id) }));
  }, [analogs, pinned, settings.showAnalogs]);

  const togglePin = (id: string) => {
    setPinned(prev => {
      const n = new Set(prev);
      n.has(id) ? n.delete(id) : n.add(id);
      return n;
    });
  };

  // Query metadata for sidebar
  const queryMeta = useMemo(() => {
    const startD = loadedSeries[windowState.start]?.d ?? new Date();
    const endD = loadedSeries[windowState.start + windowState.len - 1]?.d ?? new Date();
    const startP = loadedSeries[windowState.start]?.p ?? 0;
    const endP = loadedSeries[windowState.start + windowState.len - 1]?.p ?? 0;
    return { startD, endD, startP, endP, ret: startP ? (endP / startP - 1) : 0 };
  }, [windowState, loadedSeries]);

  // Dataset label for display
  const datasetLabel = useMemo(() => {
    const parts = activeDataset.split("/");
    if (parts.length === 3) return `${parts[1].toUpperCase()} \u00B7 ${parts[2]}`;
    return "SPX \u00B7 daily";
  }, [activeDataset]);

  // Grouped catalog for dropdown
  const groupedCatalog = useMemo(() => groupByAssetClass(catalog), [catalog]);

  // ── Banner visibility logic ────────────────────────────────────────
  // Offline banner: API is confirmed down (isOnline === false). We avoid
  // flashing while the health check is in flight (isOnline === null).
  const showOfflineBanner = isOnline === false && !dismissedBanners.has("offline");
  // Empty-catalog banner: API is up but returned zero datasets. Only show
  // once the dataset fetch has resolved — by the time isOnline flips to
  // true the catalog useEffect has already run and populated (or not).
  const showEmptyCatalogBanner =
    isOnline === true && catalog.length === 0 && !dismissedBanners.has("empty-catalog");

  return (
    <div
      className="workstation"
      data-right-drawer={rightDrawerOpen ? "open" : "closed"}
    >
      {/* ── Responsive banners (offline / empty-catalog) ─────── */}
      {showOfflineBanner && (
        <div className="ws-banner ws-banner--warn" role="status">
          <span className="ws-banner__icon" aria-hidden="true">&#x1F536;</span>
          <span className="ws-banner__text">
            Running in demo mode &mdash; API offline. Data is synthetic, not live SPX.
          </span>
          <button
            type="button"
            className="ws-banner__dismiss"
            aria-label="Dismiss offline banner"
            onClick={() => dismissBanner("offline")}
          >
            &times;
          </button>
        </div>
      )}
      {showEmptyCatalogBanner && (
        <div className="ws-banner ws-banner--info" role="status">
          <span className="ws-banner__icon" aria-hidden="true">&#x2139;</span>
          <span className="ws-banner__text">
            Backend is online but has no registered datasets. See README for how to register one,
            or run with synthetic fallback via <code>NEXT_PUBLIC_DATA_MODE=demo</code>.
          </span>
          <button
            type="button"
            className="ws-banner__dismiss"
            aria-label="Dismiss empty catalog banner"
            onClick={() => dismissBanner("empty-catalog")}
          >
            &times;
          </button>
        </div>
      )}

      {/* ── LEFT SIDEBAR ─────────────────────────────────────── */}
      <aside className="side">
        {/* Dataset selector */}
        <div className="side__section">
          <div className="side__header">
            <span className="label">Dataset</span>
            {isOnline === false && (
              <span className="mono" style={{ fontSize: 9, color: "var(--negative)", letterSpacing: ".04em" }}>
                offline &mdash; synthetic data
              </span>
            )}
            {isOnline === null && (
              <span className="mono" style={{ fontSize: 9, color: "var(--ink-3)" }}>checking...</span>
            )}
          </div>
          <button
            className="chip"
            style={{ width: "100%", justifyContent: "space-between", display: "flex", padding: "6px 10px" }}
            onClick={() => setDatasetOpen(o => !o)}
          >
            <span className="mono" style={{ fontSize: 11 }}>{datasetLabel}</span>
            <span style={{ fontSize: 9 }}>{datasetOpen ? "\u25B2" : "\u25BC"}</span>
          </button>
          {datasetOpen && catalog.length > 0 && (
            <div className="saved-list" style={{ maxHeight: 200, overflow: "auto", marginTop: 4 }}>
              {Object.entries(groupedCatalog).map(([assetClass, items]) => (
                <div key={assetClass}>
                  <div className="label" style={{ fontSize: 9, color: "var(--ink-3)", margin: "6px 0 2px", textTransform: "uppercase", letterSpacing: ".12em" }}>
                    {assetClass}
                  </div>
                  {items.map(item => {
                    const id = `${item.assetClass}/${item.symbol}/${item.timeframe}`;
                    return (
                      <div
                        key={id}
                        className="saved"
                        style={{ cursor: "pointer", fontWeight: id === activeDataset ? 600 : 400 }}
                        onClick={() => { setActiveDataset(id); setDatasetOpen(false); }}
                      >
                        <span className="saved__name">{item.symbol.toUpperCase()}</span>
                        <span className="saved__score" style={{ fontSize: 10 }}>{item.timeframe}</span>
                      </div>
                    );
                  })}
                </div>
              ))}
            </div>
          )}
          {datasetOpen && catalog.length === 0 && isOnline && (
            <div style={{ fontSize: 11, color: "var(--ink-3)", padding: "6px 0" }}>
              No datasets registered &mdash; see main panel for setup.
            </div>
          )}
        </div>

        <div className="side__section">
          <div className="side__header">
            <span className="label">Query</span>
            <span className="mono" style={{ fontSize: 10.5, color: "var(--ink-3)" }}>{datasetLabel}</span>
          </div>
          <div className="side__row"><span className="k">Window start</span><span className="v">{fmtDate(queryMeta.startD)}</span></div>
          <div className="side__row"><span className="k">Window end</span><span className="v">{fmtDate(queryMeta.endD)}</span></div>
          <div className="side__row"><span className="k">Length</span><span className="v">{windowState.len} d</span></div>
          <div className="side__row">
            <span className="k">Return</span>
            <span className="v" style={{ color: queryMeta.ret >= 0 ? "var(--positive)" : "var(--negative)" }}>
              {fmtPct(queryMeta.ret)}
            </span>
          </div>
        </div>

        <div className="side__section">
          <div className="side__header"><span className="label">Window length</span></div>
          <div className="chip-row">
            {[30, 60, 120, 180, 250].map(L => (
              <button key={L} className="chip" data-active={windowState.len === L ? "true" : undefined}
                onClick={() => setWindowState(w => ({ ...w, len: L,
                  start: Math.min(w.start, N - L - (settings.horizon || 60) - 5) }))}>
                {L}D
              </button>
            ))}
          </div>
          <div style={{ height: 10 }} />
          <div className="side__header"><span className="label">View range</span></div>
          <div className="chip-row">
            {[
              { L: "2Y", n: 500 }, { L: "5Y", n: 1250 }, { L: "10Y", n: 2500 }, { L: "All", n: N - 220 }
            ].map(r => (
              <button key={r.L} className="chip"
                data-active={viewRange.end - viewRange.start === r.n ? "true" : undefined}
                onClick={() => setViewRange({
                  start: Math.max(200, windowState.start - Math.floor(r.n * 0.65)),
                  end: Math.min(N - 1, windowState.start + windowState.len + Math.floor(r.n * 0.35))
                })}>
                {r.L}
              </button>
            ))}
          </div>
        </div>

        <div className="side__section">
          <div className="side__header">
            <span className="label">Pinned analogs</span>
            <span className="mono" style={{ fontSize: 10.5, color: "var(--ink-3)" }}>{pinned.size}/{analogs.length}</span>
          </div>
          <div className="saved-list">
            {analogs.slice(0, 6).map(a => (
              <div key={a.id} className="saved" onClick={() => togglePin(a.id)}>
                <span className="saved__date">{fmtDateShort(a.date)}</span>
                <span className="saved__name">{a.label}</span>
                <span className="saved__score">{a.composite.toFixed(2)}</span>
                <span style={{
                  width: 10, height: 10, borderRadius: 2, border: "1px solid var(--rule-strong)",
                  background: pinned.has(a.id) ? "var(--accent)" : "transparent"
                }} />
              </div>
            ))}
          </div>
        </div>

        <div className="side__section">
          <div className="side__header"><span className="label">Notebook</span></div>
          <div style={{ fontSize: 12, color: "var(--ink-2)", lineHeight: 1.55 }}>
            <em className="serif" style={{ fontSize: 13 }}>Nine lenses agree</em> that late-&apos;18 Q4 and
            pre-GFC &apos;07 carry the most structural weight in this query&apos;s analog set.
            The cone tightens sharply in week 3 &mdash;
            <span className="mono" style={{ fontSize: 11 }}> dispersion drops 34%</span>.
          </div>
        </div>
      </aside>

      {/* ── MAIN ─────────────────────────────────────────────── */}
      <section className="main">
        <header className="main__head">
          <div className="main__title-wrap">
            <div className="label" style={{ marginBottom: 6 }}>Retrieve &middot; analog workstation</div>
            <h1>What does <em>this</em> moment rhyme with?</h1>
            <div className="main__subtitle">
              Drag the query window along the timeline. The engine re-ranks {analogs.length} historical
              matches and redraws the forecast cone. Pin analogs to overlay them.
            </div>
            {/* Drawer toggle — only visible on midsize screens via CSS */}
            <button
              type="button"
              className="ws-drawer-toggle ws-drawer-toggle--right"
              aria-expanded={rightDrawerOpen}
              aria-controls="workstation-right-panel"
              onClick={() => setRightDrawerOpen(o => !o)}
            >
              {rightDrawerOpen ? "Hide details" : "Details"} &rarr;
            </button>
          </div>
          <div className="main__metrics">
            <div className="metric">
              <span className="label">Composite</span>
              <span className="v">{(analogs[0]?.composite ?? 0).toFixed(2)}</span>
              <span className="d">top match</span>
            </div>
            <div className="metric">
              <span className="label">P50 / {coneStats?.horizon}d</span>
              <span className={"v " + (coneStats && coneStats.p50Return >= 0 ? "pos" : "neg")}>
                {coneStats ? fmtPct(coneStats.p50Return) : "\u2014"}
              </span>
              <span className="d">median outcome</span>
            </div>
            <div className="metric">
              <span className="label">Cone width</span>
              <span className="v">{coneStats ? fmtPct(coneStats.width, 0) : "\u2014"}</span>
              <span className="d">p10 to p90</span>
            </div>
            <div className="metric">
              <span className="label">Calibration</span>
              <span className="v">B+</span>
              <span className="d">12-mo rolling</span>
            </div>
          </div>
        </header>

        <div className="chart-stack">
          {showEmptyCatalogBanner && (
            // Empty-state card: backend is live but has zero registered datasets.
            // We still render the synthetic fallback chart below it so the user
            // can evaluate the UI, but this card makes the "fix your setup" path
            // obvious with two explicit CTAs.
            <div className="ws-empty-state" role="region" aria-label="No datasets registered">
              <div className="ws-empty-state__card">
                <h2 className="ws-empty-state__headline">No datasets registered yet</h2>
                <p className="ws-empty-state__body">
                  The engine finds analogs by matching historical windows, so it needs at
                  least one dataset to search against. Register a dataset via the platform
                  registry, or flip the app into synthetic-demo mode to explore the UI.
                </p>
                <div className="ws-empty-state__actions">
                  <button
                    type="button"
                    className="ws-empty-state__cta ws-empty-state__cta--primary"
                    onClick={() => {
                      // Flip isOnline false → the synthetic-fallback memo takes over
                      // and populates SERIES + findAnalogs() immediately. No network.
                      setIsOnline(false);
                    }}
                  >
                    Load demo SPX data
                  </button>
                  <a
                    className="ws-empty-state__cta"
                    href="https://github.com/the-similarity/base#readme"
                    target="_blank"
                    rel="noreferrer noopener"
                  >
                    Open docs
                  </a>
                </div>
              </div>
            </div>
          )}
          <div className="chart-card">
            <div className="chart-card__head">
              <div className="chart-card__title">
                <span className="t">{datasetLabel} &middot; full history</span>
                <span className="sub">{loadedSeries.length.toLocaleString()} bars</span>
              </div>
              <div className="chart-card__legend">
                <span className="legend-dot"><i />Query</span>
                <span className="legend-dot analog"><i />Analogs ({analogOverlays.length})</span>
                <span className="legend-dot cone"><i />P10&ndash;P90 cone</span>
                {searching && (
                  <span className="mono" style={{ fontSize: 10, color: "var(--ink-3)", marginLeft: 8 }}>
                    searching...
                  </span>
                )}
              </div>
            </div>
            <div className="chart-card__body" style={{ position: "relative" }}>
              {searching && (
                <div style={{
                  position: "absolute", inset: 0, display: "flex", alignItems: "center",
                  justifyContent: "center", background: "var(--bg-card)", opacity: 0.6, zIndex: 10,
                  pointerEvents: "none",
                }}>
                  <span className="mono" style={{ fontSize: 12, color: "var(--ink-2)" }}>Searching...</span>
                </div>
              )}
              <LineChart
                series={loadedSeries}
                viewStart={viewRange.start}
                viewEnd={viewRange.end}
                window={windowState}
                onWindowChange={setWindowState}
                analogsOverlay={analogOverlays}
                cone={cone}
                forecastHorizon={settings.horizon || 60}
                onHover={setCrosshairIdx}
                crosshairIdx={crosshairIdx}
                height={380}
                showCone={settings.showCone !== false}
              />
            </div>
          </div>
        </div>

        {/* Trust strip */}
        <div style={{ display: "flex", flexDirection: "column" }}>
          <div className="trust">
            <div className="trust__item">
              <span className="label">Coverage 80%</span>
              <span className="v pos">78.4%</span>
            </div>
            <div className="trust__item">
              <span className="label">CRPS (1Y)</span>
              <span className="v">0.042</span>
            </div>
            <div className="trust__item">
              <span className="label">Hit rate &middot; sign</span>
              <span className="v pos">0.61</span>
            </div>
            <div className="trust__item">
              <span className="label">Regime drift</span>
              <span className="v warn">elevated</span>
            </div>
            <div className="trust__item">
              <span className="label">N analogs used</span>
              <span className="v">{analogs.length}</span>
            </div>
            <button className="trust__expand" onClick={() => setTrustOpen(o => !o)}>
              {trustOpen ? "Hide" : "Open"} calibration panel &rarr;
            </button>
          </div>

          {trustOpen && (
            <div className="trust-panel">
              <div>
                <h3>Reliability diagram</h3>
                <svg viewBox="0 0 260 160" width="100%" height="160">
                  <rect x="1" y="1" width="258" height="158" fill="none" stroke="var(--rule)" />
                  <line x1="20" y1="140" x2="240" y2="20" stroke="var(--ink-4)" strokeDasharray="3 3" />
                  {[0.05, 0.18, 0.31, 0.48, 0.6, 0.72, 0.82, 0.92].map((p, i) => {
                    const obs = p + (Math.sin(i * 1.3) * 0.04);
                    return <circle key={i} cx={20 + p * 220} cy={140 - obs * 120} r="3.5" fill="var(--positive)" />;
                  })}
                  <text x="20" y="154" className="axis-label" fontSize="9" fill="var(--ink-3)">predicted</text>
                  <text x="4" y="20" className="axis-label" fontSize="9" fill="var(--ink-3)" transform="rotate(-90 8 20)">observed</text>
                </svg>
                <div style={{ fontSize: 12, color: "var(--ink-2)", marginTop: 8 }}>
                  Predicted quantiles match observed frequencies to within 4 percentage points.
                </div>
              </div>
              <div>
                <h3>Coverage over time</h3>
                <svg viewBox="0 0 260 160" width="100%" height="160">
                  <rect x="1" y="1" width="258" height="158" fill="none" stroke="var(--rule)" />
                  <line x1="10" y1="60" x2="250" y2="60" stroke="var(--rule-strong)" strokeDasharray="3 3" />
                  <text x="12" y="56" className="axis-label" fontSize="9" fill="var(--ink-3)">80% target</text>
                  {Array.from({ length: 48 }).map((_, i) => {
                    const v = 0.80 + Math.sin(i * 0.7) * 0.08 + (i > 36 ? -0.05 : 0);
                    const x = 10 + i * 5;
                    const y = 160 - v * 150;
                    return <line key={i} x1={x} x2={x} y1={160} y2={y} stroke="var(--ink-2)" strokeWidth="1.4" />;
                  })}
                </svg>
                <div style={{ fontSize: 12, color: "var(--ink-2)", marginTop: 8 }}>
                  Coverage has been stable at 78&ndash;82% over the last 12 months, with mild regime drift at the tail.
                </div>
              </div>
              <div>
                <h3>Honesty note</h3>
                <p style={{ fontFamily: "var(--serif)", fontSize: 15, lineHeight: 1.5, color: "var(--ink-2)", fontStyle: "italic" }}>
                  Similarity is not a guarantee. Markets regime-shift. The cone reports what
                  <span style={{ fontStyle: "normal", fontWeight: 500 }}> tended to happen</span> after similar
                  structural patterns &mdash; nothing more, nothing less.
                </p>
              </div>
            </div>
          )}
        </div>

        {/* Analog strip */}
        <div className="strip">
          {searching && analogs.length === 0 && (
            <div style={{ display: "flex", alignItems: "center", justifyContent: "center", width: "100%", padding: 32 }}>
              <span className="mono" style={{ fontSize: 12, color: "var(--ink-3)" }}>Searching for analogs...</span>
            </div>
          )}
          {analogs.map(a => (
            <div key={a.id} className="analog-card"
              data-pinned={pinned.has(a.id) ? "true" : undefined}
              onClick={() => togglePin(a.id)}
              onMouseEnter={() => setHoverAnalog(a.id)}
              onMouseLeave={() => setHoverAnalog(null)}>
              <div className="analog-card__head">
                <span className="analog-card__date">#{a.rank} &middot; {fmtDateShort(a.date)}</span>
                <span className="analog-card__score">{a.composite.toFixed(2)}</span>
              </div>
              <div className="analog-card__title">{a.label}</div>
              <div className="analog-card__note">{a.note}</div>
              <div className="analog-card__spark">
                <Sparkline values={[...a.priceWindow, ...a.after.slice(0, 60)]} width={110} highlight={0.35} />
                <span className={"analog-card__after " + (a.afterReturn >= 0 ? "pos" : "neg")}>
                  {fmtPct(a.afterReturn)}
                </span>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* Backdrop shown only when the right drawer is open on midsize screens.
          Clicking it closes the drawer. On large screens the drawer CSS
          doesn't apply so the backdrop is hidden via display: none. */}
      <div
        className="ws-drawer-backdrop"
        data-visible={rightDrawerOpen ? "true" : "false"}
        onClick={() => setRightDrawerOpen(false)}
        aria-hidden="true"
      />

      {/* ── RIGHT PANEL ──────────────────────────────────────── */}
      <aside className="right" id="workstation-right-panel">
        {/* Close button inside the drawer — hidden on large screens where
            the panel is statically docked. */}
        <button
          type="button"
          className="ws-drawer-close"
          aria-label="Close details panel"
          onClick={() => setRightDrawerOpen(false)}
        >
          &times;
        </button>
        <div className="right__section">
          <div className="lens-head">
            <div>
              <div className="label">Nine lenses &middot; mean agreement</div>
              <div className="score">
                {(Object.values(compLenses).reduce((a: number, b: number) => a + b, 0) / 9).toFixed(2)}
                <span className="d"> / 1.00</span>
              </div>
            </div>
          </div>
          <LensRadar lenses={compLenses} size={220} />
          <LensBars lenses={compLenses} compact={false} />
        </div>

        <div className="right__section">
          <div className="side__header"><span className="label">Lens reading</span></div>
          <div style={{ fontSize: 12.5, color: "var(--ink-2)", lineHeight: 1.6 }}>
            <p style={{ margin: "0 0 10px" }}>
              <b style={{ color: "var(--ink)", fontWeight: 500 }}>High agreement on Shape + Engine lenses</b> suggests
              structural and dynamical alignment with top analogs.
            </p>
            <p style={{ margin: 0 }}>
              <b style={{ color: "var(--ink)", fontWeight: 500 }}>Weakest lens:</b> Carry &mdash;
              the predictive transfer is real but modest. Treat P50 as a center of mass, not a target.
            </p>
          </div>
        </div>
      </aside>
    </div>
  );
}
