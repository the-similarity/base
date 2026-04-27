/**
 * Accounts screen — grouped account cards with mini sparklines.
 *
 * Groups: Cash, Credit cards, Investments, Loans. Each group renders a
 * 2-column grid of account cards. Credit cards include a utilization
 * progress bar and "available" remainder; savings accounts show APY.
 */
"use client";

import { Icon } from "../icons";
import { Pill, Topbar, SegControl } from "../shared";
import { Sparkline } from "../charts";
import { ACCOUNTS, FMT } from "../data";
import type { Account } from "../data";
import type { ScreenProps } from "../screen-types";

export function ScreenAccounts({ onCmdK }: ScreenProps) {
  const groups: Record<string, Account[]> = {
    Cash: ACCOUNTS.filter((a) => ["Checking", "Savings"].includes(a.kind)),
    "Credit cards": ACCOUNTS.filter((a) => a.kind === "Credit Card"),
    Investments: ACCOUNTS.filter((a) =>
      ["Investment", "Retirement"].includes(a.kind)
    ),
    Loans: ACCOUNTS.filter((a) => a.kind === "Loan"),
  };

  const totals: Record<string, number> = Object.fromEntries(
    Object.entries(groups).map(([k, arr]) => [
      k,
      arr.reduce((s, a) => s + a.balance, 0),
    ])
  );
  const grandTotal = Object.values(totals).reduce((a, b) => a + b, 0);

  return (
    <div className="content-col screen-fade">
      <Topbar
        crumbs={["Workspace", "Accounts"]}
        onCmdK={onCmdK}
        actions={
          <>
            <button className="btn">
              <Icon name="link" /> Connect
            </button>
            <button className="btn primary">
              <Icon name="plus" /> Add account
            </button>
          </>
        }
      />

      <div className="scroll">
        <div className="scroll-pad">
          <div className="row gap-24" style={{ alignItems: "flex-end" }}>
            <div>
              <div className="h-eyebrow mb-8">All accounts</div>
              <div className="h-display num" style={{ fontSize: 44 }}>
                $
                {grandTotal.toLocaleString("en-US", { maximumFractionDigits: 0 })}
              </div>
              <div className="row gap-8 mt-8 fz-12 text-3">
                <span>{ACCOUNTS.length} accounts</span>
                <span>·</span>
                <span>4 institutions</span>
                <span>·</span>
                <span className="row gap-4">
                  <span
                    style={{
                      width: 6,
                      height: 6,
                      borderRadius: 3,
                      background: "var(--pos)",
                    }}
                  />{" "}
                  Synced 2m ago
                </span>
              </div>
            </div>
            <div className="right row gap-8">
              <button className="btn">
                <Icon name="filter" /> Group
              </button>
              <SegControl
                value="grid"
                onChange={() => {}}
                options={[
                  { value: "grid", label: "Cards" },
                  { value: "list", label: "List" },
                ]}
              />
            </div>
          </div>

          {Object.entries(groups).map(
            ([label, arr]) =>
              arr.length > 0 && (
                <div key={label} className="mt-24">
                  <div className="row" style={{ alignItems: "baseline", marginBottom: 10 }}>
                    <div className="fw-6 fz-13">{label}</div>
                    <div className="text-3 fz-12" style={{ marginLeft: 8 }}>
                      {arr.length} {arr.length === 1 ? "account" : "accounts"}
                    </div>
                    <div
                      className="num right fw-6"
                      style={{
                        color: totals[label] >= 0 ? "var(--ink)" : "var(--neg)",
                      }}
                    >
                      {FMT.usd(totals[label], { cents: false })}
                    </div>
                  </div>
                  <div
                    style={{
                      display: "grid",
                      gridTemplateColumns: "repeat(2, 1fr)",
                      gap: 12,
                    }}
                  >
                    {arr.map((a) => (
                      <div key={a.id} className="acct-card">
                        <div className="acct-logo" style={{ background: a.color }}>
                          {a.logo || a.bank.slice(0, 1)}
                        </div>
                        <div className="grow col" style={{ minWidth: 0 }}>
                          <div className="row gap-8">
                            <div className="fw-6 fz-13">{a.name}</div>
                            {a.apy && <Pill tone="pos">APY {a.apy.toFixed(2)}%</Pill>}
                          </div>
                          <div className="text-3 fz-12">
                            {a.bank} ··{a.last4}
                            {a.due ? ` · Due ${a.due}` : ""}
                          </div>
                          {a.limit && (
                            <div className="row gap-8 mt-8">
                              <div className="progress thin grow">
                                <div
                                  className="fill"
                                  style={{
                                    width: `${
                                      (Math.abs(a.balance) / a.limit) * 100
                                    }%`,
                                    background: "var(--ink-2)",
                                  }}
                                />
                              </div>
                              <div className="text-3 fz-11 num">
                                $
                                {(a.limit - Math.abs(a.balance)).toLocaleString()}{" "}
                                avail
                              </div>
                            </div>
                          )}
                        </div>
                        <div className="col" style={{ alignItems: "flex-end" }}>
                          <div
                            className={`num fw-6 fz-14 ${
                              a.balance < 0 ? "neg" : ""
                            }`}
                          >
                            {a.balance < 0 ? "−" : ""}$
                            {Math.abs(a.balance).toLocaleString("en-US", {
                              minimumFractionDigits: 2,
                              maximumFractionDigits: 2,
                            })}
                          </div>
                          <div className="mt-4">
                            <Sparkline
                              data={[8, 9, 7, 10, 12, 11, 14, 13, 16, 15]}
                              stroke={a.balance >= 0 ? "var(--pos)" : "var(--neg)"}
                              width={80}
                              height={22}
                            />
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )
          )}
        </div>
      </div>
    </div>
  );
}
