/**
 * Transactions screen — split layout: list on the left, detail panel right.
 *
 * Local state:
 *   - `selected`: which TX id is open in the right panel
 *   - `search`: text filter on merchant name (substring, case-insensitive)
 *   - `activeFilters`: filter chips that toggle on/off (visual-only)
 *   - `view`: "list" | "group" (visual-only — both render the same grouping)
 *
 * Group key: each TX is bucketed by its long-form date string ("Monday,
 * April 27"). useMemo prevents re-grouping on every keystroke when search
 * doesn't change the underlying filtered set.
 */
"use client";

import { useState, useMemo } from "react";
import { Icon } from "../icons";
import {
  Pill,
  Topbar,
  MerchantBadge,
  CategoryChip,
  SegControl,
  Chip,
} from "../shared";
import { ACCOUNTS, CATEGORIES, FMT, TX } from "../data";
import type { Transaction } from "../data";
import type { ScreenProps } from "../screen-types";

export function ScreenTransactions({ onCmdK }: ScreenProps) {
  const [selected, setSelected] = useState("t0");
  const [search, setSearch] = useState("");
  const [activeFilters, setActiveFilters] = useState<string[]>(["This month"]);
  const [view, setView] = useState("list");

  const filtered = TX.filter(
    (t) => !search || t.merchant.toLowerCase().includes(search.toLowerCase())
  );
  const tx = filtered.find((t) => t.id === selected) || filtered[0];

  // Group by long-form date string so the "Monday, April 27" headers in
  // the design appear as bucket separators.
  const groups = useMemo(() => {
    const g: Record<string, Transaction[]> = {};
    filtered.forEach((t) => {
      const k = t.date.toLocaleDateString("en-US", {
        weekday: "long",
        month: "long",
        day: "numeric",
      });
      (g[k] = g[k] || []).push(t);
    });
    return g;
  }, [filtered]);

  const account = ACCOUNTS.find((a) => a.id === tx?.account);

  return (
    <div className="split">
      <div
        className="content-col screen-fade"
        style={{ borderRight: "1px solid var(--border)" }}
      >
        <Topbar
          crumbs={["Workspace", "Transactions"]}
          onCmdK={onCmdK}
          actions={
            <>
              <button className="btn">
                <Icon name="download" /> Export
              </button>
              <button className="btn primary">
                <Icon name="plus" /> Add transaction
              </button>
            </>
          }
        />

        <div className="filter-bar">
          <div className="search-wrap">
            <Icon name="search" />
            <input
              className="search-input"
              placeholder="Search merchant, note, amount…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>
          {["This month", "All accounts", "All categories", "Cleared"].map((f) => (
            <Chip
              key={f}
              active={activeFilters.includes(f)}
              removable
              onClick={() =>
                setActiveFilters((arr) =>
                  arr.includes(f) ? arr.filter((x) => x !== f) : [...arr, f]
                )
              }
            >
              {f}
            </Chip>
          ))}
          <button className="chip">
            <Icon name="plus" style={{ width: 11, height: 11 }} /> Filter
          </button>
          <div className="right row gap-6">
            <SegControl
              value={view}
              onChange={setView}
              options={[
                { value: "list", label: "List" },
                { value: "group", label: "Grouped" },
              ]}
            />
            <button className="icon-btn outline">
              <Icon name="sort" />
            </button>
          </div>
        </div>

        <div className="scroll">
          <div className="tx-row head">
            <span></span>
            <span>Merchant</span>
            <span>Category</span>
            <span style={{ textAlign: "right" }}>Account</span>
            <span style={{ textAlign: "right" }}>Amount</span>
            <span></span>
          </div>
          {Object.entries(groups).map(([day, items]) => (
            <div key={day}>
              <div
                style={{
                  padding: "14px 16px 6px",
                  fontSize: 11,
                  textTransform: "uppercase",
                  letterSpacing: "0.06em",
                  color: "var(--ink-3)",
                  fontWeight: 550,
                  background: "var(--surface)",
                  borderBottom: "1px solid var(--border)",
                  display: "flex",
                  alignItems: "center",
                  gap: 8,
                }}
              >
                <span>{day}</span>
                <span style={{ color: "var(--ink-4)" }}>·</span>
                <span
                  className="num text-3"
                  style={{ textTransform: "none", letterSpacing: 0 }}
                >
                  Net{" "}
                  {FMT.usd(
                    items.reduce((s, t) => s + t.amount, 0),
                    { sign: true }
                  )}
                </span>
              </div>
              {items.map((t) => {
                const acct = ACCOUNTS.find((a) => a.id === t.account);
                return (
                  <div
                    key={t.id}
                    className={`tx-row ${selected === t.id ? "selected" : ""}`}
                    onClick={() => setSelected(t.id)}
                  >
                    <span className={`ck ${selected === t.id ? "on" : ""}`}>
                      <Icon name="check" />
                    </span>
                    <div className="merch-cell">
                      <MerchantBadge name={t.merchant} size={26} />
                      <div className="col" style={{ minWidth: 0 }}>
                        <div className="merch-name">{t.merchant}</div>
                        {t.note && <div className="merch-sub">{t.note}</div>}
                      </div>
                    </div>
                    <div>
                      <CategoryChip cat={t.category} />
                    </div>
                    <div
                      className="text-3 fz-12"
                      style={{ textAlign: "right" }}
                    >
                      {acct?.bank} ··{acct?.last4}
                    </div>
                    <div
                      className={`num ${t.amount > 0 ? "pos fw-6" : ""}`}
                      style={{ textAlign: "right" }}
                    >
                      {t.amount > 0 ? "+" : ""}
                      {FMT.usd(t.amount)}
                    </div>
                    <button
                      className="icon-btn"
                      onClick={(e) => e.stopPropagation()}
                    >
                      <Icon name="moreV" />
                    </button>
                  </div>
                );
              })}
            </div>
          ))}
        </div>
      </div>

      {/* Detail panel */}
      {tx && (
        <div className="detail-panel screen-fade">
          <div
            style={{
              padding: "18px 16px 12px",
              borderBottom: "1px solid var(--border)",
            }}
          >
            <div className="row gap-8" style={{ alignItems: "center" }}>
              <MerchantBadge name={tx.merchant} size={36} />
              <div className="col grow">
                <div className="fw-6 fz-13">{tx.merchant}</div>
                <div className="fz-12 text-3">
                  {tx.date.toLocaleDateString("en-US", {
                    weekday: "short",
                    month: "short",
                    day: "numeric",
                    year: "numeric",
                  })}
                </div>
              </div>
              <button className="icon-btn">
                <Icon name="moreV" />
              </button>
            </div>
            <div
              className="h-display num mt-12"
              style={{
                fontSize: 36,
                color: tx.amount > 0 ? "var(--pos)" : "var(--ink)",
              }}
            >
              {tx.amount > 0 ? "+" : ""}
              {FMT.usd(tx.amount)}
            </div>
            <div className="row gap-6 mt-8">
              {tx.cleared ? (
                <Pill tone="pos" dot>
                  Cleared
                </Pill>
              ) : (
                <Pill tone="warn" dot>
                  Pending
                </Pill>
              )}
              <Pill>USD</Pill>
            </div>
          </div>

          <div style={{ padding: "12px 0" }}>
            <div className="prop-row">
              <div className="k">
                <Icon name="tag" /> Category
              </div>
              <div className="v">
                <CategoryChip cat={tx.category} />
              </div>
            </div>
            <div className="prop-row">
              <div className="k">
                <Icon name="bank" /> Account
              </div>
              <div className="v">
                {account?.name} ··{account?.last4}
              </div>
            </div>
            <div className="prop-row">
              <div className="k">
                <Icon name="calendar" /> Date
              </div>
              <div className="v">
                {tx.date.toLocaleDateString("en-US", {
                  month: "short",
                  day: "numeric",
                  year: "numeric",
                })}
              </div>
            </div>
            <div className="prop-row">
              <div className="k">
                <Icon name="pin" /> Location
              </div>
              <div className="v">San Francisco, CA</div>
            </div>
            <div className="prop-row">
              <div className="k">
                <Icon name="user" /> Split with
              </div>
              <div className="v">
                <Pill>Just me</Pill>
              </div>
            </div>
            <div className="prop-row">
              <div className="k">
                <Icon name="repeat" /> Recurring
              </div>
              <div className="v text-3">Detect off</div>
            </div>
          </div>

          <div
            style={{
              padding: "4px 16px 12px",
              borderTop: "1px solid var(--border)",
            }}
          >
            <div className="h-eyebrow mb-8 mt-12">Note</div>
            <div
              className="card tinted card-pad"
              style={{ padding: 12, fontSize: 13, color: "var(--ink-2)" }}
            >
              {tx.note || "Add a note…"}
            </div>

            <div className="h-eyebrow mb-8 mt-20">Receipt</div>
            <button
              className="btn"
              style={{ width: "100%", justifyContent: "center", height: 36 }}
            >
              <Icon name="paperclip" /> Attach receipt
            </button>

            <div className="h-eyebrow mb-8 mt-20">Activity</div>
            <div style={{ marginLeft: -16, marginRight: -16 }}>
              <div className="activity-item">
                <div className="dot">
                  <Icon name="check" />
                </div>
                <div className="body">
                  <span className="who">You</span> categorized as{" "}
                  {CATEGORIES[tx.category].label}{" "}
                  <span className="meta">2h ago</span>
                </div>
              </div>
              <div className="activity-item">
                <div className="dot">
                  <Icon name="sparkle" />
                </div>
                <div className="body">
                  <span className="who">Lumen</span> auto-imported from{" "}
                  {account?.bank} <span className="meta">3h ago</span>
                </div>
              </div>
              <div className="activity-item">
                <div className="dot">
                  <Icon name="card" />
                </div>
                <div className="body">
                  <span className="who">{account?.bank}</span> posted{" "}
                  {FMT.usd(tx.amount)}{" "}
                  <span className="meta">
                    {tx.date.toLocaleDateString("en-US", {
                      month: "short",
                      day: "numeric",
                    })}
                  </span>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
