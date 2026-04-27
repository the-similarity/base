/**
 * Dashboard — Lumen landing for the finance overview dashboard.
 *
 * Canonical view: /finance/dashboard — Lumen surfaces an explainer
 * card + entry point. The real dashboard renders run aggregates and
 * trust-score histograms via the production chart layer.
 */
"use client";

import Link from "next/link";
import { Topbar } from "../shared";
import { Icon } from "../icons";
import type { ScreenProps } from "../screen-types";

export function ScreenDashboard({ onCmdK }: ScreenProps) {
  return (
    <div className="lumen-content-col lumen-screen-fade">
      <Topbar crumbs={["Workspace", "Finance", "Dashboard"]} onCmdK={onCmdK} />
      <div className="lumen-scroll">
        <div className="lumen-scroll-pad">
          <div className="lumen-mb-24">
            <div className="lumen-eyebrow lumen-mb-12">Finance · dashboard</div>
            <div
              className="lumen-display"
              style={{ fontSize: 40, marginBottom: 12 }}
            >
              Operating dashboard
            </div>
            <div className="lumen-text-2" style={{ fontSize: 14, maxWidth: 640 }}>
              Run aggregates, trust-score histograms, and cohort views across
              every finance run in the registry.
            </div>
          </div>

          <div className="lumen-card">
            <div
              style={{ padding: 28, display: "flex", flexDirection: "column", gap: 14 }}
            >
              <div className="lumen-text-2" style={{ fontSize: 14, lineHeight: 1.55 }}>
                The full operating dashboard lives in the finance app.
              </div>
              <div className="lumen-row lumen-gap-8">
                <Link href="/finance/dashboard" className="lumen-btn is-primary">
                  <Icon name="link" /> Open dashboard
                </Link>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
