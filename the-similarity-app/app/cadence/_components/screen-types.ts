/**
 * Cadence screen identifiers — shared union to keep nav, palette, and the
 * top-level switch statement type-safe. Adding a new screen requires:
 *   1. extending this union
 *   2. wiring sidebar.tsx (NAV groups)
 *   3. wiring page.tsx (switch + import)
 *   4. wiring cmdk.tsx (palette item, optional)
 *
 * Each screen owns the same prop shape so the switch in page.tsx can
 * forward props without per-screen casts.
 *
 * Mapping from spec:
 *   today    — KEY METRICS column + DayTrajectory + RhymeHeatmap + TagDonut + ThreadRibbon
 *   rhymes   — hero analogue cards + forecast cone
 *   cycles   — recurring patterns (weekly / monthly / training)
 *   log      — chronological event ledger + composer
 *   targets  — active sleep / HRV / recovery targets with progress
 *   goals    — long-horizon goals with projected completion
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
