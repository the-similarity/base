/**
 * Strategy — Lumen landing for the strategy builder.
 *
 * Canonical view: /strategy. Lumen surfaces an explainer + entry point.
 */
"use client";

import Link from "next/link";
import { Topbar } from "../shared";
import { Icon } from "../icons";
import type { ScreenProps } from "../screen-types";

export function ScreenStrategy({ onCmdK }: ScreenProps) {
  return (
    <div className="lumen-content-col lumen-screen-fade">
      <Topbar crumbs={["Workspace", "Reports", "Strategy"]} onCmdK={onCmdK} />
      <div className="lumen-scroll">
        <div className="lumen-scroll-pad">
          <div className="lumen-mb-24">
            <div className="lumen-eyebrow lumen-mb-12">Reports · strategy</div>
            <div
              className="lumen-display"
              style={{ fontSize: 40, marginBottom: 12 }}
            >
              Strategy builder
            </div>
            <div className="lumen-text-2" style={{ fontSize: 14, maxWidth: 640 }}>
              Compose entries, exits, and risk pads from analog signals.
              Backtest the assembled strategy across the registered runs.
            </div>
          </div>

          <div className="lumen-card">
            <div
              style={{ padding: 28, display: "flex", flexDirection: "column", gap: 14 }}
            >
              <div className="lumen-text-2" style={{ fontSize: 14, lineHeight: 1.55 }}>
                The strategy builder UI lives at /strategy in the main app.
              </div>
              <div className="lumen-row lumen-gap-8">
                <Link href="/strategy" className="lumen-btn is-primary">
                  <Icon name="link" /> Open strategy builder
                </Link>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
