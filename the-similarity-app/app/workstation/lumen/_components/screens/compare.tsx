/**
 * Compare — Lumen landing for the run-compare experience.
 *
 * Why this is a landing card and not a full embed: the canonical
 * compare view lives at /finance/compare and depends on chart
 * components that pull /globals.css selectors (lightweight-charts
 * theme tokens, .pillar grid, etc.). Embedding inside the Lumen
 * `.lumen-app` shell would produce a CSS-cascade fight; the
 * pragmatic answer is to keep the compare experience canonical at
 * /finance/compare and use the Lumen screen as a polished entry point.
 */
"use client";

import Link from "next/link";
import { Topbar } from "../shared";
import { Icon } from "../icons";
import type { ScreenProps } from "../screen-types";

export function ScreenCompare({ onCmdK }: ScreenProps) {
  return (
    <div className="lumen-content-col lumen-screen-fade">
      <Topbar crumbs={["Workspace", "Finance", "Compare"]} onCmdK={onCmdK} />
      <div className="lumen-scroll">
        <div className="lumen-scroll-pad">
          <div className="lumen-mb-24">
            <div className="lumen-eyebrow lumen-mb-12">Finance · compare</div>
            <div
              className="lumen-display"
              style={{ fontSize: 40, marginBottom: 12 }}
            >
              Compare runs
            </div>
            <div className="lumen-text-2" style={{ fontSize: 14, maxWidth: 640 }}>
              Diff two backtest runs side-by-side: hit rates, calibration,
              trust scores, and forecast cones overlaid on the same axis.
            </div>
          </div>

          <div className="lumen-card">
            <div
              style={{ padding: 28, display: "flex", flexDirection: "column", gap: 14 }}
            >
              <div className="lumen-text-2" style={{ fontSize: 14, lineHeight: 1.55 }}>
                The canonical comparison view lives in the finance app — it
                renders the run-vs-run diff with the production chart
                components. Open it to compare any two runs from the
                registry.
              </div>
              <div className="lumen-row lumen-gap-8">
                <Link href="/finance/compare" className="lumen-btn is-primary">
                  <Icon name="link" /> Open compare view
                </Link>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
