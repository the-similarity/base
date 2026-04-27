"use client";

/**
 * PrudentDemoPreview — the home-page tile for the Prudent surface.
 *
 * Replaces the static SVG mock that used to live inline in `app/page.tsx`
 * with the REAL `RhymePairCard` component from `/prudent/rhymes`, wrapped
 * in a lightweight `.prudent-root` shell so the component's CSS variables
 * resolve without the full Prudent layout.
 *
 * Mock data mirrors the curated pair on `/prudent-demo` (two deep U-shape
 * weeks, 86% shape match), so investors who click through from the home
 * tile to `/prudent-demo` see the exact same story they saw in the
 * preview — no surprise reveal, just a larger frame and more cards.
 *
 * Why a separate wrapper and not a direct import into page.tsx:
 *   - `RhymePairCard` depends on `--panel / --line / --ink / --serif / …`
 *     tokens that only exist inside `.prudent-root`. The home page uses
 *     a different scope (warm paper + oxblood), so we must open a
 *     scoped style island here or the card renders with missing colors.
 *   - The home page also sits under `body { overflow: hidden }`, which
 *     fights the real prudent-root's `height:100vh; overflow-y:auto`.
 *     This preview drops those two rules: the home tile is the scroll
 *     parent, and the preview just needs to occupy its fixed slot.
 */

import { RhymePairCard } from "../../app/prudent/rhymes/page";
import type { HistoryDay } from "../../app/prudent/engine";

/* ── Mock history — two matched U-shape weeks ────────────────────────
 *
 * Time-ascending array (oldest first) so pair indices map directly to
 * `history.slice(pair.a, pair.a + 7)`. The card reads `week[3].text` for
 * its dominant-theme tag and `week[0..6].avg` for the mini-sparkline, so
 * those are the only fields that matter for a preview render.
 *
 * Windows (0..6 and 14..20) trace near-identical arcs:
 *   70 → 55 → 40 → 25 → 40 → 58 → 72  (Window A — oldest)
 *   72 → 58 → 40 → 28 → 42 → 60 → 74  (Window B — recent)
 * A 14-day buffer of calm days (avg 56..63) between them prevents the
 * real findTopRhymes sweep from selecting an overlapping pair.
 */
const DEMO_HISTORY: HistoryDay[] = [
  // Window A — days 34..28 (oldest first after reversal)
  { day: 34, avg: 70, text: "Woke early, read on the balcony, felt lucky." },
  { day: 33, avg: 55, text: "Decent start, the afternoon slipped away." },
  { day: 32, avg: 40, text: "Headachy, scattered. Nothing stuck." },
  { day: 31, avg: 25, text: "The deadline pushed. I dreaded the morning and it showed." },
  { day: 30, avg: 40, text: "Started to recover. Went for a long evening walk." },
  { day: 29, avg: 58, text: "Worked out, then drinks. Good talk." },
  { day: 28, avg: 72, text: "Everything resolved in one email thread. Relief." },

  // Buffer — flat days between the two windows
  { day: 27, avg: 63, text: "Saw an old professor. He remembered my thesis." },
  { day: 26, avg: 55, text: "Slow day. Took a long nap." },
  { day: 25, avg: 59, text: "A lot of emails but nothing urgent." },
  { day: 24, avg: 61, text: "Picked up tomatoes at the market. Made soup." },
  { day: 23, avg: 64, text: "Went skating, first time in years. Fell twice, laughed." },
  { day: 22, avg: 60, text: "Finished a book I've been putting off." },
  { day: 21, avg: 58, text: "Reading, cooking, quiet call with my sister." },

  // Window B — days 20..14
  { day: 20, avg: 72, text: "Slept nine hours, felt gentle and slow all morning." },
  { day: 19, avg: 58, text: "Nice breakfast, then the day stalled mid-afternoon." },
  { day: 18, avg: 42, text: "Tired and wired. Couldn't focus, couldn't rest." },
  { day: 17, avg: 28, text: "A bruising morning meeting — the feedback was hard but fair." },
  { day: 16, avg: 42, text: "Paced around, then wrote for three hours straight." },
  { day: 15, avg: 60, text: "Better sleep, better day — presented and it landed." },
  { day: 14, avg: 74, text: "Finally broke through on the spec. Champagne-worthy." },
];

export function PrudentDemoPreview() {
  return (
    <div className="prudent-root prudent-preview-scope">
      <style>{PRUDENT_PREVIEW_CSS}</style>
      <div className="prudent-preview-header">
        <span className="prudent-preview-eyebrow">Strongest rhyme</span>
        <span className="prudent-preview-sub">86% shape match · RMSE 0.22</span>
      </div>
      <RhymePairCard
        pair={{ a: 0, b: 14, score: -0.22 }}
        history={DEMO_HISTORY}
      />
    </div>
  );
}

/*
 * Scoped CSS for the preview. A trimmed subset of the full prudent root
 * style block — just the variables and utility classes `RhymePairCard`
 * and its children (`PairSide`, `MiniSparkline`, `dominantTheme`) need.
 *
 * Crucially we DROP the `height: 100vh; overflow-y: auto` rule that the
 * real layout carries, because this preview lives inside the home page's
 * scroll container and would otherwise create a nested scroll well.
 *
 * Dark-mode hookup: the real prudent layout swaps palette via a
 * `.prudent-root.prudent-dark` class it manages internally. This preview
 * lives on the home page, whose theme toggle sets `data-theme="dark"` on
 * `<html>`. We bridge the two by selecting
 *   html[data-theme="dark"] .prudent-preview-scope
 * and overriding the palette with the dark tokens lifted verbatim from
 * `.prudent-root.prudent-dark`. Without this the tile stays blazing
 * white when the rest of the page flips to dark — a literal flashbang.
 *
 * The `.prudent-preview-scope` selector is used to pin those overrides
 * so they can't accidentally hit any `.prudent-root` that shows up
 * elsewhere on the same page.
 */
const PRUDENT_PREVIEW_CSS = `
  .prudent-preview-scope {
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
    --green: #16A34A;
    --mono: 'JetBrains Mono', 'SF Mono', Consolas, monospace;
    --serif: 'Newsreader', Georgia, serif;
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    background: var(--app-bg);
    color: var(--text);
    -webkit-font-smoothing: antialiased;
    /* No height or overflow — the home-page tile handles scroll. */
    border-radius: var(--radius-md, 6px);
    padding: 16px 18px;
  }
  /* Dark-mode palette — values lifted from .prudent-root.prudent-dark
     in app/prudent/layout.tsx. The toggle in app/page.tsx sets
     data-theme="dark" on <html>; this selector inherits that. */
  [data-theme="dark"] .prudent-preview-scope {
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
    --green: #22C55E;
  }
  /* Nested card contrast: in dark mode the inner card background
     (var --app-bg, #0E0F11) sits against the preview panel surface
     (var --panel, #17191C) at almost the same lightness, making
     the inner card invisible. Mirror the real prudent page fix and
     lift the nested card to var --hover for separation. */
  [data-theme="dark"] .prudent-preview-scope .rhyme-pair-card {
    background: var(--hover) !important;
    border-color: var(--line-mid) !important;
  }
  .prudent-preview-scope *,
  .prudent-preview-scope *::before,
  .prudent-preview-scope *::after {
    box-sizing: border-box;
  }
  .prudent-preview-scope .mono { font-family: var(--mono); }
  .prudent-preview-scope .serif { font-family: var(--serif); }
  .prudent-preview-scope .tnum { font-variant-numeric: tabular-nums; }

  /* Preview-specific header above the reused card. Keeps the tile from
     feeling like a raw card drop — mirrors the mini chart-card header
     on the Workstation preview next door. */
  .prudent-preview-scope .prudent-preview-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 12px;
    padding: 0 2px;
  }
  .prudent-preview-scope .prudent-preview-eyebrow {
    font-family: var(--mono);
    font-size: 10.5px;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    color: var(--muted);
    font-weight: 600;
  }
  .prudent-preview-scope .prudent-preview-sub {
    font-family: var(--mono);
    font-size: 10.5px;
    color: var(--muted);
  }

  /* Responsive fallback copied from the real /prudent/rhymes page —
     at narrow widths the 3-col rhyme card stacks A / center / B so it
     still reads inside the home tile on small viewports. */
  @media (max-width: 560px) {
    .prudent-preview-scope .rhyme-pair-card {
      grid-template-columns: 1fr !important;
      text-align: left !important;
    }
    .prudent-preview-scope .rhyme-pair-center {
      flex-direction: row !important;
      justify-content: space-between;
      width: 100%;
    }
  }
`;
