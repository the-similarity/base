"use client";

/**
 * /prudent/engine — "look under the hood" diagnostics surface.
 *
 * Makes the engine feel tangible: shows parse source (regex vs Claude),
 * the 21-pattern lexicon as a visual taxonomy, a live parse playground,
 * and the API integration story. Clinical, technical, confidence-building.
 */

import { useEffect, useMemo, useState } from "react";
import { useParsedNarrative } from "../use-parse";
import { fmtClockTime } from "../_components/shell";

// ─── Lexicon (mirrored from engine.ts — keep in sync manually until engine
// exports it). Single source of truth for the rule-based v0.3 parser.
const LEXICON: Array<{ re: string; d: number; tag: string; cert: number }> = [
  { re: "/(terrible|awful|devastat\\w*|miserable|wrecked|shattered)/i", d: -28, tag: "low", cert: 0.9 },
  { re: "/(bad|rough|hard|tough|difficult|painful|stressful)/i", d: -14, tag: "low", cert: 0.75 },
  { re: "/(tired|exhausted|drained|sluggish|heavy|groggy)/i", d: -10, tag: "energy", cert: 0.7 },
  { re: "/(anxious|worried|nervous|on edge|panicky)/i", d: -12, tag: "tension", cert: 0.8 },
  { re: "/(annoyed|frustrated|irritated|angry|pissed)/i", d: -11, tag: "tension", cert: 0.8 },
  { re: "/(sad|down|low|blue|gloomy|melanchol\\w*)/i", d: -13, tag: "low", cert: 0.8 },
  { re: "/(lonely|isolated|alone)/i", d: -10, tag: "low", cert: 0.75 },
  { re: "/(bored|flat|dull|meh|okay|ok|fine)/i", d: -2, tag: "flat", cert: 0.5 },
  { re: "/(work\\w*|meeting|email\\w*|standup|review)/i", d: -3, tag: "work", cert: 0.4 },
  { re: "/(commut\\w*|subway|traffic|drive|bus)/i", d: -2, tag: "move", cert: 0.4 },
  { re: "/(lunch|dinner|breakfast|coffee|ate|eating|food)/i", d: 2, tag: "food", cert: 0.5 },
  { re: "/(walk\\w*|run|gym|yoga|stretch\\w*|bike|ride)/i", d: 7, tag: "body", cert: 0.7 },
  { re: "/(read\\w*|book|music|listen\\w*|podcast)/i", d: 4, tag: "quiet", cert: 0.6 },
  { re: "/(nap|slept|sleep|rest\\w*)/i", d: 5, tag: "rest", cert: 0.6 },
  { re: "/(friend|texted|called|saw|met|talked to|hug\\w*)/i", d: 9, tag: "social", cert: 0.75 },
  { re: "/(laugh\\w*|joke|funny|smile\\w*)/i", d: 10, tag: "social", cert: 0.75 },
  { re: "/(better|improv\\w*|lift\\w*|rebound\\w*|recover\\w*)/i", d: 12, tag: "rise", cert: 0.8 },
  { re: "/(good|nice|pleasant|calm|peaceful)/i", d: 8, tag: "rise", cert: 0.7 },
  { re: "/(great|wonderful|amazing|brilliant|love\\w*|happy|joy\\w*)/i", d: 18, tag: "high", cert: 0.85 },
  { re: "/(breakthrough|flow|focused|productive|clicked)/i", d: 16, tag: "high", cert: 0.85 },
  { re: "/(excited|energized|alive|thrilled)/i", d: 15, tag: "high", cert: 0.8 },
];

const ALL_TAGS = Array.from(new Set(LEXICON.map((l) => l.tag)));

interface ParseLog {
  id: number;
  at: Date;
  text: string;
  source: string;
  events: number;
  ms: number;
}

export default function EnginePage() {
  const [text, setText] = useState(
    "slow morning, great lunch, flow afternoon — friend called, calm night.",
  );
  const [filterTag, setFilterTag] = useState<string | null>(null);
  const [log, setLog] = useState<ParseLog[]>([]);
  const [logSeq, setLogSeq] = useState(0);

  const parse = useParsedNarrative(text, { debounceMs: 180 });

  // Record parses into an in-session log (not persisted).
  useEffect(() => {
    if (parse.source === "idle" || parse.loading) return;
    setLog((prev) => {
      const entry: ParseLog = {
        id: logSeq,
        at: new Date(),
        text: text.slice(0, 90),
        source: parse.source,
        events: parse.events.length,
        ms: 0,
      };
      const next = [entry, ...prev].slice(0, 20);
      return next;
    });
    setLogSeq((n) => n + 1);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [parse.source, parse.events.length]);

  const rows = useMemo(() => {
    let list = LEXICON.slice();
    if (filterTag) list = list.filter((l) => l.tag === filterTag);
    list.sort((a, b) => Math.abs(b.d) - Math.abs(a.d));
    return list;
  }, [filterTag]);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
      {/* Status row */}
      <section
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(4, 1fr)",
          gap: 14,
        }}
      >
        <StatusCard
          label="Parse source"
          value={parse.source}
          accent={parse.source === "api" ? "var(--accent)" : "var(--muted)"}
          detail={parse.loading ? "resolving…" : "live"}
        />
        <StatusCard
          label="API status"
          value="not set"
          accent="var(--warm-strong)"
          detail="regex fallback active"
          mono
        />
        <StatusCard
          label="Last parse"
          value={parse.events.length}
          accent="var(--ink)"
          detail={`${parse.events.length} events`}
        />
        <StatusCard
          label="Lexicon"
          value={LEXICON.length}
          accent="var(--ink)"
          detail={`${ALL_TAGS.length} tags · rule-based v0.3`}
        />
      </section>

      {/* Lexicon */}
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
            <div style={{ fontSize: 14, fontWeight: 600 }}>Lexicon</div>
            <div style={{ fontSize: 11, color: "var(--muted)", marginTop: 2 }}>
              21 regex patterns · 13 tags · click a tag to filter
            </div>
          </div>
          {filterTag && (
            <button
              onClick={() => setFilterTag(null)}
              style={{ fontSize: 12, color: "var(--warm-strong)", fontWeight: 500 }}
            >
              Clear filter
            </button>
          )}
        </div>
        <div style={{ display: "flex", gap: 5, flexWrap: "wrap", marginBottom: 16 }}>
          {ALL_TAGS.map((t) => (
            <button
              key={t}
              onClick={() => setFilterTag(filterTag === t ? null : t)}
              style={{
                fontSize: 11,
                padding: "4px 9px",
                borderRadius: 5,
                background: filterTag === t ? tagColor(t) : "var(--hover)",
                color: filterTag === t ? "#fff" : "var(--muted)",
                fontWeight: filterTag === t ? 600 : 500,
              }}
            >
              {t}
            </button>
          ))}
        </div>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
          <thead>
            <tr style={{ fontSize: 10, color: "var(--muted)", textTransform: "uppercase", letterSpacing: "0.08em" }}>
              <th style={{ textAlign: "left", padding: "6px 10px", fontWeight: 600 }}>Match pattern</th>
              <th style={{ textAlign: "left", padding: "6px 10px", fontWeight: 600, width: 100 }}>Tag</th>
              <th style={{ textAlign: "right", padding: "6px 10px", fontWeight: 600, width: 80 }}>Δ</th>
              <th style={{ textAlign: "left", padding: "6px 10px", fontWeight: 600, width: 140 }}>Certainty</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={i} style={{ borderTop: "1px solid var(--line)" }}>
                <td
                  className="mono"
                  style={{ padding: "8px 10px", color: "var(--ink)", fontSize: 11 }}
                >
                  {r.re}
                </td>
                <td style={{ padding: "8px 10px" }}>
                  <span
                    style={{
                      display: "inline-flex",
                      alignItems: "center",
                      gap: 5,
                      fontSize: 11,
                      color: "var(--muted)",
                    }}
                  >
                    <span
                      style={{ width: 7, height: 7, borderRadius: "50%", background: tagColor(r.tag) }}
                    />
                    {r.tag}
                  </span>
                </td>
                <td
                  className="tnum"
                  style={{
                    textAlign: "right",
                    padding: "8px 10px",
                    fontWeight: 600,
                    color: r.d >= 0 ? "var(--green)" : "var(--warm-strong)",
                  }}
                >
                  {r.d >= 0 ? "+" : ""}
                  {r.d}
                </td>
                <td style={{ padding: "8px 10px" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <div
                      style={{
                        flex: 1,
                        height: 4,
                        borderRadius: 2,
                        background: "var(--hover)",
                        position: "relative",
                        overflow: "hidden",
                      }}
                    >
                      <div
                        style={{
                          position: "absolute",
                          left: 0,
                          top: 0,
                          bottom: 0,
                          width: `${r.cert * 100}%`,
                          background: "var(--accent)",
                          borderRadius: 2,
                        }}
                      />
                    </div>
                    <span className="mono tnum" style={{ fontSize: 10, color: "var(--muted)" }}>
                      {r.cert.toFixed(2)}
                    </span>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      {/* Playground */}
      <section
        style={{
          background: "var(--panel)",
          border: "1px solid var(--line)",
          borderRadius: 10,
          padding: "18px 20px",
          display: "grid",
          gridTemplateColumns: "1.3fr 1fr",
          gap: 18,
        }}
      >
        <div>
          <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 2 }}>Playground</div>
          <div style={{ fontSize: 11, color: "var(--muted)", marginBottom: 10 }}>
            Type a day — see it parsed in real time.
          </div>
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="Type a day to see it parsed…"
            style={{
              width: "100%",
              minHeight: 220,
              padding: 14,
              fontFamily: "var(--serif)",
              fontSize: 16,
              lineHeight: 1.6,
              border: "1px solid var(--line-mid)",
              borderRadius: 8,
              background: "var(--app-bg)",
              color: "var(--ink)",
              resize: "vertical",
            }}
          />
        </div>
        <div>
          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              marginBottom: 10,
            }}
          >
            <div style={{ fontSize: 13, fontWeight: 600 }}>Parsed events</div>
            <SourcePill source={parse.source} loading={parse.loading} />
          </div>
          <div
            style={{
              border: "1px dashed var(--line-mid)",
              borderRadius: 8,
              padding: 12,
              minHeight: 220,
              maxHeight: 280,
              overflow: "auto",
            }}
          >
            {parse.events.length === 0 && (
              <div
                style={{ fontSize: 12, color: "var(--faint)", textAlign: "center", padding: "60px 0" }}
              >
                No anchors detected.
              </div>
            )}
            {parse.events.map((ev, i) => (
              <div
                key={i}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 8,
                  padding: "7px 0",
                  borderTop: i === 0 ? "none" : "1px solid var(--line)",
                  fontSize: 12,
                }}
              >
                <span
                  style={{
                    width: 7,
                    height: 7,
                    borderRadius: "50%",
                    background: tagColor(ev.tag),
                    flexShrink: 0,
                  }}
                />
                <span
                  className="serif"
                  style={{
                    flex: 1,
                    fontStyle: "italic",
                    color: "var(--muted)",
                    whiteSpace: "nowrap",
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                  }}
                >
                  {ev.text.slice(0, 30)}
                </span>
                <span
                  style={{
                    fontSize: 10,
                    color: "var(--muted)",
                    padding: "1px 6px",
                    borderRadius: 4,
                    background: "var(--hover)",
                  }}
                >
                  {ev.tag}
                </span>
                <span
                  className="tnum"
                  style={{
                    fontSize: 11,
                    fontWeight: 600,
                    color: ev.delta > 0 ? "var(--green)" : "var(--warm-strong)",
                    width: 30,
                    textAlign: "right",
                  }}
                >
                  {ev.delta > 0 ? "+" : ""}
                  {ev.delta.toFixed(0)}
                </span>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* API integration snippet */}
      <section
        style={{
          background: "var(--panel)",
          border: "1px solid var(--line)",
          borderRadius: 10,
          padding: "18px 20px",
        }}
      >
        <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 2 }}>API integration</div>
        <div style={{ fontSize: 11, color: "var(--muted)", marginBottom: 12 }}>
          The API always returns <code>{"{events, series, source}"}</code>. When{" "}
          <code>ANTHROPIC_API_KEY</code> is set, responses come from Claude Sonnet 4.6 with
          prompt caching. Without it, the regex fallback runs in-process.
        </div>
        <pre
          className="mono"
          style={{
            background: "var(--hover)",
            padding: 16,
            borderRadius: 8,
            fontFamily: "var(--mono)",
            fontSize: 12,
            color: "var(--ink)",
            overflow: "auto",
            margin: 0,
          }}
        >{`curl -X POST http://localhost:3000/api/prudent/parse \\
  -H "Content-Type: application/json" \\
  -d '{"text": "slow morning, great lunch, flow afternoon"}'`}</pre>
      </section>

      {/* Recent parses log */}
      {log.length > 0 && (
        <section
          style={{
            background: "var(--panel)",
            border: "1px solid var(--line)",
            borderRadius: 10,
            padding: "18px 20px",
          }}
        >
          <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 2 }}>Recent parses</div>
          <div style={{ fontSize: 11, color: "var(--muted)", marginBottom: 10 }}>
            In-session only · {log.length} / 20
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
            {log.map((l) => (
              <div
                key={l.id}
                className="mono"
                style={{
                  display: "grid",
                  gridTemplateColumns: "110px 60px 1fr 50px",
                  gap: 10,
                  fontSize: 11,
                  color: "var(--muted)",
                  padding: "4px 0",
                  borderBottom: "1px solid var(--line)",
                }}
              >
                <span>{fmtClockTime(l.at)}</span>
                <span style={{ color: l.source === "api" ? "var(--accent)" : "var(--muted)" }}>
                  {l.source}
                </span>
                <span className="serif" style={{ fontStyle: "italic", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                  {l.text}
                </span>
                <span className="tnum" style={{ textAlign: "right" }}>
                  {l.events}ev
                </span>
              </div>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}

// ─── UI pieces ────────────────────────────────────────────────────────

function StatusCard({
  label,
  value,
  detail,
  accent,
  mono,
}: {
  label: string;
  value: string | number;
  detail: string;
  accent: string;
  mono?: boolean;
}) {
  return (
    <div
      style={{
        background: "var(--panel)",
        border: "1px solid var(--line)",
        borderRadius: 10,
        padding: "14px 16px",
      }}
    >
      <div style={{ fontSize: 11, color: "var(--muted)", fontWeight: 500 }}>{label}</div>
      <div
        className={mono ? "mono" : undefined}
        style={{
          fontSize: mono ? 18 : 26,
          fontWeight: 600,
          color: accent,
          marginTop: 6,
          letterSpacing: "-0.01em",
        }}
      >
        {value}
      </div>
      <div style={{ fontSize: 11, color: "var(--faint)", marginTop: 4 }}>{detail}</div>
    </div>
  );
}

function SourcePill({ source, loading }: { source: string; loading: boolean }) {
  const color = source === "api" ? "var(--accent)" : source === "idle" ? "var(--faint)" : "var(--muted)";
  return (
    <span
      className="mono"
      style={{
        fontSize: 10,
        padding: "3px 8px",
        borderRadius: 999,
        background: "var(--hover)",
        color,
        fontWeight: 600,
      }}
    >
      {loading ? "…" : source}
    </span>
  );
}

function tagColor(tag: string): string {
  const palette = ["#3B82F6", "#F97316", "#16A34A", "#7A4789", "#3D7B87", "#B6A13A", "#8A8F96"];
  const idx = ALL_TAGS.indexOf(tag);
  return idx >= 0 ? palette[idx % palette.length] : palette[0];
}
