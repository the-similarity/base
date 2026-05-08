/**
 * Lumen screen identifiers — a one-element union now that the route
 * collapses to a single screen (the embedded Workstation component).
 *
 * History note: this used to be a nine-element union covering
 * Retrieve / Runs / Compare / Reviews / Dashboard / Strategy /
 * Cadence / Case Studies / Reports — every entry corresponded to a
 * mockup screen under `screens/`. Those screens were deleted when
 * `/workstation/lumen` started embedding the real Workstation
 * component; the type is kept (rather than removed entirely) so the
 * sidebar / palette / page contract doesn't need to special-case the
 * "no screens" edge.
 *
 * If we ever add a second contained screen, extend this union, then
 * follow the same wiring rule the original comment described:
 *   1. extend this union
 *   2. add a sidebar entry in sidebar.tsx
 *   3. mount the screen in page.tsx
 *   4. (optionally) add a palette entry in cmdk.tsx
 *
 * Lifecycle / immutability notes
 * ------------------------------
 * `ScreenId` is THE source of truth for screen identity. Anything keyed
 * off the screen id (sidebar, palette, page switch) MUST import this
 * union — never inline string-literal types — so adding/removing a
 * screen forces compile-time checks at every site.
 */

import type { Dispatch, SetStateAction } from "react";

/**
 * The set of screens mounted under /workstation/lumen.
 *
 * Currently a single entry. Kept as a union (rather than the literal
 * type `"retrieve"`) so future expansion is a one-line change.
 */
export type ScreenId = "retrieve";

/**
 * Common prop shape passed to every screen by `page.tsx`. Screens
 * accept whichever subset they actually use — TS optional fields keep
 * us flexible without per-screen prop interfaces.
 */
export interface ScreenProps {
  onCmdK: () => void;
  onNavigate: (id: ScreenId) => void;
  // Optional route-level dark-mode setter for screens that need to
  // expose the same theme action as Cmd+K.
  setDark?: Dispatch<SetStateAction<boolean>>;
}
