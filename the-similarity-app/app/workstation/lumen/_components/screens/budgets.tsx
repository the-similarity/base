/**
 * Budgets screen — month-to-date totals + per-category progress bars.
 *
 * Over-budget categories render a darker overflow segment beyond the 100%
 * line so users can see at a glance which budgets blew their cap.
 */
"use client";

import { Icon } from "../icons";
import { Pill, Topbar, SectionHead, SegControl } from "../shared";
import { BUDGETS, CATEGORIES } from "../data";
import type { ScreenProps } from "../screen-types";

export function ScreenBudgets({ onCmdK }: ScreenProps) {
  const total = BUDGETS.reduce((s, b) => s + b.limit, 0);
  const spent = BUDGETS.reduce((s, b) => s + b.spent, 0);

  return (
    <div className="content-col screen-fade">
      <Topbar
        crumbs={["Workspace", "Budgets"]}
        onCmdK={onCmdK}
        actions={
          <>
            <button className="btn">
              <Icon name="history" /> Last month
            </button>
            <button className="btn primary">
              <Icon name="plus" /> New budget
            </button>
          </>
        }
      />

      <div className="scroll">
        <div className="scroll-pad">
          <div className="row gap-24" style={{ alignItems: "flex-end" }}>
            <div>
              <div className="h-eyebrow mb-8">April · Day 27 of 30</div>
              <div className="h-display num" style={{ fontSize: 44 }}>
                ${spent.toFixed(0)}{" "}
                <span className="text-3" style={{ fontSize: 22 }}>
                  of ${total.toFixed(0)}
                </span>
              </div>
              <div className="row gap-8 mt-8">
                <Pill tone="warn" dot>
                  ${(spent - total).toFixed(0)} over pace
                </Pill>
                <span className="text-3 fz-12">3 categories over limit</span>
              </div>
            </div>
            <div className="right">
              <SegControl
                value="month"
                onChange={() => {}}
                options={[
                  { value: "week", label: "Week" },
                  { value: "month", label: "Month" },
                  { value: "year", label: "Year" },
                ]}
              />
            </div>
          </div>

          {/* Big aggregate bar */}
          <div className="card card-pad mt-20">
            <div className="row gap-12" style={{ alignItems: "center" }}>
              <div className="grow">
                <div className="progress" style={{ height: 28, borderRadius: 8 }}>
                  <div
                    className="fill"
                    style={{
                      width: `${Math.min(100, (spent / total) * 100)}%`,
                      background: "linear-gradient(90deg, var(--accent), var(--accent-2))",
                      borderRadius: 8,
                    }}
                  />
                </div>
              </div>
              <div className="num fw-6">{((spent / total) * 100).toFixed(0)}%</div>
            </div>
            <div className="row mt-8 fz-12 text-3">
              <span>$0</span>
              <span className="right">${total.toFixed(0)}</span>
            </div>
          </div>

          {/* Categories */}
          <div className="mt-24">
            <SectionHead
              title="Categories"
              sub={`${BUDGETS.length} budgets`}
              actions={
                <button className="btn ghost">
                  <Icon name="grid" /> Reorder
                </button>
              }
            />
            <div className="card">
              {BUDGETS.map((b, i) => {
                const cat = CATEGORIES[b.cat];
                const pct = (b.spent / b.limit) * 100;
                const over = pct > 100;
                return (
                  <div
                    key={b.cat}
                    style={{
                      display: "grid",
                      gridTemplateColumns: "32px 200px 1fr 110px",
                      gap: 14,
                      alignItems: "center",
                      padding: "14px 16px",
                      borderBottom:
                        i < BUDGETS.length - 1
                          ? "1px solid var(--border)"
                          : "none",
                    }}
                  >
                    <div
                      style={{
                        width: 28,
                        height: 28,
                        borderRadius: 7,
                        background: cat.color + "18",
                        color: cat.color,
                        display: "grid",
                        placeItems: "center",
                      }}
                    >
                      <Icon name={cat.icon} />
                    </div>
                    <div className="col">
                      <div className="fw-6 fz-13">{cat.label}</div>
                      <div className="text-3 fz-11">
                        {over
                          ? `${(pct - 100).toFixed(0)}% over`
                          : `${(100 - pct).toFixed(0)}% remaining`}
                      </div>
                    </div>
                    <div>
                      <div className="progress" style={{ height: 8 }}>
                        <div
                          className="fill"
                          style={{
                            width: `${Math.min(100, pct)}%`,
                            background: over ? "var(--neg)" : cat.color,
                          }}
                        />
                        {over && (
                          // Faded over-cap segment that visually extends past
                          // the 100% boundary. Capped at 50% extra so a wildly
                          // over-budget row doesn't push beyond the card.
                          <div
                            style={{
                              position: "absolute",
                              top: 0,
                              left: "100%",
                              height: 8,
                              width: `${Math.min(50, pct - 100)}%`,
                              background: "var(--neg)",
                              opacity: 0.4,
                              borderRadius: "0 999px 999px 0",
                            }}
                          />
                        )}
                      </div>
                    </div>
                    <div className="num" style={{ textAlign: "right" }}>
                      <span className={`fw-6 ${over ? "neg" : ""}`}>
                        ${b.spent.toFixed(0)}
                      </span>
                      <span className="text-3"> / ${b.limit}</span>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
