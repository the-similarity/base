/**
 * Cadence — Lumen landing for the daily research cadence view.
 *
 * Canonical view: /cadence. Lumen surfaces an explainer + entry point.
 */
"use client";

import Link from "next/link";
import { Topbar } from "../shared";
import { Icon } from "../icons";
import type { ScreenProps } from "../screen-types";

export function ScreenCadence({ onCmdK }: ScreenProps) {
  return (
    <div className="lumen-content-col lumen-screen-fade">
      <Topbar crumbs={["Workspace", "Reports", "Cadence"]} onCmdK={onCmdK} />
      <div className="lumen-scroll">
        <div className="lumen-scroll-pad">
          <div className="lumen-mb-24">
            <div className="lumen-eyebrow lumen-mb-12">Reports · cadence</div>
            <div
              className="lumen-display"
              style={{ fontSize: 40, marginBottom: 12 }}
            >
              Cadence
            </div>
            <div className="lumen-text-2" style={{ fontSize: 14, maxWidth: 640 }}>
              Daily research cadence: today&rsquo;s analogs, rhyme checks,
              biomarker reviews, and the rolling calibration trend.
            </div>
          </div>

          <div className="lumen-card">
            <div
              style={{ padding: 28, display: "flex", flexDirection: "column", gap: 14 }}
            >
              <div className="lumen-text-2" style={{ fontSize: 14, lineHeight: 1.55 }}>
                The full cadence experience lives at /cadence.
              </div>
              <div className="lumen-row lumen-gap-8">
                <Link href="/cadence" className="lumen-btn is-primary">
                  <Icon name="link" /> Open cadence
                </Link>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
