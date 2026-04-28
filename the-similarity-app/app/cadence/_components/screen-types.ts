/**
 * Cadence screen identifiers — shared union to keep nav, palette, and the
 * top-level switch statement type-safe. Adding a new screen requires:
 *   1. extending this union
 *   2. wiring sidebar.tsx (NAV)
 *   3. wiring page.tsx (switch + import)
 *   4. wiring cmdk.tsx (palette item, optional)
 *
 * Each screen owns the same prop shape so the switch in page.tsx can
 * forward props without per-screen casts.
 *
 * Mapping after the slop cut (5 screens):
 *   today    — recovery hero + key metrics column + DayTrajectory chart
 *              with rhyme overlay + top-rhyme bridge to /rhymes
 *   rhymes   — hero analogue cards + forecast cone
 *   log      — chronological event ledger
 *   sources  — connected wearables + lab uploads
 *   labs     — long-term biomarker tracking with optimal ranges
 */

export type ScreenId =
  | "today"
  | "rhymes"
  | "log"
  | "sources"
  | "labs";

export interface ScreenProps {
  onCmdK: () => void;
  onNavigate: (id: ScreenId) => void;
}
