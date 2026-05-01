"use client";

/**
 * AnalogDetailDrawer — right-side slide-in inspector for a single analog.
 *
 * Lifecycle:
 *   - Renders as a fixed-position element at the edge of the viewport. The
 *     host component (`Workstation`) keeps state `detailAnalogId` and flips
 *     this component's `open` prop on/off. We ALWAYS mount the drawer
 *     (even when closed) so the slide-out transition plays cleanly — only
 *     the `translateX` changes, the node stays in the DOM.
 *   - When `analog` is null the body renders an empty shell. Practically
 *     this only flashes for one frame when the drawer is closing (host
 *     sets `detailAnalogId = null`, which makes `analog = null`, which
 *     makes `open = false` on the next render). We guard with a local
 *     `lastAnalog` ref in the host so the closing transition reads stable
 *     content — but the drawer itself is defensive about null.
 *
 * Accessibility:
 *   - `role="dialog"` + `aria-modal={false}` because the chart behind
 *     remains interactive (by design — the PM can still hover price
 *     while reading the breakdown).
 *   - ESC handling lives in the host (Workstation) because it shares a
 *     keyboard map with Search and jump chords; routing it through the
 *     host avoids fighting for the keydown listener.
 *
 * Styling:
 *   - All classes prefixed `.adrawer__` and gated on `[data-open]`. Rules
 *     live at the bottom of `app/globals.css` (see task spec).
 */

import { useEffect, useState } from "react";

import type { AnalogMatch, LensScores } from "../../lib/data";
import { LENS_DEFS, fmtDate, fmtPct } from "../../lib/data";
import type { GoodrunLabel } from "../../lib/goodruns";
import { Sparkline } from "./sparkline";

export interface AnalogDetailDrawerProps {
  /** The analog to inspect. Null when nothing is selected. */
  analog: AnalogMatch | null;
  /** Whether the drawer is visible (drives the slide-in transform). */
  open: boolean;
  /** Whether the analog is currently pinned (drives the toggle label). */
  pinned: boolean;
  /** Close the drawer without changing pin state. */
  onClose: () => void;
  /** Toggle pin on the analog being inspected. */
  onTogglePin: (id: string) => void;
  /**
   * User clicked "Find similar analogs" — ask the host to move the query
   * window to this analog's [startIdx, startIdx+priceWindow.length] range.
   * The host is responsible for dispatching the custom event and setting
   * `windowState`. We DO NOT fire the search here — user must click Search
   * explicitly so the new query window is visible first.
   */
  onUseAsQuery: (analog: AnalogMatch) => void;
  /**
   * Persist this analog as a "goodrun" — the host writes a row to the
   * backend ``/goodruns`` surface carrying the query window, the match
   * window, and the raw engine score breakdown (math names). Optional:
   * when omitted the Save button is hidden. When present but the
   * analog has no ``scoreBreakdown`` (synthetic / offline fallback),
   * the button renders disabled with a tooltip explaining why. The
   * state machine for the button (idle / saving / saved / error) lives
   * in the drawer because it's UI-local.
   */
  onSaveGoodrun?: (analog: AnalogMatch, label: GoodrunLabel) => Promise<void>;
}

type SaveState = "idle" | "saving" | "saved" | "error";

const GOODRUN_SAVE_OPTIONS: { label: GoodrunLabel; text: string }[] = [
  { label: "goodrun", text: "Save to goodrun" },
  { label: "almost_good", text: "Save almost good" },
  { label: "badrun", text: "Save badrun" },
];

function initialSaveStates(): Record<GoodrunLabel, SaveState> {
  return {
    goodrun: "idle",
    almost_good: "idle",
    badrun: "idle",
  };
}

/**
 * Known regime lookup for the context strip.
 *
 * Hand-curated — 5-10 entries is plenty. Each entry has a [start, end] date
 * pair and a short label. If the analog's start date falls inside any of
 * these windows, we surface the label; otherwise we fall back to
 * "Q{1..4} {year}". This is deliberately not exhaustive — the intent is to
 * tell the user "you've seen this movie before" for the most famous
 * episodes, not to encyclopedically classify every quarter.
 *
 * Dates are inclusive [start, end]. Ordering is newest-first because the
 * `find()` below short-circuits on first match, and the most recent
 * regimes are the most frequently-surfaced in analog results.
 */
const KNOWN_REGIMES: { start: string; end: string; label: string }[] = [
  { start: "2023-03-01", end: "2023-06-30", label: "2023 · regional bank stress" },
  { start: "2022-01-01", end: "2022-12-31", label: "2022 · inflation / rate-hike shock" },
  { start: "2020-02-15", end: "2020-05-31", label: "COVID crash + recovery" },
  { start: "2018-10-01", end: "2018-12-31", label: "Q4 2018 · rate-panic selloff" },
  { start: "2015-08-01", end: "2016-02-29", label: "2015-16 · China devaluation / oil bust" },
  { start: "2011-08-01", end: "2011-10-31", label: "2011 · US debt ceiling + EU crisis" },
  { start: "2008-09-01", end: "2009-03-31", label: "2008-09 · Global Financial Crisis" },
  { start: "2001-03-01", end: "2002-10-31", label: "2001-02 · Dotcom bust" },
  { start: "1998-07-01", end: "1998-10-31", label: "1998 · Russia / LTCM" },
];

/**
 * Derive a regime label for a date.
 *
 * 1. If it falls inside any KNOWN_REGIMES window, use that label.
 * 2. Otherwise render "Q{1..4} {year}" so the user still gets temporal
 *    anchoring. We deliberately do NOT try to auto-classify off-list
 *    regimes — that's a rabbit hole of drift detection. Returns ""
 *    when the date is invalid so the caller can skip rendering.
 */
export function regimeLabelFor(date: Date): string {
  if (!(date instanceof Date) || Number.isNaN(date.getTime())) return "";
  const iso = date.toISOString().slice(0, 10);
  for (const r of KNOWN_REGIMES) {
    if (iso >= r.start && iso <= r.end) return r.label;
  }
  // Fallback: quarter + year.
  const month = date.getUTCMonth(); // 0..11
  const q = Math.floor(month / 3) + 1;
  return `Q${q} ${date.getUTCFullYear()}`;
}

/**
 * Compute lens ranks so the top-3 lenses (for THIS analog) can be colored
 * in the analog's rank palette while the remaining 6 stay muted.
 *
 * Returns a Set of lens keys that are in the top 3 by score (ties broken
 * by LENS_DEFS order — stable so the UI doesn't flicker under re-renders).
 */
function topLensKeys(lenses: LensScores): Set<string> {
  const pairs = LENS_DEFS.map(d => ({
    key: d.key,
    score: (lenses as unknown as Record<string, number>)[d.key] ?? 0,
  }));
  pairs.sort((a, b) => b.score - a.score);
  return new Set(pairs.slice(0, 3).map(p => p.key));
}

export function AnalogDetailDrawer({
  analog,
  open,
  pinned,
  onClose,
  onTogglePin,
  onUseAsQuery,
  onSaveGoodrun,
}: AnalogDetailDrawerProps) {
  /*
   * Save-to-goodrun button state machine.
   *
   * States:
   *   - "idle"    : default; click triggers the save
   *   - "saving"  : awaiting the POST; button disabled to prevent
   *                 double-submit if the user mashes the button
   *   - "saved"   : success; label flips to "Saved ✓" for ~2s then returns
   *                 to idle (visual feedback without a toast dependency)
   *   - "error"   : most recent save failed; label shows "Retry — <msg>".
   *                 Next click retries; no automatic reset
   *
   * Resets to "idle" whenever the selected analog changes so a previous
   * save's success/error state doesn't bleed across different matches.
   * Also resets when the drawer closes — re-opening should not show a
   * stale "Saved ✓" that no longer corresponds to a visible save action.
   */
  const [saveStates, setSaveStates] = useState<Record<GoodrunLabel, SaveState>>(initialSaveStates);
  const [saveErrors, setSaveErrors] = useState<Partial<Record<GoodrunLabel, string>>>({});

  useEffect(() => {
    setSaveStates(initialSaveStates());
    setSaveErrors({});
  }, [analog?.id, open]);

  useEffect(() => {
    const savedLabels = GOODRUN_SAVE_OPTIONS
      .filter(option => saveStates[option.label] === "saved")
      .map(option => option.label);
    if (!savedLabels.length) return;
    const handle = window.setTimeout(() => {
      setSaveStates(prev => {
        const next = { ...prev };
        for (const label of savedLabels) {
          if (next[label] === "saved") next[label] = "idle";
        }
        return next;
      });
    }, 2000);
    return () => window.clearTimeout(handle);
  }, [saveStates]);

  const hasBreakdown = analog?.scoreBreakdown != null;
  // Hide the save action entirely when the host didn't pass a handler.
  // That way tests and non-workstation mounts of the drawer (if any)
  // don't have a no-op button littering the footer.
  const canShowSave = typeof onSaveGoodrun === "function";
  function saveDisabled(label: GoodrunLabel) {
    const state = saveStates[label];
    return !analog || !hasBreakdown || state === "saving" || state === "saved";
  }

  async function handleSave(label: GoodrunLabel) {
    if (!analog || !onSaveGoodrun) return;
    setSaveStates(prev => ({ ...prev, [label]: "saving" }));
    setSaveErrors(prev => ({ ...prev, [label]: undefined }));
    try {
      await onSaveGoodrun(analog, label);
      setSaveStates(prev => ({ ...prev, [label]: "saved" }));
    } catch (err) {
      setSaveStates(prev => ({ ...prev, [label]: "error" }));
      setSaveErrors(prev => ({ ...prev, [label]: err instanceof Error ? err.message : "save failed" }));
    }
  }

  function saveButtonText(label: GoodrunLabel, text: string) {
    const state = saveStates[label];
    if (state === "saving") return "Saving...";
    if (state === "saved") return "Saved";
    if (state === "error") return "Retry save";
    return text;
  }

  function saveTitle(label: GoodrunLabel) {
    if (!hasBreakdown) {
      // Explain why the button is inert — a synthetic/offline analog has
      // no engine math-name breakdown to persist, which is the whole
      // point of the feature. Saving would write null lenses and
      // defeat the purpose.
      return "Save requires the live API — synthetic analogs have no engine score breakdown.";
    }
    if (saveStates[label] === "error" && saveErrors[label]) return `Last attempt failed: ${saveErrors[label]}`;
    return `Persist this match as ${label} with its raw engine score breakdown.`;
  }
  // Rank 0..5 → palette color. We clamp to 0..5 because the multi-analog
  // palette only defines six slots (--c-analog-1..6); ranks above that
  // fall back to the strong ink color via the CSS rule.
  const rankIndex = analog ? Math.max(0, Math.min(5, (analog.rank ?? 1) - 1)) : 0;

  const topLenses = analog ? topLensKeys(analog.lenses) : new Set<string>();

  // Full-resolution sparklines: the match window, the forward window, and
  // the combined series used to render one continuous line. We clamp the
  // forward slice to 240 bars so extremely long horizons don't make the
  // sparkline unreadable. Everything falls back to [] when `analog` is
  // null so the closing transition doesn't crash on a partial render.
  const matchValues = analog?.priceWindow ?? [];
  const afterRaw = analog?.after ?? [];
  const afterValues = afterRaw.slice(0, 240);
  const combined = [...matchValues, ...afterValues];

  return (
    <aside
      className="adrawer"
      data-open={open ? "true" : "false"}
      role="dialog"
      aria-modal={false}
      aria-label="Analog detail"
      aria-hidden={!open}
    >
      <header className="adrawer__head">
        <div className="adrawer__rank-badge" data-rank={rankIndex}>
          #{analog?.rank ?? "—"}
        </div>
        <div className="adrawer__head-meta">
          <div className="adrawer__date-range">
            {analog
              ? `${fmtDate(analog.date)} → ${fmtDate(analog.endDate)}`
              : "—"}
          </div>
          <div className="adrawer__label serif">{analog?.label ?? ""}</div>
        </div>
        <div className="adrawer__composite">
          <span className="adrawer__composite-v">
            {analog ? analog.composite.toFixed(2) : "—"}
          </span>
          <span className="adrawer__composite-k">composite</span>
        </div>
        <button
          type="button"
          className="adrawer__pin-toggle"
          onClick={() => { if (analog) onTogglePin(analog.id); }}
          aria-pressed={pinned}
          // Accessible name differs from the footer action button so
          // role-and-name queries can unambiguously target one or the
          // other. The footer carries the canonical "Pin this analog";
          // the header is the quick toggle.
          aria-label={pinned ? "Unpin (header toggle)" : "Pin (header toggle)"}
          disabled={!analog}
        >
          {pinned ? "Unpin" : "Pin"}
        </button>
        <button
          type="button"
          className="adrawer__close"
          onClick={onClose}
          aria-label="Close analog detail drawer"
        >
          &times;
        </button>
      </header>

      {/* Context strip — one sentence on WHAT was happening back then. */}
      {analog && (
        <div className="adrawer__context">
          <span className="adrawer__context-icon" aria-hidden="true">&#x1F4CD;</span>
          <span className="adrawer__context-text">
            {regimeLabelFor(analog.date) || "Historical window"}
          </span>
        </div>
      )}

      {/* Per-lens score bars — 9 rows, one per lens, top-3 colored. */}
      {analog && (
        <section className="adrawer__section" aria-labelledby="adrawer-lens-h">
          <h3 id="adrawer-lens-h" className="adrawer__h">
            Lens breakdown
            <span className="adrawer__h-sub">score 0 → 1</span>
          </h3>
          <div className="adrawer__lens-list">
            {LENS_DEFS.map(def => {
              const score = (analog.lenses as unknown as Record<string, number>)[def.key] ?? 0;
              const isTop = topLenses.has(def.key);
              // Clamp for the width calculation but show the raw value
              // in the numeric label — same convention as the chart.
              const pct = Math.max(0, Math.min(1, score)) * 100;
              return (
                <div
                  key={def.key}
                  className="adrawer__lens-row"
                  data-top={isTop ? "true" : "false"}
                  data-rank={rankIndex}
                >
                  <span className="adrawer__lens-name">{def.name}</span>
                  <span className="adrawer__lens-bar">
                    <span
                      className="adrawer__lens-bar-fill"
                      style={{ width: `${pct}%` }}
                    />
                  </span>
                  <span className="adrawer__lens-score mono">
                    {score.toFixed(2)}
                  </span>
                </div>
              );
            })}
          </div>
        </section>
      )}

      {/* Expanded sparklines — match window + forward window side-by-side. */}
      {analog && combined.length > 2 && (
        <section className="adrawer__section" aria-labelledby="adrawer-spark-h">
          <h3 id="adrawer-spark-h" className="adrawer__h">
            Path
            <span className="adrawer__h-sub">
              match · {matchValues.length}d
              {afterValues.length > 0 ? ` → +${afterValues.length}d` : ""}
            </span>
          </h3>
          <div className="adrawer__spark-wrap">
            <Sparkline
              values={combined}
              width={380}
              height={80}
              // `highlight` is the fraction of the RIGHT side that is the
              // "after" region; the Sparkline draws a dashed divider at
              // the split so users can see match-vs-forward without two
              // separate SVGs. When there's no forward data we pass 0 so
              // no divider renders.
              highlight={combined.length > 0 ? afterValues.length / combined.length : 0}
            />
          </div>
          <div className="adrawer__spark-meta mono">
            <span>match end: {matchValues[matchValues.length - 1]?.toFixed(2) ?? "—"}</span>
            {afterValues.length > 0 && (
              <span
                className={
                  analog.afterReturn >= 0
                    ? "adrawer__spark-ret pos"
                    : "adrawer__spark-ret neg"
                }
              >
                +{afterValues.length}d: {fmtPct(analog.afterReturn)}
              </span>
            )}
          </div>
        </section>
      )}

      {/* Action row — pin/unpin, find-similar, save-to-goodrun, close. */}
      <footer className="adrawer__actions">
        <button
          type="button"
          className="adrawer__action adrawer__action--primary"
          onClick={() => { if (analog) onTogglePin(analog.id); }}
          disabled={!analog}
        >
          {pinned ? "Unpin this analog" : "Pin this analog"}
        </button>
        <button
          type="button"
          className="adrawer__action"
          onClick={() => { if (analog) onUseAsQuery(analog); }}
          disabled={!analog}
          title="Move the query window to this analog's date range (doesn't run search automatically)"
        >
          Find similar analogs
        </button>
        {canShowSave && GOODRUN_SAVE_OPTIONS.map(option => (
          <button
            key={option.label}
            type="button"
            className="adrawer__action"
            onClick={() => handleSave(option.label)}
            disabled={saveDisabled(option.label)}
            data-state={saveStates[option.label]}
            title={saveTitle(option.label)}
          >
            {saveButtonText(option.label, option.text)}
          </button>
        ))}
        <button
          type="button"
          className="adrawer__action adrawer__action--ghost"
          onClick={onClose}
        >
          Close
        </button>
      </footer>
    </aside>
  );
}
