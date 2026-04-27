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
 *
 * Lifecycle / immutability notes
 * ------------------------------
 * The `ScreenId` union is THE source of truth for screen identity.
 * Anything keyed off the screen id (sidebar, palette, page switch)
 * MUST import this union — never inline string-literal types — so
 * adding/removing a screen forces compile-time checks at every site.
 */

import type { Dispatch, SetStateAction } from "react";
import type { TweakState } from "./tweaks";

/**
 * The set of screens mounted under /workstation/lumen.
 *
 * Order here mirrors the sidebar order so a reviewer reading either
 * file in isolation gets the same mental model. Adding a new screen
 * means: extend this union, add a `screens/<id>.tsx`, add a sidebar
 * row, add a switch case in page.tsx, add a palette entry in cmdk.tsx.
 */
export type ScreenId =
  | "retrieve"
  | "runs"
  | "compare"
  | "reviews"
  | "dashboard"
  | "strategy"
  | "cadence"
  | "case-studies"
  | "reports";

/**
 * Common prop shape passed to every screen by `page.tsx`. Screens
 * accept whichever subset they actually use — TS optional fields keep
 * us flexible without per-screen prop interfaces.
 */
export interface ScreenProps {
  onCmdK: () => void;
  onNavigate: (id: ScreenId) => void;
  // The tweaks setter is forwarded so palette-style "Toggle theme"
  // actions inside a screen can mutate the chrome's theme. Optional
  // because most screens never touch it.
  setTweaks?: Dispatch<SetStateAction<TweakState>>;
}
