/**
 * Static catalogue of generated HTML reports that live under
 * `public/reports/`. Server-rendered on the Reports page. Each entry
 * corresponds to a file copied from the `vision/` directory at the
 * repo root.
 *
 * Invariants:
 *   - `file` MUST match a file path under `public/reports/` (resolved by
 *     the Next.js static asset pipeline at `/reports/<file>`).
 *   - `date` is the human-facing publication date shown in the feed;
 *     format `YYYY-MM-DD`.
 *   - Order of this array defines the display order on the page. Newest
 *     first — append new entries at the **top** of the array.
 */

export type ReportEntry = {
  id: string;
  title: string;
  summary: string;
  file: string;
  date: string;
  kind: "pitch" | "findings" | "research";
  tag: string;
};

export const REPORTS: ReportEntry[] = [
  {
    id: "findings-414",
    title: "Phase 1 Findings — April 14",
    summary:
      "Three parallel tracks, three real signals. Adaptive conformal wins 14% CRPS. Tier 2 retrieval is a 37× runtime sink with no CRPS win. Decision layer shipped as opt-in modules.",
    file: "findings_deck_414.html",
    date: "2026-04-14",
    kind: "findings",
    tag: "Phase 1",
  },
  {
    id: "pitch-414",
    title: "Pitch Deck — April 14",
    summary:
      "Engine-first thesis, finance-as-proving-ground, five-pillar expansion path. The story alongside the evidence.",
    file: "pitch_deck_414.html",
    date: "2026-04-14",
    kind: "pitch",
    tag: "Company",
  },
];
