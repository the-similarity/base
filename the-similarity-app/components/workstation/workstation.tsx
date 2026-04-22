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
  SERIES, LENS_DEFS, findAnalogs, buildCone, computeCalibrationMetrics,
  fmtDate, fmtDateShort, fmtPct,
  type LensScores, type AnalogMatch, type ConePoint, type DataPoint,
  type CalibrationResult,
} from "../../lib/data";
import {
  isApiAvailable, fetchCatalog, fetchSeries, searchApi,
  mapMatchesToAnalogs, mapForecastToCone, mapScoreBreakdownToLenses,
} from "../../lib/api";
import type { CatalogItem } from "../../lib/types";
import {
  parseUrlState,
  serializeUrlState,
  type WorkstationUrlState,
} from "../../lib/url-state";
import { LineChart, AnalogOverlay } from "./line-chart";
import { LineChartLW } from "./line-chart-lw";
import { LensRadar } from "./lens-radar";
import { LensBars } from "./lens-bars";
import { Sparkline } from "./sparkline";
import { AnalogDetailDrawer } from "./analog-detail-drawer";

/** Settings shape passed from the app shell */
export interface WorkstationSettings {
  theme: string;
  kAnalogs: number;
  horizon: number;
  showAnalogs: string;
  showCone: boolean;
  /**
   * Which chart engine renders the main price/cone/analog view.
   * - "fast" → SVG LineChart, supports draggable query window (default).
   * - "pro"  → lightweight-charts LineChartLW, read-only window,
   *   crosshair + pan/zoom via the native canvas engine.
   * Optional so older persisted settings decode cleanly; read sites must
   * default via `(settings.chartMode ?? "fast")`.
   */
  chartMode?: "fast" | "pro";
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

/**
 * Filter catalog items by a free-form search query.
 *
 * The query matches against the symbol (primary) and the asset class
 * (secondary) so users can narrow either axis: typing "btc" hits BTCUSD
 * regardless of asset class, typing "crypto" collapses the list to the
 * crypto group. Empty / whitespace queries pass everything through
 * unchanged.
 *
 * Intentionally case-insensitive: the UI shows symbols uppercase but
 * the user's expectation is that typing matches regardless of case.
 */
export function filterCatalog(items: CatalogItem[], query: string): CatalogItem[] {
  const q = query.trim().toLowerCase();
  if (!q) return items;
  return items.filter(item =>
    item.symbol.toLowerCase().includes(q) ||
    item.assetClass.toLowerCase().includes(q)
  );
}

/**
 * Format a bar count with a thousands separator.
 *
 * Kept as a separate helper so the dropdown item card renders the same
 * "7,500 bars" string everywhere (selected summary, per-item card,
 * offline note) without each call site re-implementing locale rules.
 */
export function formatBarCount(n: number): string {
  if (!n || n <= 0) return "";
  return `${n.toLocaleString("en-US")} bars`;
}

/**
 * Parse an ISO timestamp into a Date, returning null on failure.
 *
 * Central place to handle the "manifest may be missing or malformed"
 * case. Callers in the dropdown render "—" when the result is null
 * rather than letting `new Date(null)` silently yield a valid epoch or
 * `new Date("garbage")` produce an Invalid Date that formats as "NaN".
 */
export function parseIsoOrNull(iso: string | null | undefined): Date | null {
  if (!iso) return null;
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? null : d;
}

/**
 * Detect stale data. "Stale" means the last-updated timestamp is older
 * than `thresholdHours` and the dataset frequency is daily or faster
 * (i.e. a 1m/5m/1h/1d dataset). Weekly / monthly datasets are never
 * flagged because they're *expected* to lag multiple days.
 *
 * Returns false when we can't tell (missing timestamp, unrecognised
 * frequency) — the UI prefers silence over noisy false positives.
 */
export function isStale(
  item: CatalogItem,
  now: Date,
  thresholdHours: number = 48,
): boolean {
  const updated = parseIsoOrNull(item.lastUpdatedAt);
  if (!updated) return false;
  // Anything coarser than 1 day is expected to have multi-day gaps.
  // The bare timeframe code is a fine proxy: "1w" / "1M" etc. all skip
  // the staleness check.
  const tf = item.timeframe.toLowerCase();
  const isIntradayOrDaily =
    tf.endsWith("m") || tf.endsWith("h") || tf === "1d";
  if (!isIntradayOrDaily) return false;
  const deltaHours = (now.getTime() - updated.getTime()) / 3_600_000;
  return deltaHours > thresholdHours;
}

/**
 * Format a short ISO date as "YYYY-MM-DD" (or "—" if null).
 *
 * The dropdown item cards render a compact `startDate → endDate` range
 * line; using ISO-style dates keeps alignment consistent regardless of
 * the user's locale and avoids the "Apr 22, 2026" vs "22 Apr 2026"
 * confusion that locale-dependent formatting would introduce.
 */
export function formatShortDate(iso: string | null | undefined): string {
  const d = parseIsoOrNull(iso);
  if (!d) return "\u2014";
  return d.toISOString().slice(0, 10);
}

/**
 * Format an ISO timestamp as "MMM DD, YYYY · HH:MM" in UTC.
 *
 * Used for the "Updated: …" sub-line on each dropdown item card. We
 * display in UTC to match the backend's source-of-truth timezone; the
 * alternative (convert to the user's locale) would make the displayed
 * value differ from what shows up in server logs, complicating support.
 */
export function formatUpdatedAt(iso: string | null | undefined): string {
  const d = parseIsoOrNull(iso);
  if (!d) return "\u2014";
  const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  const m = months[d.getUTCMonth()];
  const day = d.getUTCDate();
  const year = d.getUTCFullYear();
  const hh = String(d.getUTCHours()).padStart(2, "0");
  const mm = String(d.getUTCMinutes()).padStart(2, "0");
  return `${m} ${day}, ${year} \u00B7 ${hh}:${mm}`;
}

/**
 * The static synthetic-fallback entry used when the API is unreachable.
 *
 * Exported so tests can pin the exact wire shape the dropdown renders
 * in offline / demo mode. Kept as a frozen-value factory (not a module
 * constant) so each call returns a fresh object the caller can mutate
 * without polluting the canonical reference.
 */
export function offlineSyntheticCatalog(): CatalogItem[] {
  return [
    {
      assetClass: "stocks",
      symbol: "spy",
      timeframe: "1d",
      source: "Synthetic \u00B7 seeded PRNG",
      rowCount: 0,
      startTimestamp: null,
      endTimestamp: null,
      lastUpdatedAt: null,
      frequency: "1 day",
    },
  ];
}

/**
 * Format a past Date as a compact relative "last run" label.
 *
 * Buckets:
 *   < 45s   -> "just now"
 *   < 60m   -> "Nm ago"
 *   < 24h   -> "Nh ago"
 *   otherwise -> "Nd ago"
 *
 * Intentionally coarse: the UI refreshes every 30s (see the tick below),
 * so sub-minute precision would thrash without telling the user anything
 * useful. "just now" covers the freshly-run state; minute-resolution is
 * the right granularity for an analytical workstation.
 */
export function formatRelativeTime(when: Date, now: Date): string {
  const deltaMs = Math.max(0, now.getTime() - when.getTime());
  const deltaSec = Math.floor(deltaMs / 1000);
  if (deltaSec < 45) return "just now";
  const deltaMin = Math.floor(deltaSec / 60);
  if (deltaMin < 60) return `${deltaMin}m ago`;
  const deltaHr = Math.floor(deltaMin / 60);
  if (deltaHr < 24) return `${deltaHr}h ago`;
  const deltaDay = Math.floor(deltaHr / 24);
  return `${deltaDay}d ago`;
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

/**
 * Read URL state at mount time.
 *
 * Safe to call inside useState lazy initializers — guards against SSR by
 * returning an empty object when `window` is unavailable. The returned
 * object is a snapshot: subsequent URL changes (share-link navigations,
 * forward/back) are NOT tracked here — we write via replaceState and
 * don't treat the URL as a reactive source.
 */
function readInitialUrlState(): WorkstationUrlState {
  if (typeof window === "undefined") return {};
  try {
    return parseUrlState(window.location.search);
  } catch {
    // parseUrlState is defensive and shouldn't throw, but defense-in-depth
    // — a malformed URL should never crash the workstation.
    return {};
  }
}

export function Workstation({ settings, onSettings }: WorkstationProps) {
  /*
   * URL-state snapshot captured at mount.
   *
   * We read the URL exactly ONCE. The lazy-initializer pattern makes this
   * safe during React 19 strict-mode double-renders: `readInitialUrlState`
   * runs only on the first mount. The snapshot is stored in a ref so
   * downstream effects can consult the ORIGINAL share-link intent without
   * being confused by our own `history.replaceState` writes.
   *
   * Priority contract: URL state > localStorage > defaults. Every call
   * site that merges state must check `urlStateRef.current` FIRST and
   * fall through to localStorage/defaults only when the URL field is
   * undefined.
   */
  const urlStateRef = useRef<WorkstationUrlState>(readInitialUrlState());

  // ── Data source state ──────────────────────────────────────────────
  const [isOnline, setIsOnline] = useState<boolean | null>(null); // null = checking
  const [catalog, setCatalog] = useState<CatalogItem[]>([]);
  /*
   * Active dataset — URL override takes precedence over the default.
   *
   * If the share-link carries `?ds=...`, we initialize with it so the
   * catalog-load effect fires against the right dataset immediately,
   * sparing the user a flash-of-default-spy before the override applies.
   * When the URL dataset doesn't exist in the catalog (checked after
   * /catalog resolves), we fall back silently — see the catalog-ready
   * effect below.
   */
  const [activeDataset, setActiveDataset] = useState(
    () => urlStateRef.current.dataset ?? "stocks/spy/1d",
  );
  const [loadedSeries, setLoadedSeries] = useState<DataPoint[]>(SERIES);
  const [loadedDates, setLoadedDates] = useState<string[]>([]);
  const [loadedValues, setLoadedValues] = useState<number[]>([]);
  const [datasetOpen, setDatasetOpen] = useState(false);
  // Free-form filter query for the dataset dropdown search input.
  // Scoped to the dropdown panel — closing the dropdown resets it so
  // re-opening always starts fresh.
  const [datasetSearch, setDatasetSearch] = useState("");

  // ── Search state ───────────────────────────────────────────────────
  const [searching, setSearching] = useState(false);
  const [apiAnalogs, setApiAnalogs] = useState<AnalogMatch[] | null>(null);
  const [apiCone, setApiCone] = useState<ConePoint[] | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  /*
   * Manual-search state (replaces the old "auto-search on every drag" loop).
   *
   * `lastSearch` is a snapshot of the input parameters that produced the
   * currently-displayed analogs + cone. It lets us detect when the user
   * has moved the window / changed top-K / changed the horizon without
   * re-running — the Search button then visually pulses ("dirty") to
   * prompt the user to re-run.
   *
   * `searchedAnalogs` and `searchedCone` persist the LAST successfully
   * computed results. Unlike the old `useMemo`-based synthetic pipeline
   * which recomputed on every windowState change, these are only written
   * inside `runSearch()` — so dragging the query window does NOT mutate
   * them.
   *
   * `lastRunAt` is the wall-clock Date when the current results were
   * produced; the UI renders it as a relative "2m ago" timestamp.
   */
  const [lastSearch, setLastSearch] = useState<{
    start: number;
    len: number;
    k: number;
    horizon: number;
  } | null>(null);
  const [searchedAnalogs, setSearchedAnalogs] = useState<AnalogMatch[] | null>(null);
  const [searchedCone, setSearchedCone] = useState<ConePoint[] | null>(null);
  const [lastRunAt, setLastRunAt] = useState<Date | null>(null);

  /*
   * Ticking "now" for the relative last-run label.
   *
   * We can't compute "2m ago" once and cache it — the label has to update
   * as time passes. A 30s tick is the right cadence: the label is
   * minute-resolution (see formatRelativeTime), so ticking more often
   * just wastes re-renders, but ticking less often means "just now" can
   * linger for several minutes after a search which feels stale.
   *
   * The interval is installed whenever there's a relative timestamp
   * being rendered somewhere — currently that's either the Search
   * button's "last run" label OR the dataset freshness line under the
   * sidebar header. We always keep it running because the freshness
   * line appears as soon as /catalog resolves with metadata, which is
   * typically within a second of mount. A 30s interval is cheap
   * compared to the full Workstation re-render cost.
   */
  const [nowTick, setNowTick] = useState<Date>(() => new Date());
  useEffect(() => {
    const id = window.setInterval(() => setNowTick(new Date()), 30_000);
    return () => window.clearInterval(id);
  }, []);

  // ── Window state ───────────────────────────────────────────────────
  const N = loadedSeries.length;
  /*
   * Window / view state — initialized from URL when present, falling back
   * to sensible defaults over the synthetic SERIES. When a real series is
   * loaded asynchronously (see the catalog-ready effect), the window is
   * reset to fit unless URL overrides are present; the post-series-load
   * effect below re-applies URL overrides so a share-link dataset + window
   * restores correctly even with async series loading.
   *
   * Note: we ONLY read urlStateRef for initial values here. All subsequent
   * window changes come from user interaction (drag, chip-click, "use as
   * query"). The URL is a write-target for those changes (see the
   * debounced URL-writer effect below), not a reactive input.
   */
  const [windowState, setWindowState] = useState(() => {
    const u = urlStateRef.current;
    const qs = u.queryStart;
    const ql = u.queryLen;
    if (qs !== undefined && ql !== undefined) {
      return { start: qs, len: ql };
    }
    return { start: Math.max(0, N - 240), len: 120 };
  });
  const [viewRange, setViewRange] = useState(() => {
    const u = urlStateRef.current;
    if (u.viewStart !== undefined && u.viewEnd !== undefined) {
      return { start: u.viewStart, end: u.viewEnd };
    }
    return { start: Math.max(0, N - 900), end: Math.max(0, N - 30) };
  });
  /*
   * Pinned analog ids — initialized from URL when present, otherwise
   * empty. The URL takes precedence over localStorage here so a link like
   * `?p=abc,def` always shows those two even if the recipient has a
   * different saved set. localStorage rehydrates after the first search
   * completes (see pinKey-based load effect below); to keep URL-as-truth
   * during that window, we ALSO write `urlStateRef.current.pinned` into
   * the hydrate path so it wins when both are present.
   */
  const [pinned, setPinned] = useState<Set<string>>(() => {
    const u = urlStateRef.current;
    if (u.pinned && u.pinned.length > 0) return new Set(u.pinned);
    return new Set();
  });
  /*
   * Hydration flag for the pin-persistence effects.
   *
   * The pair of effects below (load-from-storage, save-to-storage) runs
   * once per query identity. Without a flag, the SAVE effect would fire
   * on the initial mount with `pinned = empty Set`, clobbering any
   * pin set that was about to be LOADED for the same key. The flag
   * gates the save until at least one load has completed for the
   * current key, so the first write to a fresh key is always a
   * user-initiated togglePin, never an accidental mount-time empty.
   *
   * Reset semantics: whenever the query identity (dataset/start/len)
   * changes, pinHydrated flips back to false, the load effect runs,
   * then subsequent toggles persist to the new key. This keeps the
   * per-query isolation guarantee from the task spec.
   */
  const [pinHydrated, setPinHydrated] = useState(false);
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
  // ── Drawer state for mid-size screens ──────────────────────────────
  // At 1024-1279px the right panel (lens radar + reading) collapses into a
  // slide-in drawer so the chart isn't crushed. At 768-1023px the left
  // sidebar (dataset + query controls) ALSO collapses into a left-side
  // slide-in drawer so the chart gets the full width. State is local;
  // media queries gate whether the drawer styles apply — on large screens
  // the data attributes have no effect because the overlay CSS doesn't.
  const [rightDrawerOpen, setRightDrawerOpen] = useState(false);
  const [leftDrawerOpen, setLeftDrawerOpen] = useState(false);

  /*
   * Analog detail drawer state.
   *
   * `detailAnalogId` is the id of the analog the user clicked into for
   * inspection. When non-null the AnalogDetailDrawer slides in from the
   * right with that analog's context / lens breakdown / sparklines. When
   * null, the drawer renders closed (mounted but translated off-screen)
   * so the slide-out transition plays cleanly.
   *
   * The drawer is a SEPARATE affordance from pinning: clicking the card
   * body opens the drawer, while clicking a dedicated pin icon in the
   * card corner toggles pin. This lets a user inspect an analog without
   * committing to pin it.
   *
   * Null-safety: `detailAnalog` resolves to null whenever the id is null
   * OR the id no longer matches any current analog (e.g. search re-ran
   * with different results). Drawer is defensive about that case.
   */
  const [detailAnalogId, setDetailAnalogId] = useState<string | null>(null);
  const [useAsQueryBanner, setUseAsQueryBanner] = useState<string | null>(null);

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

  /*
   * Load series when dataset changes and API is online.
   *
   * URL-state interaction: on the FIRST successful load, URL-provided
   * window/view overrides take precedence over the "reset-to-defaults"
   * behavior. This restores share-links that pin (dataset, queryStart,
   * queryLen, viewStart, viewEnd) — otherwise the default reset would
   * clobber the override milliseconds after mount.
   *
   * We gate the override to the first load via `urlHydratedRef` so
   * subsequent dataset switches (user clicking a different dataset in
   * the dropdown) still reset cleanly — the URL intent is a one-shot
   * applied at mount, not a permanent lock.
   */
  const urlHydratedRef = useRef(false);
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

        const newN = dp.length;
        const u = urlStateRef.current;
        const firstHydration = !urlHydratedRef.current;

        /*
         * Window reset: honor URL overrides on the first hydration only.
         * Clamp the URL values to the actual series length so a link with
         * `qs=5000&ql=200` against a 300-bar series doesn't index out of
         * range. Clamping yields a best-effort restore instead of a
         * crash — the link still "works" on smaller datasets.
         */
        if (firstHydration && u.queryStart !== undefined && u.queryLen !== undefined) {
          const clampedStart = Math.max(0, Math.min(u.queryStart, newN - 2));
          const maxLen = Math.max(2, newN - clampedStart - 1);
          const clampedLen = Math.max(2, Math.min(u.queryLen, maxLen));
          setWindowState({ start: clampedStart, len: clampedLen });
        } else {
          setWindowState({ start: Math.max(0, newN - 240), len: Math.min(120, Math.floor(newN / 3)) });
        }

        if (firstHydration && u.viewStart !== undefined && u.viewEnd !== undefined) {
          const clampedVs = Math.max(0, Math.min(u.viewStart, newN - 2));
          const clampedVe = Math.max(clampedVs + 1, Math.min(u.viewEnd, newN - 1));
          setViewRange({ start: clampedVs, end: clampedVe });
        } else {
          setViewRange({ start: Math.max(0, newN - 900), end: Math.max(0, newN - 30) });
        }

        urlHydratedRef.current = true;
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

  /*
   * Unified manual-search entry point.
   *
   * Invariants:
   *   - Takes a SNAPSHOT of the current inputs (start/len/k/horizon) before
   *     any async work starts. This is what guarantees that dragging the
   *     window mid-flight can't corrupt the resolved result: the snapshot
   *     locks in the "what we searched for" tuple.
   *   - Writes ALL result state (searchedAnalogs, searchedCone, lastSearch,
   *     lastRunAt) atomically on success. On failure it doesn't mutate
   *     result state — the previous search stays displayed.
   *   - Honors the abort controller so a second runSearch() call cancels
   *     the first in-flight request instead of racing.
   *
   * Control flow:
   *   1. If online + series has enough data → try API.
   *   2. If API fails for any reason (including transient errors) OR we're
   *      offline → fall back to the synthetic engine.
   *   3. Either way, write results + snapshot + lastRunAt.
   *
   * This function is stable across renders via useCallback so the
   * keyboard-shortcut effect and the Search button share identical call
   * semantics.
   */
  const runSearch = useCallback(async () => {
    if (loadedValues.length < 10 && loadedSeries.length < 10) return;

    // Snapshot inputs before the async boundary. These values are frozen
    // for the remainder of this search — even if the user drags the
    // window immediately afterwards, this search will write results that
    // describe this exact snapshot.
    const snapshot = {
      start: windowState.start,
      len: windowState.len,
      k: settings.kAnalogs || 6,
      horizon: settings.horizon || 60,
    };

    // Cancel any in-flight search; the new one supersedes it.
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    setSearching(true);

    // Try API path first when online and we have enough real data.
    if (isOnline && loadedValues.length >= 10) {
      try {
        const queryValues = loadedValues.slice(snapshot.start, snapshot.start + snapshot.len);
        if (queryValues.length >= 2) {
          const result = await searchApi({
            queryValues,
            historyValues: loadedValues,
            topK: snapshot.k,
            forwardBars: snapshot.horizon,
          }, controller.signal);

          if (controller.signal.aborted) {
            setSearching(false);
            return;
          }

          const analogs = mapMatchesToAnalogs(result, loadedDates, loadedValues, snapshot.len);
          let cone: ConePoint[] = [];
          if (result.forecast) {
            const lastP = loadedValues[snapshot.start + snapshot.len - 1] ?? 1;
            cone = mapForecastToCone(result.forecast, lastP);
          }

          // Commit all result state atomically.
          setApiAnalogs(analogs);
          setApiCone(cone);
          setSearchedAnalogs(analogs);
          setSearchedCone(cone);
          setLastSearch(snapshot);
          setLastRunAt(new Date());
          setSearching(false);
          return;
        }
      } catch (err) {
        if (err instanceof Error && err.name === "AbortError") {
          // Superseded by a newer search — the newer one will flip
          // setSearching back to false when it finishes.
          return;
        }
        console.warn("API search failed, using synthetic fallback:", err);
        // Fall through to synthetic path below.
      }
    }

    // Synthetic fallback path. Used when offline, when API fails, or when
    // we simply don't have enough loaded values to query the API with.
    try {
      const anal = findAnalogs(snapshot.start, snapshot.len, {
        k: snapshot.k,
        horizon: snapshot.horizon,
      });
      const lastP = loadedSeries[snapshot.start + snapshot.len - 1]?.p ?? 1;
      const c = buildCone(anal, snapshot.horizon, lastP);
      // Synthetic results live in searchedAnalogs/Cone; apiAnalogs/apiCone
      // are cleared so the resolve-order below (api over synthetic) doesn't
      // show a stale API result alongside a fresh synthetic one.
      setApiAnalogs(null);
      setApiCone(null);
      setSearchedAnalogs(anal);
      setSearchedCone(c);
      setLastSearch(snapshot);
      setLastRunAt(new Date());
    } finally {
      setSearching(false);
    }
  }, [isOnline, loadedValues, loadedDates, loadedSeries, windowState.start, windowState.len, settings.kAnalogs, settings.horizon]);

  /*
   * Live ref to the latest runSearch closure.
   *
   * The keyboard-shortcut effect below is attached once on mount (empty
   * deps) to mirror the style used in `app/page.tsx` for jump/theme
   * chords — that avoids tearing down and reinstalling listeners on
   * every render. But a stale closure would call the FIRST runSearch
   * forever with stale snapshot inputs; the ref solves that by always
   * pointing at the latest closure.
   */
  const runSearchRef = useRef(runSearch);
  useEffect(() => { runSearchRef.current = runSearch; }, [runSearch]);

  /*
   * Live ref to the current analog list, consumed by the 1..6 keyboard
   * shortcut inside the keydown effect. The effect is installed once
   * (empty deps) to avoid re-binding on every analog-set change; the ref
   * lets the handler read the latest list without a stale closure.
   *
   * Declared here (before the keyboard effect) so the ref identity is
   * stable across renders. The useEffect below rewrites the ref target
   * whenever analogs shifts — cheap, and it never triggers a re-render.
   */
  const analogsRef = useRef<AnalogMatch[]>([]);

  /*
   * Keyboard shortcut: `Enter` or `r` re-runs the search.
   *
   * Matches the style of the top-level shortcuts in `app/page.tsx`
   * (t = theme, Shift+T = tweaks, g+letter = jump). We skip the
   * shortcut when focus is in an editable element so typing "r" into
   * a future text input wouldn't hijack the keystroke.
   *
   * We also skip when any modifier is held so Cmd+R (browser reload)
   * and Cmd+Enter (future send-command shortcuts) keep working.
   */
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null;
      const tag = target?.tagName;
      // Don't hijack keystrokes inside editable elements.
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
      if (target && target.isContentEditable) return;
      // Skip if any modifier is pressed — leave those for the browser / OS.
      if (e.metaKey || e.ctrlKey || e.altKey) return;

      // Escape closes the analog detail drawer when open. We check first
      // so it wins over the page-level Escape handler (which closes the
      // help modal). setDetailAnalogId(null) is idempotent when already
      // null — guard here is a performance nicety, not a correctness one.
      if (e.key === "Escape") {
        // Peek via ref so this effect doesn't need to re-install on every
        // drawer open/close. We don't preventDefault because the page-
        // level Escape handler is also interested (e.g. to close help /
        // cmd palette) — both should cooperate, not clobber.
        setDetailAnalogId(prev => prev !== null ? null : prev);
      }
      if (e.key === "Enter" || e.key === "r" || e.key === "R") {
        // Don't preventDefault on plain "r" because of the existing `g r`
        // jump chord in the root page — but for the shortcut to actually
        // fire on standalone "r" we need to not conflict. The chord key
        // handler at the page level sets `lastG` only when `g` was just
        // pressed; a standalone `r` without a preceding `g` does nothing
        // there, so re-using it here is safe. We still call
        // preventDefault for `Enter` to avoid default button activation
        // on any focused element.
        if (e.key === "Enter") e.preventDefault();
        runSearchRef.current();
      }

      // 1..6 → open the drawer for analog #1..#6. We use rowKeys rather
      // than e.key to keep the mapping 1:1 with ranks; shifted variants
      // (!/@/#/$/%/^) are ignored so the user's shift-typed intent
      // doesn't surprise-open a drawer. Reads analogs via ref for the
      // same reason runSearchRef exists — analogs identity changes per
      // search but we don't want to reinstall the listener each time.
      if (/^[1-6]$/.test(e.key) && !e.shiftKey) {
        const rank = parseInt(e.key, 10);
        const list = analogsRef.current;
        const target = list[rank - 1];
        if (target) {
          e.preventDefault();
          setDetailAnalogId(target.id);
        }
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  /*
   * One-shot initial search on mount.
   *
   * Previously the component auto-fired an API search 500ms after every
   * window drag, which meant each drag = one network request and a
   * thrashing cone. The new model is: run exactly ONCE when the component
   * has enough data to search, then wait for user action (button click
   * or keyboard shortcut) for all subsequent searches.
   *
   * Gate conditions:
   *   - `isOnline !== null` → health check has resolved (so we know whether
   *     to hit the API or use synthetic).
   *   - `lastSearch === null` → we haven't run yet. This is the one-shot
   *     guard; once the first search completes, this effect stops firing.
   *   - When online: require loadedValues to be populated (series fetched).
   *     Offline: synthetic SERIES is always available so no data-gate.
   *
   * We deliberately DO NOT depend on windowState here — otherwise any
   * drag before the first successful search would re-trigger this loop.
   */
  useEffect(() => {
    if (isOnline === null) return; // Still probing.
    if (lastSearch !== null) return; // Already ran.
    if (isOnline && loadedValues.length < 10) return; // Wait for series.
    runSearch();
    // We intentionally exclude `runSearch` from deps: runSearch identity
    // changes every time windowState or settings change, which would
    // cause this one-shot effect to repeatedly fire until lastSearch is
    // set. The `lastSearch === null` guard above is the authoritative
    // one-shot check.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOnline, loadedValues.length, lastSearch]);

  /*
   * Per-query localStorage key for the pinned analog set.
   *
   * Different queries should have different pin sets — pinning "Q4 '18"
   * under a query centered on 2020 shouldn't bleed into a query centered
   * on 2015. The key identity is (dataset, windowStart, windowLen) of
   * the LAST successful search; we deliberately key off `lastSearch`
   * rather than `windowState` so dragging the window doesn't cause a
   * live pin-set swap mid-edit. The pin set belongs to the search that
   * produced the analogs, not to the window the user is about to search.
   *
   * When there's no lastSearch yet, we return null — the persistence
   * effects below bail in that case, so the initial one-shot search
   * always starts with an empty pin set.
   */
  const pinKey = useMemo(() => {
    if (!lastSearch) return null;
    return `ts-pinned:${activeDataset}:${lastSearch.start}:${lastSearch.len}`;
  }, [activeDataset, lastSearch]);

  /*
   * Load persisted pin set on key change.
   *
   * Runs on first mount after a search completes, and again whenever
   * the query identity (pinKey) changes — e.g. the user re-searches a
   * different window. We reset pinHydrated to false BEFORE loading so
   * the save effect can't race ahead and clobber what we're about to
   * write. After a successful load (or an explicit "no data" resolution)
   * pinHydrated flips to true and the save effect begins tracking
   * user-initiated toggles.
   *
   * sessionStorage-style fault tolerance: localStorage access can throw
   * in some sandboxed iframes or private modes. We swallow errors and
   * let the in-memory Set take over — persistence is best-effort, not
   * load-bearing for correctness.
   */
  useEffect(() => {
    if (!pinKey) return;
    // Block any save until we've finished loading this key.
    setPinHydrated(false);
    try {
      const raw = localStorage.getItem(pinKey);
      if (raw) {
        const parsed = JSON.parse(raw) as string[];
        if (Array.isArray(parsed)) {
          setPinned(new Set(parsed));
        } else {
          setPinned(new Set());
        }
      } else {
        // No entry for this query — start with an empty set. Do NOT
        // preserve the previous query's pins; that would violate the
        // "per-query isolation" contract.
        setPinned(new Set());
      }
    } catch {
      // localStorage unavailable — carry forward with an empty set.
      setPinned(new Set());
    } finally {
      setPinHydrated(true);
    }
  }, [pinKey]);

  /*
   * Persist pin set on every change, once hydrated.
   *
   * We only write AFTER pinHydrated has flipped to true for the current
   * key, so the load-race case described above can't happen. Empty sets
   * still persist (as an empty array) so clearing pins is remembered
   * too — otherwise a Clear pins + refresh would rehydrate the old
   * pins from storage.
   */
  useEffect(() => {
    if (!pinKey || !pinHydrated) return;
    try {
      localStorage.setItem(pinKey, JSON.stringify([...pinned]));
    } catch {
      // best-effort persistence — swallow quota/private-mode failures
    }
  }, [pinKey, pinHydrated, pinned]);

  /*
   * Resolved analogs + cone.
   *
   * Resolution order:
   *   1. API result (apiAnalogs / apiCone) if online and present.
   *   2. Persisted search result (searchedAnalogs / searchedCone) — this
   *      is what the manual `runSearch()` writes for both the API and
   *      synthetic paths.
   *   3. Empty array — first render before any search has run.
   *
   * Previously a `useMemo` recomputed `findAnalogs(...)` on EVERY change
   * to windowState, which meant the cone flickered continuously as the
   * user dragged. Now the displayed cone is strictly the output of the
   * last `runSearch()` call — dragging no longer mutates it. The
   * `isDirty` derivation below tells the user when the displayed result
   * is stale relative to the current inputs.
   */
  // Wrapped in useMemo so the identity only changes when one of the
  // underlying arrays actually changes — downstream useMemo hooks that
  // depend on `analogs`/`cone` otherwise re-run on every render because
  // the conditional ternary returns a fresh expression each time.
  const analogs: AnalogMatch[] = useMemo(
    () => ((isOnline && apiAnalogs) ? apiAnalogs : (searchedAnalogs ?? [])),
    [isOnline, apiAnalogs, searchedAnalogs],
  );

  /*
   * Resolve the currently-inspected analog.
   *
   * We look up by id on each render rather than caching the analog itself,
   * because a re-search replaces the analog set wholesale — stale pointers
   * from the previous search would leave the drawer showing outdated lens
   * scores. Falling through to null when the id no longer resolves also
   * auto-closes the drawer on a new search if the selection didn't carry
   * over (the drawer only renders `open` when both detailAnalogId AND the
   * resolved analog are present).
   */
  const detailAnalog = useMemo(
    () => (detailAnalogId ? analogs.find(a => a.id === detailAnalogId) ?? null : null),
    [analogs, detailAnalogId],
  );

  /*
   * Keep `analogsRef` in sync with the latest analog list.
   *
   * The 1..6 keyboard handler reads the ref rather than closing over
   * `analogs` directly so the listener (installed once on mount) always
   * sees the current set. Without this sync the shortcut would fire for
   * the ORIGINAL search's analogs forever, even after a re-search.
   */
  useEffect(() => { analogsRef.current = analogs; }, [analogs]);

  /*
   * Pin-gated analog set — the heart of "curation drives the forecast".
   *
   * Semantics:
   *   - pinned.size === 0 → baseline: the full top-K analog set is
   *     the basis for the cone, metrics, and lens radar.
   *   - pinned.size >= 1  → curated: every downstream consumer
   *     (compLenses, coneStats, trust strip, lens radar, composite metric)
   *     reads ONLY the pinned subset. The user is asserting "these are
   *     the analogs I trust" and the UI honors that assertion by
   *     recomputing everything as if the top-K set were exactly those pins.
   *
   * Defensive floor: if every pinned id somehow fails to resolve
   * (e.g. stale pins loaded from localStorage pointing at analogs a
   * re-search no longer returned), the filter collapses to zero. We
   * fall back to the full analog set in that case — a silent degrade
   * beats a blank forecast — and surface a note in the banner so the
   * user understands why their pins aren't filtering.
   *
   * Identity stability: when pinned is empty we return the exact
   * `analogs` array by reference (not a new filtered copy) so downstream
   * memos that depend on `effectiveAnalogs` don't thrash on every render.
   */
  const effectiveAnalogs: AnalogMatch[] = useMemo(() => {
    if (pinned.size === 0) return analogs;
    const filtered = analogs.filter(a => pinned.has(a.id));
    // Degrade: a non-empty pin set that resolved to zero results falls
    // back to the full set so the UI doesn't blank out. The banner will
    // tell the user the pins didn't match any current analogs.
    return filtered.length > 0 ? filtered : analogs;
  }, [analogs, pinned]);

  /*
   * Pin-gated forecast cone.
   *
   * When pinned.size > 0 we IGNORE the backend-computed apiCone (which
   * was computed server-side over the full top-K) and recompute locally
   * via buildCone() — same algorithm as the synthetic fallback path.
   * This keeps the cone semantically tied to `effectiveAnalogs`: the
   * quantiles reflect the curated subset, not the original top-K.
   *
   * When pinned.size === 0 the baseline resolution order applies:
   *   1. apiCone (if online and present)
   *   2. searchedCone (last successful runSearch result)
   *   3. empty array
   *
   * Note: the price anchor for local buildCone is `queryLastPrice` from
   * the CURRENT windowState, not lastSearch.start — this matches what
   * the chart displays as the query terminal bar.
   */
  const cone: ConePoint[] = useMemo(() => {
    if (pinned.size > 0 && effectiveAnalogs.length > 0) {
      const queryLastIdx = windowState.start + windowState.len - 1;
      const queryLastPrice = loadedSeries[queryLastIdx]?.p ?? 1;
      const horizon = lastSearch?.horizon ?? settings.horizon ?? 60;
      return buildCone(effectiveAnalogs, horizon, queryLastPrice);
    }
    return (isOnline && apiCone) ? apiCone : (searchedCone ?? []);
  }, [
    pinned,
    effectiveAnalogs,
    isOnline,
    apiCone,
    searchedCone,
    windowState.start,
    windowState.len,
    loadedSeries,
    lastSearch?.horizon,
    settings.horizon,
  ]);

  /*
   * Dirty detection — true when the current windowState+settings no
   * longer match the snapshot captured at last-search time. Used to
   * pulse the Search button so the user knows the displayed cone
   * doesn't reflect the current query window / top-K / horizon.
   */
  const currentK = settings.kAnalogs || 6;
  const currentHorizon = settings.horizon || 60;

  /*
   * View-range sanity check.
   *
   * When the user picks a long horizon (e.g. 365 bars on daily data),
   * the forecast cone extends ~17 months past the query window. If
   * viewRange.end is shorter than `queryEnd + horizon + 5`, the right
   * edge of the cone gets clipped off the chart and the visualization
   * lies about how long the forecast runs.
   *
   * Guardrail: when horizon or windowState changes, if the cone would
   * be clipped, extend viewRange.end just enough to fit it (+5 bar
   * pad). We NEVER contract the view — that would yank context out
   * from under the user. We also clamp to the series length so we
   * don't scroll past the end of data.
   *
   * This runs in an effect rather than inline in setViewRange because
   * horizon changes come from onSettings (owned by app/page.tsx) and
   * we can't intercept them here — we have to react.
   */
  useEffect(() => {
    const queryEnd = windowState.start + windowState.len - 1;
    const minRequiredEnd = Math.min(N - 1, queryEnd + currentHorizon + 5);
    if (viewRange.end < minRequiredEnd) {
      setViewRange(v => ({ ...v, end: minRequiredEnd }));
    }
    // Only re-run when the inputs to the clip-check change. viewRange.end
    // is intentionally omitted from deps to avoid a feedback loop (we
    // write to it inside this effect).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentHorizon, windowState.start, windowState.len, N]);
  const isDirty = !lastSearch
    || lastSearch.start !== windowState.start
    || lastSearch.len !== windowState.len
    || lastSearch.k !== currentK
    || lastSearch.horizon !== currentHorizon;

  // Composite lenses = mean across the EFFECTIVE analog set.
  // When the user has pinned analogs, these are just the pinned ones —
  // so the radar/bars show the mean agreement of their curated set,
  // not the original top-K. This is the whole reason effectiveAnalogs
  // exists: pinning drives what the workstation displays.
  const compLenses = useMemo(() => {
    const keys = LENS_DEFS.map(d => d.key);
    const out: Record<string, number> = {};
    keys.forEach(k => {
      out[k] = effectiveAnalogs.reduce((s, a) => s + (a.lenses[k as keyof LensScores] || 0), 0) / (effectiveAnalogs.length || 1);
    });
    return out as unknown as LensScores;
  }, [effectiveAnalogs]);

  // Cone endpoint statistics for the header metrics. Cone itself is
  // already pin-gated upstream (see the `cone` useMemo), so these
  // summary stats inherit pin-gating automatically — no further changes
  // needed here. Kept the dependency list the same.
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

  // Catalog source for the dropdown.
  //
  // Online mode: use the live /catalog response.
  // Offline / demo mode: use a static synthetic entry so the dropdown
  // still renders something legible rather than an empty panel. We
  // intentionally DO NOT fetch /catalog in offline mode (see the mount
  // effect), so this is the sole source of items in that path.
  const dropdownCatalog = useMemo<CatalogItem[]>(() => {
    if (isOnline === false) return offlineSyntheticCatalog();
    return catalog;
  }, [catalog, isOnline]);

  // Filtered + grouped catalog for the dropdown panel. Filter runs
  // first so empty groups disappear when the user narrows by symbol.
  const filteredCatalog = useMemo(
    () => filterCatalog(dropdownCatalog, datasetSearch),
    [dropdownCatalog, datasetSearch],
  );
  const groupedCatalog = useMemo(
    () => groupByAssetClass(filteredCatalog),
    [filteredCatalog],
  );

  // The catalog entry for the currently-selected dataset. Used for the
  // compact selected-summary rendered on the trigger button and for the
  // freshness line under the Dataset header. Null when the active
  // dataset id doesn't (yet) appear in the catalog — that's a legit
  // transient state between mount and the first /catalog response.
  const selectedItem = useMemo<CatalogItem | null>(() => {
    return (
      dropdownCatalog.find(
        d => `${d.assetClass}/${d.symbol}/${d.timeframe}` === activeDataset,
      ) ?? null
    );
  }, [dropdownCatalog, activeDataset]);

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
      data-left-drawer={leftDrawerOpen ? "open" : "closed"}
    >
      {/* ── Small-screen notice (<768px) ─────────────────────── */}
      {/* Polite, non-blocking: the layout below still renders, but this
          hint appears at the top so a mobile visitor knows what to expect. */}
      <div className="ws-mobile-notice" role="note">
        Best viewed on a desktop display (&ge; 1024px). Layout is compact on this screen.
      </div>

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
      <aside className="side" id="workstation-left-panel">
        {/* Close button — visible only when the sidebar is a drawer (768-1023px) */}
        <button
          type="button"
          className="ws-drawer-close ws-drawer-close--left"
          aria-label="Close controls panel"
          onClick={() => setLeftDrawerOpen(false)}
        >
          &times;
        </button>
        {/* ──────────────────────────────────────────────────────────
            Dataset selector — custom dropdown with rich metadata cards.

            Contract:
            - The trigger button shows the currently-selected dataset
              as a single-line summary (symbol · timeframe · bar count
              · relative update).
            - A freshness line ("updated · 16m ago") sits directly
              under the "Dataset" label so the user can read liveness
              at a glance without opening the dropdown. It flips to the
              --warn colour once the data is >7 days old.
            - Opening the dropdown reveals grouped per-item cards with
              source, row count, date range, and an absolute "Updated:"
              timestamp. A staleness dot appears on items that are
              >48h old (for daily-or-faster timeframes).
            - A search input at the top filters by symbol / asset class
              substring and dissolves empty groups.
            - Offline mode renders a single "Synthetic · seeded PRNG"
              entry; /catalog is NOT fetched in that path.
         ─────────────────────────────────────────────────────────── */}
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
          {/* Freshness line under the header. Visible whenever we have
              a last-updated timestamp; styled warn when >7d old. */}
          {selectedItem?.lastUpdatedAt && (() => {
            const updatedAt = parseIsoOrNull(selectedItem.lastUpdatedAt);
            if (!updatedAt) return null;
            const ageDays = (nowTick.getTime() - updatedAt.getTime()) / 86_400_000;
            const warn = ageDays > 7;
            return (
              <div
                className="dataset-freshness"
                data-warn={warn ? "true" : undefined}
                title={`Last updated ${formatUpdatedAt(selectedItem.lastUpdatedAt)}`}
              >
                updated &middot; {formatRelativeTime(updatedAt, nowTick)}
              </div>
            );
          })()}
          <button
            type="button"
            className="dataset-trigger"
            aria-haspopup="listbox"
            aria-expanded={datasetOpen}
            onClick={() => {
              setDatasetOpen(o => !o);
              // Reset the in-panel search whenever we open/close so the
              // user always starts from the full list.
              setDatasetSearch("");
            }}
          >
            <span className="dataset-trigger__main">
              <span className="dataset-trigger__symbol">
                {datasetLabel}
              </span>
              <span className="dataset-trigger__meta">
                {selectedItem
                  ? [
                      formatBarCount(selectedItem.rowCount),
                      selectedItem.lastUpdatedAt
                        ? `updated ${formatRelativeTime(
                            parseIsoOrNull(selectedItem.lastUpdatedAt) ?? nowTick,
                            nowTick,
                          )}`
                        : null,
                    ]
                      .filter(Boolean)
                      .join(" \u00B7 ")
                  : "—"}
              </span>
            </span>
            <span className="dataset-trigger__caret" aria-hidden="true">
              {datasetOpen ? "\u25B2" : "\u25BC"}
            </span>
          </button>
          {datasetOpen && (
            <div className="dataset-panel" role="listbox" aria-label="Select dataset">
              <input
                type="search"
                className="dataset-panel__search"
                placeholder="Filter by symbol or asset class"
                value={datasetSearch}
                onChange={e => setDatasetSearch(e.target.value)}
                autoFocus
                aria-label="Filter datasets"
              />
              <div className="dataset-panel__list">
                {Object.entries(groupedCatalog).length === 0 && (
                  <div className="dataset-panel__empty">
                    {isOnline === false
                      ? "Offline — synthetic entry above."
                      : catalog.length === 0
                      ? "No datasets registered."
                      : "No matches."}
                  </div>
                )}
                {Object.entries(groupedCatalog).map(([assetClass, items]) => (
                  <div key={assetClass} className="dataset-panel__group">
                    <div className="dataset-panel__group-header">
                      {assetClass}
                    </div>
                    {items.map(item => {
                      const id = `${item.assetClass}/${item.symbol}/${item.timeframe}`;
                      const selected = id === activeDataset;
                      const stale = isStale(item, nowTick);
                      // Only show staleness for online data (synthetic
                      // has no concept of freshness).
                      const showStaleDot = stale && isOnline !== false;
                      return (
                        <button
                          key={id}
                          type="button"
                          role="option"
                          aria-selected={selected}
                          className="dataset-card"
                          data-selected={selected ? "true" : undefined}
                          onClick={() => {
                            setActiveDataset(id);
                            setDatasetOpen(false);
                            setDatasetSearch("");
                          }}
                        >
                          <div className="dataset-card__title-row">
                            <span className="dataset-card__title">
                              {item.symbol.toUpperCase()} &middot; {item.timeframe}
                            </span>
                            {showStaleDot && (
                              <span
                                className="dataset-card__stale-dot"
                                aria-hidden="true"
                                title={`Data may be stale (last updated ${
                                  item.lastUpdatedAt
                                    ? formatRelativeTime(
                                        parseIsoOrNull(item.lastUpdatedAt) ?? nowTick,
                                        nowTick,
                                      )
                                    : "unknown"
                                })`}
                              />
                            )}
                          </div>
                          <div className="dataset-card__sub">
                            {item.source}
                            {item.rowCount > 0 && (
                              <> &middot; {formatBarCount(item.rowCount)}</>
                            )}
                          </div>
                          {(item.startTimestamp || item.endTimestamp) && (
                            <div className="dataset-card__sub">
                              {formatShortDate(item.startTimestamp)} &rarr;{" "}
                              {formatShortDate(item.endTimestamp)}
                            </div>
                          )}
                          {item.lastUpdatedAt && (
                            <div className="dataset-card__sub dataset-card__sub--muted">
                              Updated: {formatUpdatedAt(item.lastUpdatedAt)}
                            </div>
                          )}
                          {isOnline === false && (
                            <div className="dataset-card__sub dataset-card__sub--muted">
                              Demo mode &mdash; data is synthetic, not real.
                            </div>
                          )}
                        </button>
                      );
                    })}
                  </div>
                ))}
              </div>
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
        {/* ── Pin-filtered banner ─────────────────────────────
            Renders only when the user has curated the analog set via
            pinning. The banner makes the curated state unmistakable
            (it's the difference between "top-K says +3%" and "my 2
            analogs say +3%") and gives a one-click escape hatch back
            to the top-K baseline. See CSS `.ws-pin-banner` for layout.

            Guard: we only show once there's actually something to
            filter. `effectiveAnalogs.length` is the authoritative count
            shown to the user — not `pinned.size`, because a pin
            referring to an analog the engine didn't return (stale
            localStorage) doesn't affect the forecast and shouldn't be
            counted in the banner number. */}
        {pinned.size > 0 && effectiveAnalogs.length > 0 && (
          <div
            className="ws-pin-banner"
            role="status"
            aria-live="polite"
          >
            <span className="ws-pin-banner__icon" aria-hidden="true">&#x1F3AF;</span>
            <span className="ws-pin-banner__text">
              Forecast from <strong>{effectiveAnalogs.length}</strong>{" "}
              pinned analog{effectiveAnalogs.length === 1 ? "" : "s"} (not top-K).
              {/* Fallback note: pins exist but none matched the current
                  analog set. effectiveAnalogs silently degrades to the
                  full set in that case; we surface the reason here. */}
              {pinned.size > 0 && analogs.filter(a => pinned.has(a.id)).length === 0 && (
                <> {" "}<em style={{ color: "var(--ink-3)" }}>
                  (saved pins didn&apos;t match current results — showing full set)
                </em></>
              )}
            </span>
            <button
              type="button"
              className="ws-pin-banner__clear"
              onClick={() => setPinned(new Set())}
              aria-label="Clear all pinned analogs"
            >
              Clear pins
            </button>
          </div>
        )}
        <header className="main__head">
          <div className="main__title-wrap">
            <div className="label" style={{ marginBottom: 6 }}>Retrieve &middot; analog workstation</div>
            <h1>What does <em>this</em> moment rhyme with?</h1>
            <div className="main__subtitle">
              Drag the query window along the timeline. The engine re-ranks {analogs.length} historical
              matches and redraws the forecast cone. Pin analogs to overlay them.
            </div>
            {/* Drawer toggles — each only visible in its own breakpoint via CSS.
                "Controls" (left drawer) appears at 768-1023px where the sidebar
                is hidden. "Details" (right drawer) appears at 1024-1279px where
                the right panel is hidden. */}
            <div className="ws-drawer-toggles">
              <button
                type="button"
                className="ws-drawer-toggle ws-drawer-toggle--left"
                aria-expanded={leftDrawerOpen}
                aria-controls="workstation-left-panel"
                onClick={() => setLeftDrawerOpen(o => !o)}
              >
                &larr; {leftDrawerOpen ? "Hide controls" : "Controls"}
              </button>
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
          </div>
          <div className="main__metrics">
            <div className="metric">
              <span className="label">Composite</span>
              {/* Top-of-set composite score. Reads from effectiveAnalogs so
                  when the user pins a curated subset, this reports the
                  best score AMONG the pins, not the original top-K. */}
              <span className="v">{(effectiveAnalogs[0]?.composite ?? 0).toFixed(2)}</span>
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

        {/* ── Search control row ───────────────────────────────────────
            Visible manual-search controls. Left group:
              - Top-K selector — compact segmented control mirroring the
                tweaks-panel setting so users don't have to open a panel
                to change how many analogs come back.
              - Search button — primary; pulses when isDirty (window or
                settings changed since last search).
              - Last-run timestamp — relative, ticks every 30s.
            The tweaks-panel K control is NOT removed; this is a mirror
            surface for discoverability. */}
        <div className="ws-search-row" role="group" aria-label="Search controls">
          <div className="ws-search-row__group">
            <span className="label ws-search-row__label">Top K</span>
            <div className="ws-topk" role="radiogroup" aria-label="Number of analog matches to return">
              {[1, 3, 6, 10].map(k => (
                <button
                  key={k}
                  type="button"
                  role="radio"
                  aria-checked={currentK === k}
                  className="ws-topk__btn"
                  data-active={currentK === k ? "true" : undefined}
                  onClick={() => onSettings({ ...settings, kAnalogs: k })}
                >
                  {k}
                </button>
              ))}
            </div>
            {/* ── Horizon selector ──────────────────────────────────────
                Presets: 30/60/120/180/250/365 bars. The backend (FastAPI
                /search) accepts any forward_bars value — this control is
                purely a UI affordance to drive `settings.horizon` without
                opening the tweaks panel.

                Behavior:
                  - Changing the value updates settings via onSettings;
                    horizon is a field on WorkstationSettings that already
                    persists through localStorage in app/page.tsx, so no
                    new persistence wiring is needed.
                  - This flips isDirty (see the derivation below which
                    already diffs lastSearch.horizon vs currentHorizon),
                    which makes the Search button pulse. Searches do NOT
                    auto-fire — user clicks Search or presses Enter/r.
                  - The `d` suffix on each button disambiguates the unit
                    (bars-on-a-daily-series) without cluttering the label.
                  - Tabular-num is applied via the .ws-horizon__btn CSS so
                    three-digit vs two-digit values don't cause width jitter.

                Coordination note: top-K is on the left of the search row;
                Agent D is adding a chart-mode toggle elsewhere in this file.
                This selector stays adjacent to .ws-topk to keep "what the
                search computes" controls grouped together. */}
            <span className="label ws-search-row__label ws-search-row__label--secondary">
              Horizon
            </span>
            <div
              className="ws-horizon"
              role="radiogroup"
              aria-label="Forecast horizon in bars"
            >
              {[30, 60, 120, 180, 250, 365].map(h => (
                <button
                  key={h}
                  type="button"
                  role="radio"
                  aria-checked={currentHorizon === h}
                  className="ws-horizon__btn"
                  data-active={currentHorizon === h ? "true" : undefined}
                  onClick={() => onSettings({ ...settings, horizon: h })}
                  title={`Forecast ${h} bars forward`}
                >
                  {h}d
                </button>
              ))}
            </div>
            {/*
             * View-range clip hint.
             *
             * The forecast cone is drawn from query_end → query_end + horizon
             * on the chart's x-axis. If the current viewRange ends before
             * that, the right end of the cone gets clipped and the user
             * sees a truncated forecast. We surface a passive hint here so
             * the user knows *why* the cone looks short, without being
             * intrusive (it's just a small info icon with a tooltip — no
             * modal, no auto-scroll).
             *
             * Math: viewRange.end must be at least `queryEnd + horizon + 5`
             * for the cone to sit comfortably inside the view. We add the
             * 5-bar pad so the terminal marker isn't flush against the
             * right edge.
             */}
            {(() => {
              const queryEnd = windowState.start + windowState.len - 1;
              const coneEnd = queryEnd + currentHorizon;
              const wouldClip = viewRange.end < coneEnd + 5;
              if (!wouldClip) return null;
              return (
                <span
                  className="ws-horizon__clip-hint"
                  role="note"
                  aria-label="View range warning"
                  title="View range doesn't cover forecast — expand to see the full cone."
                >
                  <svg width="11" height="11" viewBox="0 0 12 12" aria-hidden="true">
                    <circle cx="6" cy="6" r="5" fill="none" stroke="currentColor" strokeWidth="1.2" />
                    <line x1="6" y1="4" x2="6" y2="7" stroke="currentColor" strokeWidth="1.2" />
                    <circle cx="6" cy="9" r="0.7" fill="currentColor" />
                  </svg>
                </span>
              );
            })()}
          </div>
          <div className="ws-search-row__group ws-search-row__group--end">
            {/*
             * Fewer-matches warning.
             *
             * From the_similarity/core/projector.py: a candidate match is
             * dropped when `match.end_idx + forward_bars > len(history)` —
             * i.e. there aren't enough post-match bars to realize the
             * forecast. At long horizons (180, 250, 365) this can
             * collapse the analog set dramatically on short series.
             *
             * Guard conditions:
             *   - Only render AFTER a search has run (lastSearch !== null).
             *     Before the first search it would be misleading ("0 of 6"
             *     when we simply haven't searched yet).
             *   - Only render when we got strictly fewer results than the
             *     requested K. Equal or greater is a clean run.
             *   - Not while a search is in flight (stale while refreshing).
             *
             * The warning is inline-muted rather than a banner because it
             * reflects a data-property (history depth), not an error
             * state. Quants can read it, digest it, and decide whether
             * to pick a shorter horizon or accept the smaller analog set.
             */}
            {!searching && lastSearch !== null && searchedAnalogs !== null && searchedAnalogs.length < lastSearch.k && (
              <span
                className="ws-search-row__fewer-matches mono"
                role="note"
                aria-live="polite"
              >
                Only {searchedAnalogs.length} of {lastSearch.k} analogs have
                enough forward history at this horizon.
              </span>
            )}
            {lastRunAt && (
              <span className="ws-search-row__lastrun mono" aria-live="polite">
                Last run &middot; {formatRelativeTime(lastRunAt, nowTick)}
              </span>
            )}
            <button
              type="button"
              className="ws-search-btn"
              data-dirty={isDirty && !searching ? "true" : undefined}
              data-searching={searching ? "true" : undefined}
              onClick={() => runSearch()}
              disabled={searching}
              aria-label={
                searching
                  ? "Searching"
                  : isDirty
                  ? "Search (pending changes)"
                  : "Search"
              }
            >
              {searching ? (
                <>
                  <span className="ws-search-btn__spinner" aria-hidden="true" />
                  <span>Searching&hellip;</span>
                </>
              ) : (
                <>
                  <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.4" aria-hidden="true">
                    <circle cx="5" cy="5" r="3.5" />
                    <line x1="7.5" y1="7.5" x2="11" y2="11" />
                  </svg>
                  <span>Search</span>
                  {isDirty && <span className="ws-search-btn__dot" aria-hidden="true" />}
                </>
              )}
            </button>
          </div>
        </div>

        <div className="chart-stack">
          {/* Chart-mode toggle — "Fast" SVG vs "Pro" lightweight-charts.
              Sits just above the chart-card so it doesn't collide with the
              search/top-K row (owned by another agent). Keeping this a tiny
              right-aligned segmented control keeps it in the same
              .ws-chartmode pattern as the nearby chip rows. */}
          <div
            className="ws-chartmode-row"
            role="region"
            aria-label="Chart view mode"
          >
            <div className="ws-chartmode" role="tablist" aria-label="Chart view">
              {([
                { id: "fast", label: "Fast", hint: "SVG chart, draggable query window" },
                { id: "pro",  label: "Pro",  hint: "TradingView-grade canvas, read-only window" },
              ] as const).map(opt => {
                const active = (settings.chartMode ?? "fast") === opt.id;
                return (
                  <button
                    key={opt.id}
                    type="button"
                    role="tab"
                    aria-selected={active}
                    title={opt.hint}
                    className="ws-chartmode__btn"
                    data-active={active ? "true" : undefined}
                    onClick={() => onSettings({ ...settings, chartMode: opt.id })}
                  >
                    {opt.label}
                  </button>
                );
              })}
            </div>
          </div>
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
                {/* Per-rank legend dots — one colored pip per analog, colored
                    to match the chart overlay AND the card's left border. A
                    click on a dot toggles the pin on that analog (same as
                    clicking the card). The dot's alpha ring marks pinned
                    state so the legend mirrors the card strip's pin state.
                    We render up to analogOverlays.length dots; the
                    "Analogs (N)" label stays as a text prefix so the
                    existing "is it only showing top 1?" question lands a
                    visible count even when dots wrap. */}
                <span className="legend-dot analog">
                  <i />Analogs ({analogOverlays.length})
                </span>
                {analogOverlays.map((a, i) => {
                  const id = a.id;
                  const isPinned = !!a.pinned;
                  return (
                    <span
                      key={`legend-rank-${id ?? i}`}
                      className="legend-dot analog-rank"
                      data-rank={i}
                      data-pinned={isPinned ? "true" : undefined}
                    >
                      <button
                        type="button"
                        aria-label={`Toggle pin on analog ${i + 1}`}
                        title={isPinned ? "Unpin this analog" : "Pin this analog"}
                        onClick={() => { if (id) togglePin(id); }}
                        onMouseEnter={() => { if (id) setHoverAnalog(id); }}
                        onMouseLeave={() => setHoverAnalog(null)}
                      >
                        <i />
                        <span>#{i + 1}</span>
                      </button>
                    </span>
                  );
                })}
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
              {loadedSeries.length === 0 ? (
                // Dataset loaded but returned zero bars — better to tell the
                // user than silently render an empty chart axis.
                <div className="ws-micro-empty" role="status">
                  <div className="ws-micro-empty__title">No data in this window</div>
                  <div className="ws-micro-empty__body">
                    The current dataset returned zero bars. Try a different dataset
                    or widen the view range.
                  </div>
                </div>
              ) : (
                // Pro view uses lightweight-charts; Fast view uses the SVG chart.
                // Props are identical so we spread the same object into whichever
                // component is active — keeps behavior drift between the two
                // views localised to each renderer's internals.
                (() => {
                  const sharedChartProps = {
                    series: loadedSeries,
                    viewStart: viewRange.start,
                    viewEnd: viewRange.end,
                    window: windowState,
                    onWindowChange: setWindowState,
                    analogsOverlay: analogOverlays,
                    cone,
                    forecastHorizon: settings.horizon || 60,
                    onHover: setCrosshairIdx,
                    crosshairIdx,
                    height: 380,
                    showCone: settings.showCone !== false,
                    // Drives the per-analog hover preview in both chart
                    // renderers. Set from the .analog-card mouse
                    // enter/leave handlers in the strip below.
                    hoveredAnalogId: hoverAnalog,
                  };
                  return (settings.chartMode ?? "fast") === "pro"
                    ? <LineChartLW {...sharedChartProps} />
                    : <LineChart {...sharedChartProps} />;
                })()
              )}
            </div>
          </div>
        </div>

        {/* ── Trust strip (computed from THIS query's analogs) ──────────────
            Metrics flow: the trust strip reads `trustMetrics`, which is
            `computeCalibrationMetrics(analogs, cone, queryLastPrice)`.
            This is *in-sample* — each analog's forward window is compared
            against the engine's own forecast cone. Numbers change with
            every query because the analog set changes.

            When backend integration lands (SearchResponse.metrics), swap
            the `computeCalibrationMetrics(...)` call for `apiMetrics ??
            computeCalibrationMetrics(...)` so backend ground-truth wins
            and the client-side derivation is the fallback.

            Grade drives the badge color:
              A → positive (green), B → accent (blue),
              C → warning (amber), D/F → negative (red),
              unknown → muted (grey, em-dashes for numerics).           */}
        <div style={{ display: "flex", flexDirection: "column" }}>
          {(() => {
            // Compute metrics inline so hooks outside this block are
            // untouched. The computation is O(analogs * percentiles)
            // and runs once per render — cheap.
            //
            // Pin-gating: we pass effectiveAnalogs (not analogs) so a PM
            // who has pinned 2 analogs sees Coverage/CRPS/HitRate/Grade
            // computed ONLY on those 2. This is the critical quant-
            // credibility path — the trust strip must answer "how well
            // does the cone I'm looking at match its empirical history",
            // and when curation changes the cone, it must change the
            // metrics too. `cone` above is already pin-gated.
            const queryLastPrice = loadedSeries[windowState.start + windowState.len - 1]?.p ?? 1;
            const trustMetrics: CalibrationResult = computeCalibrationMetrics(
              effectiveAnalogs,
              cone,
              queryLastPrice,
            );
            const isUnknown = trustMetrics.grade === "unknown";
            // Numeric badge class per metric value — mirrors the live-data
            // sign convention used elsewhere in the trust strip.
            const coverageGap = Math.abs(trustMetrics.coverage - 0.80);
            const coverageClass = isUnknown
              ? ""
              : coverageGap <= 0.05 ? "pos"
              : coverageGap <= 0.15 ? ""
              : "warn";
            const hitClass = isUnknown
              ? ""
              : trustMetrics.hitRate >= 0.55 ? "pos"
              : trustMetrics.hitRate >= 0.50 ? ""
              : "neg";
            const driftClass = isUnknown
              ? ""
              : trustMetrics.regimeDrift === "low" ? "pos"
              : trustMetrics.regimeDrift === "elevated" ? "warn"
              : "neg";
            // Em-dash placeholders whenever the engine returned unknown,
            // so a quant can distinguish "no data yet" from "zero".
            const dash = "\u2014";
            // ℹ glyph — rendered next to each metric label so quants get
            // a one-sentence definition on hover without leaving the page.
            // Intentionally uses the native `title` attribute: acceptable
            // shortcut per the calibration-panel audit spec, avoids adding
            // a custom tooltip layer (and its accessibility footguns) to
            // the workstation bundle. Screen readers announce `title` as
            // an accessible name, so the explanations are surfaced there
            // as well. 12px sizing matches the muted .label typography.
            const infoGlyph = (tip: string) => (
              <span
                className="trust__info"
                role="img"
                aria-label={tip}
                title={tip}
              >
                &#9432;
              </span>
            );
            return (
              <>
                <div className="trust">
                  <div className="trust__item">
                    <span className="label">
                      Coverage 80%
                      {infoGlyph("Coverage: fraction of realized moves that landed inside the P10-P90 cone. Target 80%.")}
                    </span>
                    <span className={"v " + coverageClass}>
                      {isUnknown ? dash : fmtPct(trustMetrics.coverage, 1)}
                    </span>
                  </div>
                  <div className="trust__item">
                    <span className="label">
                      CRPS
                      {infoGlyph("CRPS (Continuous Ranked Probability Score): lower is better. Measures how well the probability distribution matched the realized outcome.")}
                    </span>
                    <span className="v">
                      {isUnknown ? dash : trustMetrics.crps.toFixed(3)}
                    </span>
                  </div>
                  <div className="trust__item">
                    <span className="label">
                      Hit rate &middot; sign
                      {infoGlyph("Hit rate: fraction of analogs whose forward direction matched the realized direction at horizon. Chance baseline is 0.50.")}
                    </span>
                    <span className={"v " + hitClass}>
                      {isUnknown ? dash : trustMetrics.hitRate.toFixed(2)}
                    </span>
                  </div>
                  <div className="trust__item">
                    <span className="label">
                      Regime drift
                      {infoGlyph("Regime drift: how much the market regime has changed between the analogs and now. Low is good; high means the analog set may be stale.")}
                    </span>
                    <span className={"v " + driftClass}>
                      {isUnknown ? dash : trustMetrics.regimeDrift}
                    </span>
                  </div>
                  <div className="trust__item">
                    <span className="label">
                      N analogs used
                      {infoGlyph("Number of analogs with realized forward windows used to compute these metrics. Pinning filters this set.")}
                    </span>
                    <span className="v">{trustMetrics.nAnalogs}</span>
                  </div>
                  <button className="trust__expand" onClick={() => setTrustOpen(o => !o)}>
                    {trustOpen ? "Hide" : "Open"} calibration panel &rarr;
                  </button>
                </div>

                {trustOpen && isUnknown && (
                  // Empty-state card: we avoid rendering the reliability
                  // diagram or per-bucket bar chart at all when the engine
                  // has insufficient data, because drawing either with zero
                  // buckets produces visually-empty plots that quants read
                  // as "calibration is broken" rather than "not enough
                  // runs yet". Instead we surface a concrete explanation
                  // and a CTA. The link target is a placeholder — once
                  // backtest-sweep UI lands it should point at that route
                  // (see Batch 2 finance operating product roadmap).
                  <div className="trust-panel trust-panel--empty" role="status">
                    <div className="trust-panel__empty-card">
                      <h3>Calibration needs more runs</h3>
                      <p>
                        The engine has fewer than 3 analogs with realised
                        forward windows against this query. Coverage, CRPS,
                        and the reliability diagram need at least a handful
                        of observed outcomes before they carry signal. Trust
                        score will appear automatically once the engine has
                        accumulated at least 30 runs against this dataset.
                      </p>
                      <a
                        href="/finance/reviews"
                        className="trust-panel__cta"
                      >
                        Trigger backtest sweep &rarr;
                      </a>
                    </div>
                  </div>
                )}
                {trustOpen && !isUnknown && (
                  <div className="trust-panel">
                    <div>
                      <h3>Reliability diagram</h3>
                      <svg viewBox="0 0 260 160" width="100%" height="160">
                        <rect x="1" y="1" width="258" height="158" fill="none" stroke="var(--rule)" />
                        {/* Identity line y=x → perfect calibration reference.
                            Plot region: x in [20, 240], y in [140, 20]. */}
                        <line x1="20" y1="140" x2="240" y2="20" stroke="var(--ink-4)" strokeDasharray="3 3" />
                        {/* Empirical (predicted, observed) scatter, coloured
                            by deviation from the identity line.
                            •  |obs − pred| < 0.10  → green  (well-calibrated)
                            •  0.10 ≤ |…| < 0.20    → amber  (watch)
                            •  |obs − pred| ≥ 0.20  → red    (mis-calibrated)
                            Prior behaviour painted every dot green, which
                            hid bad buckets — fixed as of the calibration-
                            panel audit (obsidian/topics/calibration panel
                            audit 2026-04-20). Each dot carries a native
                            <title> so hovering surfaces the raw numbers
                            without requiring a custom tooltip layer. */}
                        {trustMetrics.reliability.length === 0 ? (
                          <text x="130" y="80" textAnchor="middle" fontSize="11" fill="var(--ink-3)">
                            not enough data
                          </text>
                        ) : (
                          trustMetrics.reliability.map((pt, i) => {
                            const pClamped = Math.max(0, Math.min(1, pt.predicted));
                            const oClamped = Math.max(0, Math.min(1, pt.observed));
                            const deviation = Math.abs(oClamped - pClamped);
                            const color = deviation < 0.10
                              ? "var(--positive)"
                              : deviation < 0.20
                              ? "var(--warn)"
                              : "var(--negative)";
                            return (
                              <circle
                                key={i}
                                cx={20 + pClamped * 220}
                                cy={140 - oClamped * 120}
                                r="3.5"
                                fill={color}
                              >
                                <title>
                                  {`predicted ${pClamped.toFixed(2)} · observed ${oClamped.toFixed(2)} · deviation ${deviation.toFixed(2)}`}
                                </title>
                              </circle>
                            );
                          })
                        )}
                        <text x="20" y="154" className="axis-label" fontSize="9" fill="var(--ink-3)">predicted</text>
                        <text x="4" y="20" className="axis-label" fontSize="9" fill="var(--ink-3)" transform="rotate(-90 8 20)">observed</text>
                      </svg>
                      <div style={{ fontSize: 12, color: "var(--ink-2)", marginTop: 8 }}>
                        {trustMetrics.reliability.length === 0
                          ? "Not enough analogs with forward windows to build a reliability diagram."
                          : (() => {
                              // Max absolute deviation from the identity line, in
                              // percentage points. Makes the narrative change per
                              // query instead of claiming a static "within 4pp".
                              const maxDev = Math.max(
                                ...trustMetrics.reliability.map(r => Math.abs(r.observed - r.predicted)),
                              );
                              return `Predicted quantiles match observed frequencies to within ${(maxDev * 100).toFixed(1)} percentage points.`;
                            })()}
                      </div>
                    </div>
                    <div>
                      <h3>Per-bucket observed frequency</h3>
                      <svg viewBox="0 0 260 160" width="100%" height="160">
                        <rect x="1" y="1" width="258" height="158" fill="none" stroke="var(--rule)" />
                        {/* Previous implementation drew 12 IDENTICAL bars,
                            all at height = trustMetrics.coverage. That
                            looked like a rolling time-series but was a
                            synthetic placeholder (same number painted 12
                            times). It's been replaced with the real per-
                            percentile observed frequency derived from
                            trustMetrics.reliability[] — the thing that
                            actually changes per query and per pin set.
                            A perfectly calibrated engine has every bar
                            at height = its predicted quantile. */}
                        {trustMetrics.reliability.length === 0 ? (
                          <text x="130" y="90" textAnchor="middle" fontSize="11" fill="var(--ink-3)">
                            not enough data
                          </text>
                        ) : (() => {
                            // Plot region: x in [30, 250], y in [140, 20].
                            // Bar slot width derived from the number of
                            // reliability buckets so the layout scales
                            // correctly if the backend adds more.
                            const n = trustMetrics.reliability.length;
                            const plotLeft = 30;
                            const plotRight = 250;
                            const plotTop = 20;
                            const plotBottom = 140;
                            const slotW = (plotRight - plotLeft) / n;
                            const barW = Math.max(8, slotW * 0.55);
                            const plotH = plotBottom - plotTop;
                            // Guide lines at y = 0, 0.5, 1.0 so the eye can
                            // read deviation without counting pixels.
                            const guideYs = [0, 0.5, 1];
                            return (
                              <g>
                                {guideYs.map(g => (
                                  <line
                                    key={`g-${g}`}
                                    x1={plotLeft}
                                    x2={plotRight}
                                    y1={plotBottom - g * plotH}
                                    y2={plotBottom - g * plotH}
                                    stroke="var(--rule)"
                                    strokeDasharray="2 3"
                                  />
                                ))}
                                {trustMetrics.reliability.map((pt, i) => {
                                  const oClamped = Math.max(0, Math.min(1, pt.observed));
                                  const pClamped = Math.max(0, Math.min(1, pt.predicted));
                                  const deviation = Math.abs(oClamped - pClamped);
                                  const barColor = deviation < 0.10
                                    ? "var(--positive)"
                                    : deviation < 0.20
                                    ? "var(--warn)"
                                    : "var(--negative)";
                                  const cx = plotLeft + slotW * (i + 0.5);
                                  const x = cx - barW / 2;
                                  const y = plotBottom - oClamped * plotH;
                                  const predY = plotBottom - pClamped * plotH;
                                  return (
                                    <g key={`bar-${i}`}>
                                      {/* Observed bar (colored by deviation). */}
                                      <rect
                                        x={x}
                                        y={y}
                                        width={barW}
                                        height={plotBottom - y}
                                        fill={barColor}
                                        opacity={0.85}
                                      >
                                        <title>
                                          {`P${Math.round(pClamped * 100)} · observed ${oClamped.toFixed(2)} · predicted ${pClamped.toFixed(2)} · deviation ${deviation.toFixed(2)}`}
                                        </title>
                                      </rect>
                                      {/* Predicted-quantile tick: where the
                                          bar WOULD end for a perfectly
                                          calibrated engine. */}
                                      <line
                                        x1={x - 2}
                                        x2={x + barW + 2}
                                        y1={predY}
                                        y2={predY}
                                        stroke="var(--ink)"
                                        strokeWidth="1"
                                        strokeDasharray="2 2"
                                      />
                                      {/* Per-bucket x-label: the predicted
                                          quantile, so a quant can read e.g.
                                          "P25 observed 0.32" at a glance. */}
                                      <text
                                        x={cx}
                                        y={plotBottom + 12}
                                        textAnchor="middle"
                                        fontSize="9"
                                        fill="var(--ink-3)"
                                      >
                                        {`P${Math.round(pClamped * 100)}`}
                                      </text>
                                    </g>
                                  );
                                })}
                                {/* y-axis reference labels (0 / 0.5 / 1). */}
                                {guideYs.map(g => (
                                  <text
                                    key={`yl-${g}`}
                                    x={plotLeft - 4}
                                    y={plotBottom - g * plotH + 3}
                                    textAnchor="end"
                                    fontSize="9"
                                    fill="var(--ink-3)"
                                  >
                                    {g.toFixed(1)}
                                  </text>
                                ))}
                              </g>
                            );
                          })()}
                      </svg>
                      <div style={{ fontSize: 12, color: "var(--ink-2)", marginTop: 8 }}>
                        {trustMetrics.reliability.length === 0
                          ? "Observed frequencies will appear once the engine has at least 3 analogs with forward windows."
                          : `Bars = observed fraction of analogs at or below each predicted quantile. Dashed ticks mark the predicted value. Coverage P10→P90 is ${(trustMetrics.coverage * 100).toFixed(0)}% vs 80% target; drift is ${trustMetrics.regimeDrift}.`}
                      </div>
                    </div>
                    <div className="trust-panel__narrative">
                      {/* Grade explanation — thresholds are the source-of-
                          truth from `the-similarity-app/lib/data.ts
                          ::gradeFromMetrics`. If those thresholds change
                          there, they must change here too (or be lifted to
                          a shared const). Kept inline so the user can see
                          WHY the grade is what it is without leaving the
                          panel. */}
                      <div>
                        <h3>Grade &middot; {trustMetrics.grade}</h3>
                        <p className="trust-panel__grade-copy">
                          Composite letter grade from coverage gap, CRPS,
                          and hit rate.
                        </p>
                        <ul className="trust-panel__grade-list">
                          <li><b>A</b> · gap &le; 5%, CRPS &le; 0.05, hit &ge; 0.58</li>
                          <li><b>B</b> · gap &le; 10%, CRPS &le; 0.08, hit &ge; 0.54</li>
                          <li><b>C</b> · gap &le; 15%, CRPS &le; 0.12, hit &ge; 0.52</li>
                          <li><b>D / F</b> · anything looser</li>
                        </ul>
                        <p className="trust-panel__grade-current">
                          This query: gap {(Math.abs(trustMetrics.coverage - 0.80) * 100).toFixed(1)}% &middot; CRPS {trustMetrics.crps.toFixed(3)} &middot; hit {trustMetrics.hitRate.toFixed(2)}.
                        </p>
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
                  </div>
                )}
              </>
            );
          })()}
        </div>

        {/* Analog strip */}
        <div className="strip">
          {searching && analogs.length === 0 && (
            <div style={{ display: "flex", alignItems: "center", justifyContent: "center", width: "100%", padding: 32 }}>
              <span className="mono" style={{ fontSize: 12, color: "var(--ink-3)" }}>Searching for analogs...</span>
            </div>
          )}
          {!searching && analogs.length === 0 && loadedSeries.length > 0 && (
            // Search finished with no matches — give the user a concrete next step
            // instead of silently leaving the strip blank.
            <div className="ws-micro-empty ws-micro-empty--strip" role="status">
              <div className="ws-micro-empty__title">No analogs found</div>
              <div className="ws-micro-empty__body">
                Try widening the query window (pick a longer length chip), or drag
                the window to a different section of the timeline.
              </div>
            </div>
          )}
          {analogs.map((a, i) => {
            // `data-rank` drives the rank-indexed left-border color
            // defined in globals.css (.analog-card[data-rank="N"]).
            // `i` is 0-indexed over the display order, which matches
            // the chart overlay's rank index so card and chart line
            // share the same palette color.
            //
            // Click affordance split (PR #K):
            //   - Card body click    → open the analog detail drawer
            //   - Pin icon click     → toggle pin (existing behavior,
            //                           now scoped to just the icon)
            //   - Hover              → chart path preview (PR #231)
            //
            // The pin icon's onClick calls stopPropagation so the card's
            // click handler doesn't ALSO open the drawer when the user
            // clicks the icon. Without stopPropagation the user's "pin
            // only" intent would still open the drawer as a side effect.
            const isPinned = pinned.has(a.id);
            return (
              <div key={a.id} className="analog-card"
                data-rank={i}
                data-pinned={isPinned ? "true" : undefined}
                role="button"
                tabIndex={0}
                aria-label={`Open detail for analog ${a.rank}: ${a.label}`}
                onClick={() => setDetailAnalogId(a.id)}
                onKeyDown={(e) => {
                  // Keyboard activation for the card body. Only Enter
                  // and Space should trigger — arrow keys remain the
                  // user's normal focus-navigation chord. We avoid
                  // hijacking Space from input-like descendants by
                  // checking the event target — no inputs live in
                  // this card today, but future-proof the handler.
                  const target = e.target as HTMLElement;
                  const tag = target?.tagName;
                  if (tag === "INPUT" || tag === "TEXTAREA" || tag === "BUTTON") return;
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    setDetailAnalogId(a.id);
                  }
                }}
                onMouseEnter={() => setHoverAnalog(a.id)}
                onMouseLeave={() => setHoverAnalog(null)}>
                <div className="analog-card__head">
                  <span className="analog-card__date">#{a.rank} &middot; {fmtDateShort(a.date)}</span>
                  <div className="analog-card__head-right">
                    <span className="analog-card__score">{a.composite.toFixed(2)}</span>
                    <button
                      type="button"
                      className="analog-card__pin-btn"
                      data-pinned={isPinned ? "true" : undefined}
                      aria-pressed={isPinned}
                      aria-label={isPinned ? `Unpin analog ${a.rank}` : `Pin analog ${a.rank}`}
                      title={isPinned ? "Unpin this analog" : "Pin this analog"}
                      onClick={(e) => {
                        // Stop bubbling so the card's click (drawer open)
                        // doesn't fire. The pin icon is the ONLY affordance
                        // that toggles pin from the card strip now.
                        e.stopPropagation();
                        togglePin(a.id);
                      }}
                    >
                      <svg width="12" height="12" viewBox="0 0 16 16" aria-hidden="true" focusable="false">
                        {/* Simple pushpin glyph — head + body + tip. When
                            pinned we fill the whole glyph; when unpinned
                            we render the outline only. Path sized for a
                            12px box so it reads clearly in the card head. */}
                        <path
                          d="M9.5 1.5 L14.5 6.5 L11.5 7.5 L10.5 11.5 L8 9 L3.5 13.5 L2.5 12.5 L7 8 L4.5 5.5 L8.5 4.5 Z"
                          fill={isPinned ? "currentColor" : "none"}
                          stroke="currentColor"
                          strokeWidth="1.2"
                          strokeLinejoin="round"
                        />
                      </svg>
                    </button>
                  </div>
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
            );
          })}
        </div>
      </section>

      {/* Backdrop shown only when either drawer is open on midsize screens.
          Clicking it closes both drawers. On large screens the drawer CSS
          doesn't apply so the backdrop is hidden via display: none. */}
      <div
        className="ws-drawer-backdrop"
        onClick={() => { setRightDrawerOpen(false); setLeftDrawerOpen(false); }}
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

      {/* ── Analog detail drawer ─────────────────────────────────
          Slides in from the right when the user clicks a card body.
          Open state is driven by `detailAnalogId` — null = closed.
          The drawer itself is stateless beyond the controlled props. */}
      <AnalogDetailDrawer
        analog={detailAnalog}
        open={detailAnalog !== null}
        pinned={detailAnalog ? pinned.has(detailAnalog.id) : false}
        onClose={() => setDetailAnalogId(null)}
        onTogglePin={togglePin}
        onUseAsQuery={(analog) => {
          // Move the query window to the analog's [startIdx, priceWindow.length]
          // range. We DO NOT auto-fire search — the user must click Search so
          // the new window is visible first. `isDirty` already flips on the
          // windowState change (see derivation below) so the Search button
          // starts pulsing immediately.
          const newStart = Math.max(0, Math.min(N - 2, analog.startIdx));
          const newLen = Math.max(2, Math.min(N - newStart - 1, analog.priceWindow.length || 120));
          setWindowState({ start: newStart, len: newLen });
          // Also close the drawer so the chart is fully visible, and surface
          // a toast-style banner telling the user what just happened + how
          // to proceed. Banner clears itself after 8s so it doesn't linger
          // if the user ignores it; manual dismiss is also wired up.
          setDetailAnalogId(null);
          const label = `${fmtDate(analog.date)} → ${fmtDate(analog.endDate)}`;
          setUseAsQueryBanner(label);
          // Fire a custom event on window so other parts of the app (e.g.
          // a future analytics listener) can observe the "use as query"
          // intent without being coupled to this component.
          try {
            window.dispatchEvent(
              new CustomEvent("ts:use-analog-as-query", {
                detail: { analogId: analog.id, label },
              }),
            );
          } catch {
            // CustomEvent can throw in some sandboxed iframes — safe to ignore.
          }
        }}
      />

      {/* Transient "use as query" banner — appears when the user clicks
          "Find similar analogs" in the drawer. Self-clears after 8s or on
          manual dismiss. Positioned as a floating toast so it doesn't
          reflow the layout when it appears/disappears. */}
      {useAsQueryBanner !== null && (
        <UseAsQueryBanner
          label={useAsQueryBanner}
          onDismiss={() => setUseAsQueryBanner(null)}
        />
      )}
    </div>
  );
}

/**
 * Transient toast shown after "Find similar analogs" moves the query
 * window. Self-dismisses after 8 seconds — long enough for the PM to
 * read the sentence, short enough that it doesn't linger if ignored.
 *
 * Extracted as its own component purely so the setTimeout can live in
 * its own effect without polluting the Workstation component's already-
 * crowded hook list. The effect cleans up on unmount / prop change.
 */
function UseAsQueryBanner({
  label,
  onDismiss,
}: {
  label: string;
  onDismiss: () => void;
}) {
  useEffect(() => {
    const id = window.setTimeout(onDismiss, 8000);
    return () => window.clearTimeout(id);
  }, [onDismiss]);
  return (
    <div className="ws-use-as-query-banner" role="status" aria-live="polite">
      <span className="ws-use-as-query-banner__icon" aria-hidden="true">&#x1F4CD;</span>
      <span className="ws-use-as-query-banner__text">
        Query window moved to <strong>{label}</strong> &mdash; click Search to find new analogs.
      </span>
      <button
        type="button"
        className="ws-use-as-query-banner__dismiss"
        onClick={onDismiss}
        aria-label="Dismiss notice"
      >
        &times;
      </button>
    </div>
  );
}
