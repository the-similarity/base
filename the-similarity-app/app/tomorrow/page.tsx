"use client";

/**
 * Tomorrow — default landing page.
 *
 * The layout (`app/tomorrow/layout.tsx`) owns the shell + providers; this
 * module is the route-level view and just renders the Today body.
 *
 * Note on metadata: the layout is a client component, so route-level
 * metadata cannot live there. Wave 2 agents can override the per-route
 * title by adding a `metadata` export in their own sub-route page.tsx
 * files — this top-level page intentionally leaves metadata to the app
 * shell's <head> so the marketing description (set in an earlier PR)
 * continues to apply to /tomorrow.
 */

import TodayView from "./_components/today-view";

export default function TomorrowPage() {
  return <TodayView />;
}
