/**
 * Reports — Lumen landing for the reports route.
 *
 * Canonical view: /reports. Lumen surfaces an explainer + entry point.
 */
"use client";

import Link from "next/link";
import { Topbar } from "../shared";
import { Icon } from "../icons";
import type { ScreenProps } from "../screen-types";

export function ScreenReports({ onCmdK }: ScreenProps) {
  return (
    <div className="lumen-content-col lumen-screen-fade">
      <Topbar crumbs={["Workspace", "Reports"]} onCmdK={onCmdK} />
      <div className="lumen-scroll">
        <div className="lumen-scroll-pad">
          <div className="lumen-mb-24">
            <div className="lumen-eyebrow lumen-mb-12">Reports</div>
            <div
              className="lumen-display"
              style={{ fontSize: 40, marginBottom: 12 }}
            >
              Reports
            </div>
            <div className="lumen-text-2" style={{ fontSize: 14, maxWidth: 640 }}>
              Periodic write-ups: weekly retrospectives, calibration drift
              reviews, and the running changelog of the analog suite.
            </div>
          </div>

          <div className="lumen-card">
            <div
              style={{ padding: 28, display: "flex", flexDirection: "column", gap: 14 }}
            >
              <div className="lumen-text-2" style={{ fontSize: 14, lineHeight: 1.55 }}>
                The full reports archive lives at /reports.
              </div>
              <div className="lumen-row lumen-gap-8">
                <Link href="/reports" className="lumen-btn is-primary">
                  <Icon name="link" /> Open reports
                </Link>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
