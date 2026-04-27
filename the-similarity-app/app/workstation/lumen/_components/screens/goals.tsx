/**
 * Goals screen — progress rings + funding actions for each savings goal.
 *
 * Each goal renders a Ring component with the goal's signature color,
 * an icon overlay (centered inside the ring), the current/target dollars,
 * and an ETA from the data record.
 */
"use client";

import { Icon } from "../icons";
import { Pill, Topbar } from "../shared";
import { Ring } from "../charts";
import { GOALS } from "../data";
import type { ScreenProps } from "../screen-types";

export function ScreenGoals({ onCmdK }: ScreenProps) {
  const total = GOALS.reduce((s, g) => s + g.current, 0);
  const target = GOALS.reduce((s, g) => s + g.target, 0);

  return (
    <div className="content-col screen-fade">
      <Topbar
        crumbs={["Workspace", "Goals"]}
        onCmdK={onCmdK}
        actions={
          <button className="btn primary">
            <Icon name="plus" /> New goal
          </button>
        }
      />
      <div className="scroll">
        <div className="scroll-pad">
          <div>
            <div className="h-eyebrow mb-8">
              Saving toward {GOALS.length} goals
            </div>
            <div className="h-display num" style={{ fontSize: 44 }}>
              ${total.toLocaleString()}{" "}
              <span className="text-3" style={{ fontSize: 22 }}>
                of ${target.toLocaleString()}
              </span>
            </div>
            <div className="row gap-8 mt-8">
              <Pill tone="pos" dot>
                +$1,840 this month
              </Pill>
              <Pill>{((total / target) * 100).toFixed(0)}% complete</Pill>
            </div>
          </div>

          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(2, 1fr)",
              gap: 14,
              marginTop: 24,
            }}
          >
            {GOALS.map((g) => {
              const pct = g.current / g.target;
              const remaining = g.target - g.current;
              return (
                <div key={g.id} className="card card-pad">
                  <div className="row gap-12" style={{ alignItems: "center" }}>
                    <div style={{ position: "relative" }}>
                      <Ring pct={pct} size={84} thickness={6} color={g.color} />
                      <div
                        style={{
                          position: "absolute",
                          inset: 0,
                          display: "grid",
                          placeItems: "center",
                          color: g.color,
                        }}
                      >
                        <Icon name={g.icon} style={{ width: 22, height: 22 }} />
                      </div>
                    </div>
                    <div className="grow">
                      <div className="row gap-8" style={{ alignItems: "baseline" }}>
                        <div className="fw-6 fz-14">{g.name}</div>
                        <Pill>{(pct * 100).toFixed(0)}%</Pill>
                      </div>
                      <div className="h-display num mt-4" style={{ fontSize: 26 }}>
                        ${g.current.toLocaleString()}
                        <span
                          className="text-3"
                          style={{
                            fontSize: 13,
                            fontFamily: "Inter",
                            marginLeft: 6,
                          }}
                        >
                          / ${g.target.toLocaleString()}
                        </span>
                      </div>
                      <div className="text-3 fz-12 mt-4 row gap-6">
                        <Icon name="calendar" style={{ width: 12, height: 12 }} /> ETA{" "}
                        {g.eta} · ${remaining.toLocaleString()} to go
                      </div>
                    </div>
                  </div>
                  <div className="row gap-6 mt-16">
                    <button
                      className="btn"
                      style={{ flex: 1, justifyContent: "center" }}
                    >
                      <Icon name="plus" /> Add funds
                    </button>
                    <button
                      className="btn"
                      style={{ flex: 1, justifyContent: "center" }}
                    >
                      <Icon name="repeat" /> Auto-save
                    </button>
                    <button className="icon-btn outline">
                      <Icon name="moreV" />
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}
