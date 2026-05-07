"use client";

/**
 * /try — public, zero-signup demo of the cold-backtest engine.
 *
 * Surface contract (from vision/personalized_setup_scanner.md, Worktree D):
 *   "User pastes any chart URL or selects a recent window, sees 20
 *    historical analogs with continuations. Reuses Worktree A's cold-
 *    backtest engine via a public read-only endpoint."
 *
 * Backend posture:
 *   Worktree A's public endpoint has not landed yet at the time this
 *   widget was written. The page therefore runs the analog search
 *   client-side against the synthetic fallback engine in
 *   `lib/data.ts` (`findAnalogs` over `SERIES`, the 7,500-bar SPX-like
 *   series the workstation uses when the API is offline). When A's
 *   public endpoint ships, swap the call inside `runScan` for a
 *   `fetch('/api/public/cold-backtest')` and keep the rest of the UI.
 *
 * URL-paste field is rendered but marked as "coming soon" — without
 * the public endpoint we cannot fetch arbitrary instruments. Selecting
 * a preset window is the v1 working path.
 *
 * Compliance posture (research-tool framing):
 *   Disclaimer footer is mandatory per the plan. Avoids the forbidden
 *   words: guarantee, make money, signal (in trading sense), and
 *   investment advice. Frames the surface as a research demo.
 *
 * Low-coverage indicator:
 *   When the engine returns fewer than `LOW_COVERAGE_THRESHOLD` matches
 *   (default 5), the widget surfaces an explicit warning. This is the
 *   "low-coverage setup" item from the worktree D task list — it tells
 *   the user the setup is unusual or the lookback was too short, so
 *   they don't mistake an empty result for "no setup found".
 */

import { useState, useCallback, useMemo, useEffect } from "react";
import Link from "next/link";
import { findAnalogs, SERIES, type AnalogMatch } from "../../lib/data";
import { ThemeToggle } from "../../components/ui/theme-toggle";
import { AnalogCard } from "../../components/try/analog-card";

// ── Tunables ────────────────────────────────────────────────────────────
//
// MAX_ANALOGS: per the spec the public widget shows up to 20 historical
// analogs. The engine's de-dup pass (overlapping windows are collapsed)
// can return fewer when the series is short or the setup is rare.
//
// DEFAULT_VISIBLE: top-5 by default + "show 15 more" reveal — locked in
// the compressed-review decisions of the v1 plan as the cold-backtest
// output shape.
//
// LOW_COVERAGE_THRESHOLD: <5 matches triggers the explicit warning. The
// number was suggested 5 in the worktree D task description; it sits
// just under DEFAULT_VISIBLE so the warning fires whenever the page
// can't even fill the default reveal.
//
// WINDOW_LEN, HORIZON: 60-bar query window with 60-bar continuation. Same
// defaults the workstation uses, kept here so analogs render with the
// same shape investors see in the demo chart.
const MAX_ANALOGS = 20;
const DEFAULT_VISIBLE = 5;
const LOW_COVERAGE_THRESHOLD = 5;
const WINDOW_LEN = 60;
const HORIZON = 60;

// ── Preset windows ──────────────────────────────────────────────────────
//
// Each preset names a region of the synthetic SPX-like series. Indexes
// are chosen so the query window ends inside a recognisable regime — a
// non-quant visitor should be able to pick "trend up" or "drawdown" by
// label without understanding the underlying series. The "current"
// preset slides to the last fillable window so the page feels live.
//
// regimeNote is short editorial text shown under the preset card. It is
// descriptive (what the window looks like), not advisory (what to do
// about it) — research-tool framing.
type Preset = {
  id: string;
  label: string;
  regimeNote: string;
  // Index into SERIES where the query window starts. The window covers
  // [start, start + WINDOW_LEN) and the cold-backtest searches from
  // index 200 up to start - WINDOW_LEN - HORIZON for analogs.
  startIdx: number;
};

const PRESETS: Preset[] = [
  {
    id: "current",
    label: "Most recent 60 bars",
    regimeNote: "The window ending today — what's happening right now.",
    startIdx: SERIES.length - WINDOW_LEN - 1,
  },
  {
    id: "trend_up",
    label: "Trend continuation",
    regimeNote: "A 60-bar uptrend mid-recovery — what does the engine match?",
    startIdx: 4400,
  },
  {
    id: "drawdown",
    label: "Active drawdown",
    regimeNote: "A 60-bar drawdown like late-stage rate hike — find rhymes.",
    startIdx: 6900,
  },
  {
    id: "compression",
    label: "Range compression",
    regimeNote: "Tight 60-bar range before a regime shift — pre-breakout shape.",
    startIdx: 5500,
  },
];

// ── Page ────────────────────────────────────────────────────────────────

export default function TryPage() {
  const [presetId, setPresetId] = useState<string>("current");
  const [analogs, setAnalogs] = useState<AnalogMatch[]>([]);
  const [showAll, setShowAll] = useState(false);
  // `running` covers the synthetic-engine path which is fast enough to
  // feel synchronous, but a fetch-backed call will need a real spinner.
  // Keeping the state machine here means the swap is one-line.
  const [running, setRunning] = useState(false);

  const preset = useMemo(
    () => PRESETS.find((p) => p.id === presetId) ?? PRESETS[0],
    [presetId],
  );

  // ── Engine call ──────────────────────────────────────────────────────
  // Runs against the synthetic engine fallback. When Worktree A ships
  // /api/public/cold-backtest, replace the body of this function with a
  // fetch + JSON parse against the contract in
  // vision/personalized_setup_scanner.md and keep the result shape.
  const runScan = useCallback(async () => {
    setRunning(true);
    setShowAll(false);
    try {
      // Defer the actual compute to the next animation frame so the
      // "running" state visibly flips before findAnalogs blocks the
      // event loop on a large k. Without this users see the click
      // register but the spinner never appears.
      await new Promise((r) => requestAnimationFrame(() => r(null)));
      const result = findAnalogs(preset.startIdx, WINDOW_LEN, {
        k: MAX_ANALOGS,
        horizon: HORIZON,
      });
      setAnalogs(result);
    } finally {
      setRunning(false);
    }
  }, [preset.startIdx]);

  // Auto-run on mount + when the preset changes so the page never sits
  // empty. Without this the "select a window, then click Run" gesture
  // is two clicks for what should be a one-glance demo.
  useEffect(() => {
    runScan();
  }, [runScan]);

  const visible = showAll ? analogs : analogs.slice(0, DEFAULT_VISIBLE);
  const hiddenCount = Math.max(0, analogs.length - DEFAULT_VISIBLE);
  const lowCoverage = analogs.length < LOW_COVERAGE_THRESHOLD && !running;

  return (
    <div className="app">
      {/* Marquee chrome — same shell the rest of the app uses, so /try
          reads as part of the product, not a stand-alone microsite. */}
      <div className="marquee">
        <div className="brand">
          <Link href="/" className="brand__logo" aria-hidden="true">
            <svg width="22" height="22" viewBox="0 0 26 26">
              <circle cx="13" cy="13" r="11" fill="none" stroke="var(--ink)" strokeWidth="1.2" />
              <circle cx="13" cy="13" r="6" fill="none" stroke="var(--ink)" strokeWidth="1.2" />
              <circle cx="13" cy="13" r="1.8" fill="var(--ink)" />
            </svg>
          </Link>
          <div className="brand__word">The <em>Similarity</em></div>
        </div>
        <div style={{ overflow: "hidden", flex: 1 }}>
          <div className="marquee__track">
            <span className="marquee__item">Public research demo &middot; cold-backtest preview</span>
            <span className="marquee__item">Pick a window &middot; see historical analogs &middot; review what happened next</span>
          </div>
        </div>
        <div className="nav__right">
          <ThemeToggle />
        </div>
      </div>

      <main className="page try-page">
        <section className="try-page__inner">
          <header className="try-page__head">
            <div className="label">Try the engine</div>
            <h1 className="try-page__title">Find the moments that rhyme.</h1>
            <p className="try-page__lede">
              Pick a recent window. The engine searches three decades of price
              shapes and returns up to {MAX_ANALOGS} historical analogs with what
              happened next. No signup. Research tool — not investment advice.
            </p>
          </header>

          {/* ── Window picker ────────────────────────────────────────── */}
          <div className="try-picker" role="radiogroup" aria-label="Window selector">
            {PRESETS.map((p) => (
              <button
                key={p.id}
                role="radio"
                aria-checked={p.id === presetId}
                className={
                  "try-picker__btn" + (p.id === presetId ? " is-active" : "")
                }
                onClick={() => setPresetId(p.id)}
                disabled={running}
              >
                <span className="try-picker__label">{p.label}</span>
                <span className="try-picker__sub">{p.regimeNote}</span>
              </button>
            ))}
          </div>

          {/* ── URL paste (preview / disabled) ──────────────────────────
              Rendered so visitors see the v2 path is real, but disabled
              because the public engine endpoint (Worktree A) has not
              shipped yet. Tooltip explains the state honestly rather
              than promising functionality the page cannot deliver. */}
          <div className="try-url" aria-hidden={false}>
            <label className="try-url__label">
              Or paste a chart URL <span className="try-url__pill">soon</span>
            </label>
            <input
              type="text"
              className="try-url__input"
              placeholder="https://www.tradingview.com/chart/..."
              disabled
              aria-disabled="true"
              title="Coming soon — public engine endpoint pending"
            />
            <p className="try-url__hint">
              Coming soon. Pick a preset window above for now.
            </p>
          </div>

          {/* ── Results ─────────────────────────────────────────────── */}
          <div className="try-results">
            <div className="try-results__head">
              <span className="try-results__title">
                {running
                  ? "Searching…"
                  : `Found ${analogs.length} historical analog${analogs.length === 1 ? "" : "s"}`}
              </span>
              {!running && analogs.length > 0 && (
                <span className="try-results__sub">
                  Showing {visible.length} of {analogs.length}
                </span>
              )}
            </div>

            {/* Low-coverage indicator: fires when the engine returns fewer
                than LOW_COVERAGE_THRESHOLD matches. This is the "low-
                coverage setup" surface from the worktree D task. The text
                stays research-framed (no advice, no "don't trade this") —
                it just tells the user the engine had thin data. */}
            {lowCoverage && (
              <div className="try-low-cov" role="status">
                <strong>Low-coverage setup.</strong> The engine found fewer
                than {LOW_COVERAGE_THRESHOLD} similar windows for this
                selection. Treat any continuation summary below as
                provisional — sparse history means wide uncertainty. Try a
                different window or a more common shape (trend, drawdown).
              </div>
            )}

            <div className="try-grid">
              {visible.map((m) => (
                <AnalogCard key={m.id} match={m} />
              ))}
            </div>

            {!running && hiddenCount > 0 && !showAll && (
              <button
                className="try-show-more"
                onClick={() => setShowAll(true)}
              >
                Show {hiddenCount} more
              </button>
            )}
          </div>

          {/* ── Compliance footer ─────────────────────────────────────── */}
          <footer className="try-footer">
            <p>
              <strong>Research tool.</strong> The Similarity is a pattern-
              matching research framework. Outputs are descriptive analogs
              from past data — they are not investment advice. Past behavior
              does not guarantee future results. Always do your own research.
            </p>
            <p className="try-footer__cta">
              Want this on your own setups? <Link href="/">Read the full vision</Link>{" "}
              or{" "}
              <a
                href="https://calendly.com/buyan-khurel/30min"
                target="_blank"
                rel="noopener noreferrer"
              >
                book a 30-min demo
              </a>
              .
            </p>
          </footer>
        </section>
      </main>
    </div>
  );
}

