/**
 * Case Studies — Lumen landing for the published case-study suite.
 *
 * Canonical entry: /case-study/spy-2026-2007 — Lumen links straight to
 * the SPY 2026/2007 analog showcase as the default case study.
 */
"use client";

import Link from "next/link";
import { Topbar } from "../shared";
import { Icon } from "../icons";
import type { ScreenProps } from "../screen-types";

export function ScreenCaseStudies({ onCmdK }: ScreenProps) {
  return (
    <div className="lumen-content-col lumen-screen-fade">
      <Topbar
        crumbs={["Workspace", "Reports", "Case Studies"]}
        onCmdK={onCmdK}
      />
      <div className="lumen-scroll">
        <div className="lumen-scroll-pad">
          <div className="lumen-mb-24">
            <div className="lumen-eyebrow lumen-mb-12">Reports · case studies</div>
            <div
              className="lumen-display"
              style={{ fontSize: 40, marginBottom: 12 }}
            >
              Case studies
            </div>
            <div className="lumen-text-2" style={{ fontSize: 14, maxWidth: 640 }}>
              Published analog showcases — interactive walk-throughs of where
              the methods found a structural rhyme and what played out next.
            </div>
          </div>

          <div className="lumen-card">
            <div
              style={{ padding: 28, display: "flex", flexDirection: "column", gap: 14 }}
            >
              <div className="lumen-text-2" style={{ fontSize: 14, lineHeight: 1.55 }}>
                The featured case study is SPY 2026 vs 2007 — an interactive
                showcase of the analog match and forecast cone.
              </div>
              <div className="lumen-row lumen-gap-8">
                <Link
                  href="/case-study/spy-2026-2007"
                  className="lumen-btn is-primary"
                >
                  <Icon name="link" /> Open SPY 2026 / 2007
                </Link>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
