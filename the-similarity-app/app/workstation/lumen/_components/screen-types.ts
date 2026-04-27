/**
 * Lumen screen identifiers — shared union to keep nav, palette, and the
 * top-level switch statement type-safe. Adding a new screen requires:
 *   1. extending this union
 *   2. wiring sidebar.tsx (NAV groups)
 *   3. wiring page.tsx (switch + import)
 *   4. wiring cmdk.tsx (palette item, optional)
 *
 * Each screen owns the same prop shape so the switch in page.tsx can
 * forward props without per-screen casts.
 */

export type ScreenId =
  | "dashboard"
  | "cashflow"
  | "insights"
  | "accounts"
  | "transactions"
  | "recurring"
  | "budgets"
  | "goals"
  | "investments";

export interface ScreenProps {
  onCmdK: () => void;
  onNavigate: (id: ScreenId) => void;
}
