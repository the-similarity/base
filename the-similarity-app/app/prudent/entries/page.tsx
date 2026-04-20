"use client";

/**
 * /prudent/entries — admin / data-management view.
 *
 * Searchable, sortable table of every logged entry with bulk select,
 * inline delete confirmation, and direct export. Intentionally denser
 * than /thread — this is the spreadsheet surface.
 */

import { useMemo, useState } from "react";
import { useEngine } from "../_components/engine-context";
import { fmtShortDate, fmtClockTime } from "../_components/shell";
import type { StoredEntry } from "../storage";

const ALL_TAGS = [
  "low", "tension", "energy", "flat", "work", "move", "food",
  "body", "quiet", "rest", "social", "rise", "high",
];

type SortKey = "date" | "events" | "avg" | "vol";
type SortDir = "asc" | "desc";

export default function EntriesPage() {
  const { entries, removeEntry, openReadOnly, exportEntries, openComposer } = useEngine();
  const [query, setQuery] = useState("");
  const [activeTags, setActiveTags] = useState<Set<string>>(new Set());
  const [fromDate, setFromDate] = useState("");
  const [toDate, setToDate] = useState("");
  const [sortKey, setSortKey] = useState<SortKey>("date");
  const [sortDir, setSortDir] = useState<SortDir>("desc");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [pendingDelete, setPendingDelete] = useState<string | null>(null);

  const filtered = useMemo(() => {
    let list = entries.slice();
    if (query.trim()) {
      const q = query.toLowerCase();
      list = list.filter((e) => e.text.toLowerCase().includes(q));
    }
    if (activeTags.size > 0) {
      list = list.filter((e) => e.events.some((ev) => activeTags.has(ev.tag)));
    }
    if (fromDate) {
      const from = new Date(fromDate).getTime();
      list = list.filter((e) => new Date(e.createdAt).getTime() >= from);
    }
    if (toDate) {
      const to = new Date(toDate).getTime() + 86400000;
      list = list.filter((e) => new Date(e.createdAt).getTime() < to);
    }
    const dir = sortDir === "asc" ? 1 : -1;
    list.sort((a, b) => {
      const av = sortValue(a, sortKey);
      const bv = sortValue(b, sortKey);
      if (av < bv) return -1 * dir;
      if (av > bv) return 1 * dir;
      return 0;
    });
    return list;
  }, [entries, query, activeTags, fromDate, toDate, sortKey, sortDir]);

  const filtersActive =
    query.trim() !== "" || activeTags.size > 0 || fromDate !== "" || toDate !== "";

  const kb = (new Blob([JSON.stringify(entries)]).size / 1024).toFixed(1);

  if (entries.length === 0) {
    return <EmptyAll onCompose={openComposer} />;
  }

  const toggleTag = (t: string) => {
    const next = new Set(activeTags);
    if (next.has(t)) next.delete(t);
    else next.add(t);
    setActiveTags(next);
  };

  const toggleSelect = (id: string) => {
    const next = new Set(selected);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    setSelected(next);
  };

  const toggleAllInView = () => {
    if (selected.size === filtered.length) setSelected(new Set());
    else setSelected(new Set(filtered.map((e) => e.id)));
  };

  const sortHandler = (k: SortKey) => () => {
    if (sortKey === k) setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    else {
      setSortKey(k);
      setSortDir(k === "date" ? "desc" : "desc");
    }
  };

  const deleteSelected = () => {
    if (!confirm(`Delete ${selected.size} entries? This cannot be undone.`)) return;
    for (const id of selected) removeEntry(id);
    setSelected(new Set());
  };

  const clearFilters = () => {
    setQuery("");
    setActiveTags(new Set());
    setFromDate("");
    setToDate("");
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 14, position: "relative" }}>
      {/* Top strip */}
      <section
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          background: "var(--panel)",
          border: "1px solid var(--line)",
          borderRadius: 10,
          padding: "14px 18px",
        }}
      >
        <div>
          <div style={{ fontSize: 13, fontWeight: 600, color: "var(--ink)" }}>
            {entries.length} entries
          </div>
          <div className="mono" style={{ fontSize: 11, color: "var(--muted)", marginTop: 2 }}>
            {kb} KB stored · local only
          </div>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <Btn onClick={exportEntries}>Export JSON</Btn>
          <Btn onClick={openComposer} kind="primary">＋ New entry</Btn>
        </div>
      </section>

      {/* Filter row */}
      <section
        style={{
          background: "var(--panel)",
          border: "1px solid var(--line)",
          borderRadius: 10,
          padding: "14px 18px",
          display: "flex",
          flexDirection: "column",
          gap: 10,
        }}
      >
        <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search narratives…"
            style={{
              flex: 1,
              border: "1px solid var(--line-mid)",
              borderRadius: 7,
              padding: "7px 12px",
              fontSize: 13,
              background: "var(--app-bg)",
            }}
          />
          <input
            type="date"
            value={fromDate}
            onChange={(e) => setFromDate(e.target.value)}
            style={{
              border: "1px solid var(--line-mid)",
              borderRadius: 7,
              padding: "6px 10px",
              fontSize: 12,
              background: "var(--app-bg)",
              fontFamily: "var(--mono)",
            }}
          />
          <span style={{ color: "var(--faint)" }}>→</span>
          <input
            type="date"
            value={toDate}
            onChange={(e) => setToDate(e.target.value)}
            style={{
              border: "1px solid var(--line-mid)",
              borderRadius: 7,
              padding: "6px 10px",
              fontSize: 12,
              background: "var(--app-bg)",
              fontFamily: "var(--mono)",
            }}
          />
          {filtersActive && (
            <button
              onClick={clearFilters}
              style={{ fontSize: 12, color: "var(--warm-strong)", fontWeight: 500 }}
            >
              Clear
            </button>
          )}
        </div>
        <div style={{ display: "flex", gap: 5, flexWrap: "wrap" }}>
          {ALL_TAGS.map((t) => (
            <TagToggle key={t} tag={t} active={activeTags.has(t)} onClick={() => toggleTag(t)} />
          ))}
        </div>
      </section>

      {/* Table */}
      <section
        style={{
          background: "var(--panel)",
          border: "1px solid var(--line)",
          borderRadius: 10,
          overflow: "hidden",
        }}
      >
        <table
          style={{
            width: "100%",
            borderCollapse: "collapse",
            fontSize: 13,
          }}
        >
          <thead>
            <tr
              style={{
                borderBottom: "1px solid var(--line)",
                background: "var(--hover)",
                fontSize: 11,
                color: "var(--muted)",
                textTransform: "uppercase",
                letterSpacing: "0.06em",
              }}
            >
              <Th style={{ width: 36 }}>
                <input
                  type="checkbox"
                  checked={filtered.length > 0 && selected.size === filtered.length}
                  onChange={toggleAllInView}
                />
              </Th>
              <ThSort active={sortKey === "date"} dir={sortDir} onClick={sortHandler("date")}>
                Date
              </ThSort>
              <ThSort
                active={sortKey === "events"}
                dir={sortDir}
                onClick={sortHandler("events")}
                align="right"
              >
                Events
              </ThSort>
              <ThSort
                active={sortKey === "avg"}
                dir={sortDir}
                onClick={sortHandler("avg")}
                align="right"
              >
                Avg
              </ThSort>
              <ThSort
                active={sortKey === "vol"}
                dir={sortDir}
                onClick={sortHandler("vol")}
                align="right"
              >
                σ
              </ThSort>
              <Th>Top tag</Th>
              <Th>Preview</Th>
              <Th style={{ width: 100, textAlign: "right" }}>Actions</Th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((entry, i) => {
              const vol = stdDev(entry.series.map((p) => p.v));
              const topTag = dominantTag(entry);
              const tone = valenceTone(entry.avg);
              return (
                <tr
                  key={entry.id}
                  onClick={() => openReadOnly(entry)}
                  style={{
                    borderBottom: "1px solid var(--line)",
                    background: i % 2 === 0 ? "transparent" : "var(--app-bg)",
                    cursor: "pointer",
                  }}
                >
                  <Td onClick={(e) => e.stopPropagation()}>
                    <input
                      type="checkbox"
                      checked={selected.has(entry.id)}
                      onChange={() => toggleSelect(entry.id)}
                    />
                  </Td>
                  <Td>
                    <div style={{ fontWeight: 500 }}>
                      {fmtShortDate(new Date(entry.createdAt))}
                    </div>
                    <div className="mono" style={{ fontSize: 11, color: "var(--muted)" }}>
                      {fmtClockTime(new Date(entry.createdAt))}
                    </div>
                  </Td>
                  <Td align="right" className="tnum">
                    {entry.events.length}
                  </Td>
                  <Td align="right">
                    <span
                      className="tnum"
                      style={{
                        padding: "2px 7px",
                        borderRadius: 999,
                        background: tone.bg,
                        color: tone.fg,
                        fontWeight: 600,
                      }}
                    >
                      {Math.round(entry.avg)}
                    </span>
                  </Td>
                  <Td align="right" className="tnum" style={{ color: "var(--muted)" }}>
                    {vol.toFixed(1)}
                  </Td>
                  <Td>
                    <span
                      style={{
                        display: "inline-flex",
                        alignItems: "center",
                        gap: 5,
                        fontSize: 12,
                        color: "var(--muted)",
                      }}
                    >
                      <span
                        style={{
                          width: 7,
                          height: 7,
                          borderRadius: "50%",
                          background: tagColor(topTag),
                        }}
                      />
                      {topTag}
                    </span>
                  </Td>
                  <Td>
                    <span
                      className="serif"
                      style={{
                        fontFamily: "var(--serif)",
                        fontStyle: "italic",
                        color: "var(--muted)",
                        fontSize: 13,
                      }}
                    >
                      {entry.text.slice(0, 80)}
                      {entry.text.length > 80 ? "…" : ""}
                    </span>
                  </Td>
                  <Td
                    align="right"
                    onClick={(e) => e.stopPropagation()}
                    style={{ whiteSpace: "nowrap" }}
                  >
                    {pendingDelete === entry.id ? (
                      <>
                        <IconBtn
                          title="Confirm"
                          onClick={() => {
                            removeEntry(entry.id);
                            setPendingDelete(null);
                          }}
                          color="var(--warm-strong)"
                        >
                          ✓
                        </IconBtn>
                        <IconBtn title="Cancel" onClick={() => setPendingDelete(null)}>
                          ✕
                        </IconBtn>
                      </>
                    ) : (
                      <>
                        <IconBtn title="View" onClick={() => openReadOnly(entry)}>
                          👁
                        </IconBtn>
                        <IconBtn title="Delete" onClick={() => setPendingDelete(entry.id)}>
                          🗑
                        </IconBtn>
                      </>
                    )}
                  </Td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {filtered.length === 0 && (
          <div
            style={{
              padding: "48px 20px",
              textAlign: "center",
              color: "var(--muted)",
              fontSize: 13,
            }}
          >
            No matches. Try clearing filters.
          </div>
        )}
      </section>

      {/* Bulk action bar */}
      {selected.size > 0 && (
        <div
          style={{
            position: "sticky",
            bottom: 18,
            alignSelf: "center",
            background: "var(--ink)",
            color: "var(--app-bg)",
            padding: "10px 16px",
            borderRadius: 10,
            boxShadow: "0 10px 30px -12px rgba(0,0,0,0.35)",
            display: "flex",
            alignItems: "center",
            gap: 14,
            fontSize: 13,
          }}
        >
          <span>{selected.size} selected</span>
          <button
            onClick={() => setSelected(new Set())}
            style={{ fontSize: 12, color: "var(--faint)" }}
          >
            Clear
          </button>
          <div style={{ width: 1, height: 14, background: "rgba(255,255,255,0.2)" }} />
          <button onClick={deleteSelected} style={{ color: "#FCA5A5", fontWeight: 500 }}>
            Delete selected
          </button>
        </div>
      )}
    </div>
  );
}

// ─── Helpers ──────────────────────────────────────────────────────────

function sortValue(e: StoredEntry, k: SortKey): number {
  if (k === "date") return new Date(e.createdAt).getTime();
  if (k === "events") return e.events.length;
  if (k === "avg") return e.avg;
  return stdDev(e.series.map((p) => p.v));
}

function stdDev(values: number[]): number {
  if (values.length < 2) return 0;
  const m = values.reduce((a, b) => a + b, 0) / values.length;
  return Math.sqrt(values.reduce((a, b) => a + (b - m) ** 2, 0) / values.length);
}

function dominantTag(e: StoredEntry): string {
  const m = new Map<string, number>();
  for (const ev of e.events) m.set(ev.tag, (m.get(ev.tag) ?? 0) + Math.abs(ev.delta));
  let best = "—";
  let bestV = 0;
  for (const [t, v] of m) if (v > bestV) { best = t; bestV = v; }
  return best;
}

function valenceTone(v: number): { bg: string; fg: string } {
  if (v >= 60) return { bg: "rgba(22,163,74,0.12)", fg: "var(--green)" };
  if (v >= 40) return { bg: "rgba(156,163,175,0.18)", fg: "var(--muted)" };
  return { bg: "rgba(249,115,22,0.12)", fg: "var(--warm-strong)" };
}

function tagColor(tag: string): string {
  const palette = ["#3B82F6", "#F97316", "#16A34A", "#7A4789", "#3D7B87", "#B6A13A", "#8A8F96"];
  let h = 0;
  for (let i = 0; i < tag.length; i++) h = (h * 31 + tag.charCodeAt(i)) >>> 0;
  return palette[h % palette.length];
}

// ─── Small UI pieces ──────────────────────────────────────────────────

function Btn({
  children,
  onClick,
  kind = "secondary",
}: {
  children: React.ReactNode;
  onClick: () => void;
  kind?: "primary" | "secondary";
}) {
  const style: React.CSSProperties =
    kind === "primary"
      ? { background: "var(--ink)", color: "var(--app-bg)" }
      : { background: "var(--panel)", color: "var(--ink)", border: "1px solid var(--line-mid)" };
  return (
    <button
      onClick={onClick}
      style={{ padding: "8px 14px", borderRadius: 7, fontSize: 13, fontWeight: 500, ...style }}
    >
      {children}
    </button>
  );
}

function TagToggle({ tag, active, onClick }: { tag: string; active: boolean; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      style={{
        fontSize: 11,
        padding: "4px 9px",
        borderRadius: 5,
        background: active ? tagColor(tag) : "var(--hover)",
        color: active ? "#fff" : "var(--muted)",
        fontWeight: active ? 600 : 500,
        transition: "background 100ms",
      }}
    >
      {tag}
    </button>
  );
}

function Th({
  children,
  style,
  align,
}: {
  children: React.ReactNode;
  style?: React.CSSProperties;
  align?: "right";
}) {
  return (
    <th style={{ padding: "10px 14px", textAlign: align ?? "left", fontWeight: 600, ...style }}>
      {children}
    </th>
  );
}

function ThSort({
  children,
  active,
  dir,
  onClick,
  align,
}: {
  children: React.ReactNode;
  active: boolean;
  dir: SortDir;
  onClick: () => void;
  align?: "right";
}) {
  return (
    <th
      onClick={onClick}
      style={{
        padding: "10px 14px",
        textAlign: align ?? "left",
        fontWeight: 600,
        cursor: "pointer",
        color: active ? "var(--ink)" : undefined,
        userSelect: "none",
      }}
    >
      {children} {active && <span style={{ fontSize: 9 }}>{dir === "asc" ? "▲" : "▼"}</span>}
    </th>
  );
}

function Td({
  children,
  align,
  onClick,
  className,
  style,
}: {
  children: React.ReactNode;
  align?: "right";
  onClick?: (e: React.MouseEvent) => void;
  className?: string;
  style?: React.CSSProperties;
}) {
  return (
    <td
      onClick={onClick}
      className={className}
      style={{ padding: "12px 14px", textAlign: align ?? "left", ...style }}
    >
      {children}
    </td>
  );
}

function IconBtn({
  children,
  onClick,
  title,
  color,
}: {
  children: React.ReactNode;
  onClick: () => void;
  title?: string;
  color?: string;
}) {
  return (
    <button
      onClick={onClick}
      title={title}
      style={{
        padding: "5px 8px",
        borderRadius: 5,
        fontSize: 13,
        color: color ?? "var(--muted)",
        marginLeft: 2,
      }}
    >
      {children}
    </button>
  );
}

function EmptyAll({ onCompose }: { onCompose: () => void }) {
  return (
    <section
      style={{
        background: "var(--panel)",
        border: "1px solid var(--line)",
        borderRadius: 10,
        padding: "72px 24px",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        gap: 14,
        textAlign: "center",
      }}
    >
      <p className="serif" style={{ fontFamily: "var(--serif)", fontSize: 22, fontStyle: "italic" }}>
        No entries yet.
      </p>
      <p style={{ fontSize: 13, color: "var(--muted)" }}>
        Once you log something, it'll be manageable here.
      </p>
      <button
        onClick={onCompose}
        style={{
          marginTop: 8,
          background: "var(--ink)",
          color: "var(--app-bg)",
          padding: "10px 18px",
          borderRadius: 8,
          fontSize: 13,
          fontWeight: 500,
        }}
      >
        ＋ Log your first
      </button>
    </section>
  );
}
