/**
 * Recurring screen — flat table of subscriptions with monthly total + AI tip.
 *
 * Design intentionally keeps this screen lean — no charts, just a sorted
 * list with next-charge dates and an actionable Lumen suggestion at the
 * bottom prompting the user to downgrade or pause unused subs.
 */
"use client";

import { Icon } from "../icons";
import { Pill, Topbar } from "../shared";
import { SUBSCRIPTIONS } from "../data";
import type { ScreenProps } from "../screen-types";

export function ScreenRecurring({ onCmdK }: ScreenProps) {
  const total = SUBSCRIPTIONS.reduce((s, x) => s + x.amount, 0);
  return (
    <div className="content-col screen-fade">
      <Topbar
        crumbs={["Workspace", "Recurring"]}
        onCmdK={onCmdK}
        actions={
          <>
            <button className="btn">
              <Icon name="search" /> Detect new
            </button>
            <button className="btn primary">
              <Icon name="plus" /> Track manually
            </button>
          </>
        }
      />
      <div className="scroll">
        <div className="scroll-pad">
          <div className="row" style={{ alignItems: "flex-end" }}>
            <div>
              <div className="h-eyebrow mb-8">
                Monthly recurring · {SUBSCRIPTIONS.length} active
              </div>
              <div className="h-display num" style={{ fontSize: 44 }}>
                ${total.toFixed(2)}
              </div>
              <div className="row gap-8 mt-8">
                <Pill>${(total * 12).toFixed(0)} per year</Pill>
                <Pill tone="warn" dot>
                  2 subscriptions unused 60d+
                </Pill>
              </div>
            </div>
          </div>

          <div className="card mt-20">
            <div
              className="sub-row"
              style={{
                background: "var(--surface-2)",
                textTransform: "uppercase",
                letterSpacing: "0.06em",
                fontSize: 11,
                color: "var(--ink-3)",
                fontWeight: 550,
              }}
            >
              <span></span>
              <span>Service</span>
              <span style={{ textAlign: "right" }}>Next charge</span>
              <span style={{ textAlign: "right" }}>Amount</span>
            </div>
            {SUBSCRIPTIONS.map((s) => (
              <div key={s.name} className="sub-row">
                <div
                  className="merch"
                  style={{ background: s.color, width: 32, height: 32, fontSize: 12 }}
                >
                  {s.mark}
                </div>
                <div className="col">
                  <div className="fw-6 fz-13">{s.name}</div>
                  <div className="text-3 fz-11">{s.freq} · since Mar 2024</div>
                </div>
                <div
                  className="text-3 fz-12 num"
                  style={{ textAlign: "right" }}
                >
                  {s.next}
                </div>
                <div className="num fw-6" style={{ textAlign: "right" }}>
                  ${s.amount.toFixed(2)}
                </div>
              </div>
            ))}
          </div>

          <div className="ai-bubble mt-20">
            <div className="ai-head">
              <span className="pulse" /> Lumen Suggestion
            </div>
            <div>
              You haven&apos;t used <b>iCloud+</b> on more than 18% of capacity
              for 6 months. Downgrading to the 50GB tier would save{" "}
              <b>$84/year</b>. <b>Notion</b> hasn&apos;t been opened in 47 days
              — consider pausing.
            </div>
            <div className="row gap-6 mt-12">
              <button className="btn">Downgrade iCloud</button>
              <button className="btn">Pause Notion</button>
              <button className="btn ghost">Review later</button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
