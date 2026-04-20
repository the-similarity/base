"use client";

/**
 * /prudent/tags — taxonomy view across all stored entries.
 *
 * Aggregates tags from every entry.event and shows their relative
 * weight (donut), their lean (positive vs negative), their cadence
 * across time, and lets the user drill into entries containing a
 * selected tag.
 */

import { useMemo, useState } from "react";
import { useEngine } from "../_components/engine-context";
import { fmtShortDate } from "../_components/shell";
import type { StoredEntry } from "../storage";

const ALL_TAGS = [
  "low", "tension", "energy", "flat", "work", "move", "food",
  "body", "quiet", "rest", "social", "rise", "high",
];

const PALETTE = ["#3B82F6", "#F97316", "#16A34A", "#7A4789", "#3D7B87", "#B6A13A", "#8A8F96"];

interface TagRow {
  tag: string;
  count: number;
  posMag: number;
  negMag: number;
  days: Set<string>;
  color: string;
}

export default function TagsPage() {
  const { entries, openComposer, openReadOnly } = useEngine();
  const [active, setActive] = useState<string | null>(null);
  const [sortBy, setSortBy] = useState<"count" | "magnitude" | "lean">("count");

  const rows = useMemo(() => buildRows(entries), [entries]);
  const total = rows.reduce((s, r) => s + r.count, 0);
  const sorted = useMemo(() => {
    const list = rows.slice();
    if (sortBy === "count") list.sort((a, b) => b.count - a.count);
    if (sortBy === "magnitude") list.sort((a, b) => b.posMag + b.negMag - (a.posMag + a.negMag));
    if (sortBy === "lean") list.sort((a, b) => magLean(b) - magLean(a));
    return list;
  }, [rows, sortBy]);

  const filtered = active
    ? entries.filter((e) => e.events.some((ev) => ev.tag === active))
    : [];

  const topCommon = sorted[0];
  const topUplift = rows
    .filter((r) => r.count > 0)
    .sort((a, b) => r_avgPos(b) - r_avgPos(a))[0];
  const topDrain = rows
    .filter((r) => r.count > 0)
    .sort((a, b) => r_avgNeg(a) - r_avgNeg(b))[0];

  if (entries.length === 0) return <EmptyState onCompose={openComposer} />;

  return (
    <div className="prudent-tags-page" style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      {/*
        Responsive rules below are scoped to .prudent-tags-page so they don't
        leak into other /prudent surfaces. Breakpoints chosen empirically:
          - 1100px: donut hero stacks vertically (340px + text no longer fits
            comfortably alongside a 1fr column inside the panel padding).
          - 900px: taxonomy row collapses from a 6-column grid to a 2-row
            layout — the lean/magnitude/timeline bars wrap underneath the
            tag label so nothing gets squeezed below 40px.
          - 640px: donut shrinks so it stops overflowing on phones.
      */}
      {/* Hero: donut + headline stats */}
      <section
        className="tags-hero"
        style={{
          background: "var(--panel)",
          border: "1px solid var(--line)",
          borderRadius: 10,
          padding: "22px 26px",
          display: "grid",
          gridTemplateColumns: "340px 1fr",
          gap: 32,
          alignItems: "center",
        }}
      >
        <ConcentricDonut rows={sorted} total={total} count={entries.length} />
        <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          {topCommon && (
            <HeroStat
              label="Most common"
              tag={topCommon.tag}
              detail={`${topCommon.count} events · ${Math.round((topCommon.count / total) * 100)}% of all`}
            />
          )}
          {topUplift && (
            <HeroStat
              label="Most uplifting"
              tag={topUplift.tag}
              detail={`avg +${r_avgPos(topUplift).toFixed(1)} · ${topUplift.count} events`}
              positive
            />
          )}
          {topDrain && (
            <HeroStat
              label="Most draining"
              tag={topDrain.tag}
              detail={`avg ${r_avgNeg(topDrain).toFixed(1)} · ${topDrain.count} events`}
              negative
            />
          )}
        </div>
      </section>

      {/* Taxonomy table */}
      <section
        style={{
          background: "var(--panel)",
          border: "1px solid var(--line)",
          borderRadius: 10,
          padding: "18px 20px",
        }}
      >
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14 }}>
          <div>
            <div style={{ fontSize: 14, fontWeight: 600 }}>Taxonomy</div>
            <div style={{ fontSize: 11, color: "var(--muted)", marginTop: 2 }}>
              {rows.length} tags · {total} total events · click to explore
            </div>
          </div>
          <div style={{ display: "flex", gap: 4 }}>
            {(["count", "magnitude", "lean"] as const).map((k) => (
              <button
                key={k}
                onClick={() => setSortBy(k)}
                style={{
                  fontSize: 11,
                  padding: "5px 10px",
                  borderRadius: 6,
                  background: sortBy === k ? "var(--ink)" : "var(--hover)",
                  color: sortBy === k ? "var(--app-bg)" : "var(--muted)",
                  fontWeight: 500,
                }}
              >
                {k}
              </button>
            ))}
          </div>
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
          {sorted.map((r) => (
            <TaxRow
              key={r.tag}
              row={r}
              total={total}
              active={active === r.tag}
              onClick={() => setActive(active === r.tag ? null : r.tag)}
            />
          ))}
        </div>
      </section>

      {/* Filtered entries */}
      {active && (
        <section
          style={{
            background: "var(--panel)",
            border: "1px solid var(--line)",
            borderRadius: 10,
            padding: "18px 20px",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12 }}>
            <span style={{ fontSize: 14, fontWeight: 600 }}>Entries with</span>
            <span
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: 6,
                fontSize: 12,
                fontWeight: 600,
                padding: "3px 9px",
                borderRadius: 5,
                background: tagColor(active),
                color: "#fff",
              }}
            >
              {active}
            </span>
            <span style={{ fontSize: 11, color: "var(--muted)" }}>
              · {filtered.length} {filtered.length === 1 ? "entry" : "entries"}
            </span>
            <button
              onClick={() => setActive(null)}
              style={{ marginLeft: "auto", fontSize: 11, color: "var(--warm-strong)" }}
            >
              Clear
            </button>
          </div>
          {filtered.length === 0 ? (
            <div style={{ fontSize: 12, color: "var(--faint)", padding: "20px 0" }}>
              No entries match this tag yet.
            </div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              {filtered.slice(0, 20).map((e) => (
                <MiniEntry key={e.id} entry={e} onClick={() => openReadOnly(e)} />
              ))}
            </div>
          )}
        </section>
      )}
      {!active && (
        <section
          style={{
            background: "var(--panel)",
            border: "1px dashed var(--line-mid)",
            borderRadius: 10,
            padding: "24px 20px",
            textAlign: "center",
            fontSize: 12,
            color: "var(--muted)",
          }}
        >
          Pick a tag above to see entries containing it.
        </section>
      )}

      {/*
        Scoped responsive + dark-mode overrides for this page.
        Using a <style jsx>-style scoped block keeps these rules from leaking
        into sibling /prudent routes. Each selector is prefixed with the page
        wrapper class so specificity resolves cleanly above the inline style
        properties (inline `style` on each element would otherwise win; but
        these rules target grid-template-columns, which is also inline, so we
        use `!important` selectively where we need to override inline grids).
      */}
      <style>{`
        /* Donut hero: stack donut above copy below 1100px so 340px donut
           doesn't starve the stats column. */
        @media (max-width: 1100px) {
          .prudent-tags-page .tags-hero {
            grid-template-columns: 1fr !important;
            justify-items: center;
            text-align: center;
            gap: 20px !important;
          }
        }
        /* Shrink donut SVG container on very narrow viewports so it doesn't
           cause horizontal overflow on mobile. */
        @media (max-width: 640px) {
          .prudent-tags-page .tags-hero > div:first-child {
            width: 260px !important;
            height: 260px !important;
          }
          .prudent-tags-page .tags-hero > div:first-child svg {
            width: 260px;
            height: 260px;
          }
        }
        /* Taxonomy row reflow: at 900px collapse the 6-col grid into a
           two-row layout where tag name/count sit on top and the three
           bars/timeline share the width below. */
        @media (max-width: 900px) {
          .prudent-tags-page .tax-row {
            grid-template-columns: 1fr 50px 40px !important;
            grid-template-rows: auto auto;
            row-gap: 8px !important;
          }
          .prudent-tags-page .tax-row > .tax-lean,
          .prudent-tags-page .tax-row > .tax-mag,
          .prudent-tags-page .tax-row > .tax-timeline {
            grid-column: 1 / -1;
          }
        }
        /* Dark-mode polish: var-driven tones already cascade through the
           card backgrounds, but the rgba overlays used in valence pills
           are tuned for light mode and disappear against a #17191C panel.
           Lift their opacity so they remain legible in dark. */
        .prudent-root.prudent-dark .prudent-tags-page .valence-pos {
          background: rgba(34,197,94,0.18) !important;
        }
        .prudent-root.prudent-dark .prudent-tags-page .valence-neg {
          background: rgba(249,115,22,0.22) !important;
        }
      `}</style>
    </div>
  );
}

// ─── Donut ───────────────────────────────────────────────────────────
// Concentric stroked arcs with small angular gaps. Inner radius is large
// so the donut reads as rings, not a pie.

function ConcentricDonut({ rows, total, count }: { rows: TagRow[]; total: number; count: number }) {
  const cx = 170;
  const cy = 170;
  const radius = 130;
  const thickness = 22;
  const circumference = 2 * Math.PI * radius;
  const gap = 3; // degrees

  let offset = -90;
  const segments = rows.map((r) => {
    const pct = r.count / (total || 1);
    const angle = pct * 360 - gap;
    const seg = { start: offset, length: Math.max(angle, 0), color: r.color, pct };
    offset += pct * 360;
    return seg;
  });

  return (
    <div style={{ position: "relative", width: 340, height: 340 }}>
      <svg width={340} height={340}>
        {segments.map((s, i) => (
          <circle
            key={i}
            cx={cx}
            cy={cy}
            r={radius}
            fill="none"
            stroke={s.color}
            strokeWidth={thickness}
            strokeLinecap="round"
            strokeDasharray={`${(s.length / 360) * circumference} ${circumference}`}
            transform={`rotate(${s.start} ${cx} ${cy})`}
            opacity={0.92}
          />
        ))}
      </svg>
      <div
        style={{
          position: "absolute",
          inset: 0,
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          pointerEvents: "none",
        }}
      >
        <div style={{ fontSize: 11, color: "var(--muted)" }}>Events weighted</div>
        <div
          className="tnum"
          style={{ fontSize: 40, fontWeight: 600, color: "var(--ink)", letterSpacing: "-0.02em" }}
        >
          {total}
        </div>
        <div style={{ fontSize: 11, color: "var(--faint)" }}>across {count} days</div>
      </div>
    </div>
  );
}

// ─── Taxonomy row ────────────────────────────────────────────────────

function TaxRow({
  row,
  total,
  active,
  onClick,
}: {
  row: TagRow;
  total: number;
  active: boolean;
  onClick: () => void;
}) {
  const pct = Math.round((row.count / (total || 1)) * 100);
  const leanPos = row.posMag / (row.posMag + row.negMag || 1);

  return (
    <button
      onClick={onClick}
      className="tax-row"
      style={{
        display: "grid",
        gridTemplateColumns: "100px 60px 120px 120px 1fr 40px",
        gap: 14,
        alignItems: "center",
        padding: "10px 12px",
        borderRadius: 7,
        background: active ? "var(--hover)" : "transparent",
        textAlign: "left",
        transition: "background 120ms",
      }}
    >
      <span style={{ display: "inline-flex", alignItems: "center", gap: 8 }}>
        <span style={{ width: 10, height: 10, borderRadius: 3, background: row.color }} />
        <span
          style={{
            fontSize: 13,
            fontWeight: active ? 600 : 500,
            color: "var(--ink)",
            textTransform: "capitalize",
          }}
        >
          {row.tag}
        </span>
      </span>
      <span className="tnum" style={{ fontSize: 13, color: "var(--muted)" }}>
        {row.count}
      </span>
      <div className="tax-lean"><LeanBar posShare={leanPos} /></div>
      <div className="tax-mag"><MagnitudeBar total={row.posMag + row.negMag} max={maxMagnitude(row)} color={row.color} /></div>
      <div className="tax-timeline"><Timeline days={row.days} /></div>
      <span className="tnum" style={{ fontSize: 11, color: "var(--muted)", textAlign: "right" }}>
        {pct}%
      </span>
    </button>
  );
}

function LeanBar({ posShare }: { posShare: number }) {
  // Centered bar: midline at 50%. Green extends right, warm extends left.
  const posWidth = posShare * 50;
  const negWidth = (1 - posShare) * 50;
  return (
    <div style={{ position: "relative", height: 8, background: "var(--hover)", borderRadius: 4 }}>
      <div
        style={{
          position: "absolute",
          left: `${50 - negWidth}%`,
          top: 0,
          bottom: 0,
          width: `${negWidth}%`,
          background: "var(--warm-strong)",
          borderRadius: "4px 0 0 4px",
          opacity: 0.8,
        }}
      />
      <div
        style={{
          position: "absolute",
          left: "50%",
          top: 0,
          bottom: 0,
          width: `${posWidth}%`,
          background: "var(--green)",
          borderRadius: "0 4px 4px 0",
          opacity: 0.8,
        }}
      />
      <div
        style={{
          position: "absolute",
          left: "50%",
          top: -1,
          bottom: -1,
          width: 1,
          background: "var(--ink)",
          opacity: 0.2,
        }}
      />
    </div>
  );
}

function MagnitudeBar({ total, max, color }: { total: number; max: number; color: string }) {
  const w = Math.min(1, total / (max || 1));
  return (
    <div style={{ height: 8, background: "var(--hover)", borderRadius: 4, position: "relative", overflow: "hidden" }}>
      <div
        style={{
          position: "absolute",
          left: 0,
          top: 0,
          bottom: 0,
          width: `${w * 100}%`,
          background: color,
          borderRadius: 4,
          opacity: 0.8,
        }}
      />
    </div>
  );
}

function Timeline({ days }: { days: Set<string> }) {
  const today = new Date();
  const slots: boolean[] = [];
  for (let d = 29; d >= 0; d--) {
    const k = new Date(today.getTime() - d * 86400000).toISOString().slice(0, 10);
    slots.push(days.has(k));
  }
  return (
    <div style={{ display: "flex", gap: 2, height: 14, alignItems: "center" }}>
      {slots.map((on, i) => (
        <div
          key={i}
          style={{
            flex: 1,
            height: on ? 10 : 3,
            background: on ? "var(--accent)" : "var(--line-mid)",
            borderRadius: 1,
          }}
        />
      ))}
    </div>
  );
}

// ─── Mini entry card (inside filtered panel) ─────────────────────────

function MiniEntry({ entry, onClick }: { entry: StoredEntry; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      style={{
        display: "grid",
        gridTemplateColumns: "100px 1fr 60px",
        gap: 14,
        alignItems: "center",
        padding: "10px 14px",
        borderRadius: 7,
        border: "1px solid var(--line)",
        background: "var(--app-bg)",
        textAlign: "left",
        cursor: "pointer",
      }}
    >
      <span style={{ fontSize: 12, fontWeight: 500, color: "var(--muted)" }}>
        {fmtShortDate(new Date(entry.createdAt))}
      </span>
      <span
        className="serif"
        style={{
          fontFamily: "var(--serif)",
          fontStyle: "italic",
          fontSize: 13,
          color: "var(--ink)",
          whiteSpace: "nowrap",
          overflow: "hidden",
          textOverflow: "ellipsis",
        }}
      >
        {entry.text.slice(0, 120)}
      </span>
      <span
        className="tnum"
        style={{
          fontSize: 12,
          fontWeight: 600,
          color: entry.avg >= 50 ? "var(--green)" : "var(--warm-strong)",
          textAlign: "right",
        }}
      >
        {Math.round(entry.avg)}
      </span>
    </button>
  );
}

// ─── Hero stat row ───────────────────────────────────────────────────

function HeroStat({
  label,
  tag,
  detail,
  positive,
  negative,
}: {
  label: string;
  tag: string;
  detail: string;
  positive?: boolean;
  negative?: boolean;
}) {
  const accent = positive ? "var(--green)" : negative ? "var(--warm-strong)" : "var(--ink)";
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
      <div style={{ fontSize: 11, color: "var(--muted)", fontWeight: 500 }}>{label}</div>
      <div style={{ display: "flex", alignItems: "baseline", gap: 8 }}>
        <span
          style={{
            fontSize: 22,
            fontWeight: 600,
            color: accent,
            textTransform: "capitalize",
            letterSpacing: "-0.01em",
          }}
        >
          {tag}
        </span>
        <span style={{ fontSize: 12, color: "var(--muted)" }}>{detail}</span>
      </div>
    </div>
  );
}

function EmptyState({ onCompose }: { onCompose: () => void }) {
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
        Tags emerge from your narratives.
      </p>
      <p style={{ fontSize: 13, color: "var(--muted)", maxWidth: 420, lineHeight: 1.55 }}>
        Write a few entries and the engine will surface what drives your days.
      </p>
      <button
        onClick={onCompose}
        style={{
          marginTop: 8,
          background: "var(--warm)",
          color: "#fff",
          padding: "10px 18px",
          borderRadius: 8,
          fontSize: 13,
          fontWeight: 500,
        }}
      >
        ＋ Log first entry
      </button>
    </section>
  );
}

// ─── Helpers ─────────────────────────────────────────────────────────

function buildRows(entries: StoredEntry[]): TagRow[] {
  const agg = new Map<string, TagRow>();
  for (const e of entries) {
    const dayKey = new Date(e.createdAt).toISOString().slice(0, 10);
    for (const ev of e.events) {
      const row = agg.get(ev.tag) ?? {
        tag: ev.tag,
        count: 0,
        posMag: 0,
        negMag: 0,
        days: new Set<string>(),
        color: tagColor(ev.tag),
      };
      row.count++;
      if (ev.delta >= 0) row.posMag += ev.delta;
      else row.negMag += Math.abs(ev.delta);
      row.days.add(dayKey);
      agg.set(ev.tag, row);
    }
  }
  return Array.from(agg.values());
}

function maxMagnitude(r: TagRow): number {
  // Normalize against typical single-tag max; picks 100 as a reasonable ceiling
  // for the magnitude bar so bars feel consistent across tags.
  return Math.max(100, r.posMag + r.negMag);
}

function r_avgPos(r: TagRow): number {
  return r.count ? r.posMag / r.count : 0;
}
function r_avgNeg(r: TagRow): number {
  return r.count ? -r.negMag / r.count : 0;
}
function magLean(r: TagRow): number {
  return Math.abs(r.posMag - r.negMag);
}

function tagColor(tag: string): string {
  const idx = ALL_TAGS.indexOf(tag);
  return idx >= 0 ? PALETTE[idx % PALETTE.length] : PALETTE[0];
}
