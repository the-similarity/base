/**
 * Cadence Cycles screen — placeholder, filled in subsequent commits.
 *
 * The Lumen-style 9-screen workstation pattern requires every screen to
 * exist as a mounted component before the route can render. This stub
 * keeps the page compilable while later commits flesh out each screen
 * one at a time per the granular-commit rule in CLAUDE.md.
 */
"use client";

import { Topbar } from "../shared";
import type { ScreenProps } from "../screen-types";

export function ScreenCycles({ onCmdK }: ScreenProps) {
  return (
    <div className="content-col screen-fade">
      <Topbar crumbs={["Workspace", "Cycles"]} onCmdK={onCmdK} />
      <div className="scroll">
        <div className="scroll-pad">
          <div className="h-eyebrow mb-8">Cycles</div>
          <div className="text-3 fz-13">Coming up next.</div>
        </div>
      </div>
    </div>
  );
}
