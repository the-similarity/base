/**
 * Reviews — Lumen landing for the run review queue.
 *
 * Canonical view: /finance/reviews — Lumen surfaces a polished entry
 * point + explainer rather than re-rendering the queue inside this
 * shell.
 */
"use client";

import Link from "next/link";
import { Topbar } from "../shared";
import { Icon } from "../icons";
import type { ScreenProps } from "../screen-types";

export function ScreenReviews({ onCmdK }: ScreenProps) {
  return (
    <div className="lumen-content-col lumen-screen-fade">
      <Topbar crumbs={["Workspace", "Finance", "Reviews"]} onCmdK={onCmdK} />
      <div className="lumen-scroll">
        <div className="lumen-scroll-pad">
          <div className="lumen-mb-24">
            <div className="lumen-eyebrow lumen-mb-12">Finance · reviews</div>
            <div
              className="lumen-display"
              style={{ fontSize: 40, marginBottom: 12 }}
            >
              Run reviews
            </div>
            <div className="lumen-text-2" style={{ fontSize: 14, maxWidth: 640 }}>
              Approve, reject, or escalate finance runs. Each review captures
              the signal summary, calibration context, risk flags, and the
              realized outcome.
            </div>
          </div>

          <div className="lumen-card">
            <div
              style={{ padding: 28, display: "flex", flexDirection: "column", gap: 14 }}
            >
              <div className="lumen-text-2" style={{ fontSize: 14, lineHeight: 1.55 }}>
                The full review queue with status pills, trust decisions, and
                realized-outcome editors lives in the finance app.
              </div>
              <div className="lumen-row lumen-gap-8">
                <Link href="/finance/reviews" className="lumen-btn is-primary">
                  <Icon name="link" /> Open reviews queue
                </Link>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
