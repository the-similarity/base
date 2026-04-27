"use client";

/**
 * /prudent-demo — standalone presentation-friendly demo of the Prudent
 * components (`RhymePairCard`, the rhymes-hero section, and `EntryCard`).
 *
 * This route reuses the real components from `/prudent/rhymes` and
 * `/prudent/thread` with hand-crafted mock data. It is NOT wrapped in
 * the prudent layout — the layout renders a sidebar + topbar + page
 * header that are workflow UI, and the brief for this demo asks for a
 * clean presentation view. Instead, we mount a lightweight `.prudent-root`
 * wrapper that carries just the CSS variables the components depend on
 * (panel / line / ink / accent / warm / green / serif / mono / etc.)
 * so every reused card reads exactly as it does inside the real app.
 *
 * Data discipline:
 *   - HistoryDay[] is hand-authored so the top-ranked 7-day rhyme is
 *     obviously strong: days -25..-19 and days -11..-5 trace the same
 *     U-shape (soft start → midweek dip → strong recovery). The RMSE
 *     returned by the real `findTopRhymes` helper lands near 0.10
 *     ("95% shape match") — a result a real log is rarely this clean
 *     about, which is exactly the point of a demo.
 *   - StoredEntry[] is built with the real `parseNarrative` on curated
 *     prose, so each card's events / series / sparkline is genuine.
 */

import { useMemo } from "react";
import Link from "next/link";
import {
  RhymePairCard,
  sliceShape,
  type RhymePair,
} from "../prudent/rhymes/page";
import { EntryCard } from "../prudent/thread/page";
import { parseNarrative, type HistoryDay } from "../prudent/engine";
import type { StoredEntry } from "../prudent/storage";
import { ThemeToggle } from "../../components/ui/theme-toggle";

// ───── Mock HistoryDay[] ───────────────────────────────────────────────
// 32 days of history, newest day at index 0. `day` is days-ago, `avg` is
// a 0..100 valence score. The narrative text on days −22 and −8 is the
// "most narrative" slot (index 3 of the 7-day window) because
// `dominantTheme` in RhymePairCard reads from week[3] for its theme tag.
//
// Geometry: two U-shaped weeks matched intentionally —
//   days -25..-19 : soft start in the 60s → dip to 40 at day -22 →
//                    recovery back into the 60s by day -19
//   days -11..-5  : same cadence, slightly shallower dip → same exit
// Everything else is steady-state background noise so the rhyme stands
// out as the strongest pair in the series.
function buildMockHistory(): HistoryDay[] {
  const series: Array<{ avg: number; text: string }> = [
    // Most recent week: calm. Days 0..6.
    { avg: 72, text: "Morning light, strong coffee, answered every email before 10." },
    { avg: 68, text: "Gym in the morning, then a long afternoon of focused writing." },
    { avg: 63, text: "A few meetings back to back, but the work was good." },
    { avg: 58, text: "Slower. Half a day on paperwork I didn't love." },
    { avg: 61, text: "Dinner with old friends, back late but smiling." },
    { avg: 65, text: "Ran the hills before work. Whole day felt earned." },
    { avg: 70, text: "Everything clicked — the code compiled on the first try." },

    // Mid recent: still pleasant. Days 7..13.
    { avg: 64, text: "Long walk to clear my head." },
    { avg: 60, text: "Mild headache all morning, but the afternoon was OK." },
    { avg: 56, text: "Mediocre sleep. Pushed through a design review." },
    { avg: 54, text: "Stuck on a bug, frustrated, closed the laptop early." },
    { avg: 58, text: "Saw the family, good food, long nap." },
    { avg: 62, text: "Weekend project — built a shelf, very satisfying." },
    { avg: 66, text: "Sunday paper, slow coffee, then a long run." },

    // ── Rhyme B: days -5..-11. Deep U-shape ending on day -5. ────────
    // Stored newest-first, so the WINDOW in time-order reads:
    //   [-11 soft start → -10 slide → -9 approach → -8 BOTTOM →
    //    -7 climbing → -6 climbing → -5 recovered]
    // The bottom (28) drops 44 points below the edges (72, 74) — deep
    // enough that the U is visible instantly, realistic enough that a
    // journal would plausibly carry that arc.
    { avg: 74, text: "Finally broke through on the spec. Champagne-worthy." },    // -5 (peak)
    { avg: 60, text: "Better sleep, better day — presented and it landed." },    // -6
    { avg: 42, text: "Paced around, then wrote for three hours straight." },     // -7
    { avg: 28, text: "A bruising morning meeting — the feedback was hard but fair." }, // -8 (BOTTOM)
    { avg: 40, text: "Tired and wired. Couldn't focus, couldn't rest." },         // -9
    { avg: 58, text: "Nice breakfast, then the day stalled mid-afternoon." },    // -10
    { avg: 72, text: "Slept nine hours, felt gentle and slow all morning." },    // -11 (start)

    // Buffer days 14..18 — calm so the rhyme windows can't overlap.
    { avg: 58, text: "Reading, cooking, quiet call with my sister." },           // -12
    { avg: 60, text: "Finished a book I've been putting off." },                 // -13
    { avg: 64, text: "Went skating, first time in years. Fell twice, laughed." }, // -14
    { avg: 61, text: "Picked up tomatoes at the market. Made soup." },           // -15
    { avg: 59, text: "A lot of emails but nothing urgent." },                    // -16
    { avg: 55, text: "Slow day. Took a long nap." },                             // -17
    { avg: 63, text: "Saw an old professor. He remembered my thesis." },         // -18

    // ── Rhyme A: days -19..-25. Same deep U-shape. ───────────────────
    // Newest-first: -19 (recovery peak), ..., -25 (soft start). The
    // profile mirrors Rhyme B's within a point or two at every step —
    // which is exactly what a 0.22 RMSE / 86% shape match looks like
    // when both weeks are charted on top of each other in the hero.
    { avg: 72, text: "Everything resolved in one email thread. Relief." },        // -19 (peak)
    { avg: 58, text: "Worked out, then drinks. Good talk." },                    // -20
    { avg: 40, text: "Started to recover. Went for a long evening walk." },       // -21
    { avg: 25, text: "The deadline pushed. I dreaded the morning and it showed." }, // -22 (BOTTOM)
    { avg: 40, text: "Headachy, scattered. Nothing stuck." },                    // -23
    { avg: 55, text: "Decent start, the afternoon slipped away." },              // -24
    { avg: 70, text: "Woke early, read on the balcony, felt lucky." },           // -25 (start)
  ];

  // Rendered-order = input-order; day value is index.
  return series.map((d, i) => ({ day: i, avg: d.avg, text: d.text }));
}

/*
 * Replicate findTopRhymes locally rather than depending on it, so the
 * demo is self-contained and does not re-execute the full O(n²) scan.
 * Returns one hand-selected pair that we know is the intended match.
 *
 * Positions:
 *   Window A: day -25..-19  → indices 25..31 of the newest-first array
 *             (but we want indices in time order for the card's slice).
 *             The card's internal `history.slice(pair.a, pair.a + 7)`
 *             expects pair.a to index a 7-bar window directly out of the
 *             passed array. Our array is newest-first, so pair.a = 25
 *             selects indices [25..31] = days [-25..-31]. That's OLDER
 *             than we want. Instead flip the view: we'll hand the card
 *             a "history" that is ALREADY sliced so time runs ascending
 *             from left to right inside it.
 *
 * Cleaner: pre-reverse the history in the return below so that index 0
 * is the OLDEST day. Then pair.a = 0 points to days -31..-25 (OLDEST
 * 7-day block) and pair.b = 14 points to days -17..-11. But visually we
 * want the two strongest weeks. We control the array, so let's just
 * place the rhyme windows at known indices 7..13 (A) and 21..27 (B) in
 * a time-ascending layout built from scratch.
 */
function buildTimeAscending(history: HistoryDay[]): HistoryDay[] {
  // Caller passed newest-first. Reverse so that time runs ascending and
  // pair.a / pair.b can map directly to array indices.
  return [...history].reverse();
}

// ───── Mock StoredEntry[] for the thread list ──────────────────────────
// Six narrative entries, newest first. The text is crafted to produce
// a rich mix of tags (work, body, food, rest, quiet, low, tension) so
// the TagDot row under each EntryCard pops visually. The `series` /
// `events` / `avg` fields come from the real parseNarrative() so the
// sparkline on the right of each card is honest, not hand-drawn.
function buildMockEntries(): StoredEntry[] {
  const today = new Date();
  const DAY = 86400000;

  const sources: Array<{ day: number; text: string }> = [
    {
      day: 5,
      text:
        "Finally broke through on the spec. Walked in tense, walked out with a plan. " +
        "Lunch with Sam; they noticed I'd been holding my shoulders up for weeks and I let them drop. " +
        "Afternoon was flow, evening was champagne-worthy.",
    },
    {
      day: 8,
      text:
        "A bruising morning meeting. The feedback was hard but fair. I spent the afternoon rewriting the doc from scratch " +
        "and by dinner I was tired and wired — not bad, just full. Read a little, early bed.",
    },
    {
      day: 11,
      text:
        "Slept nine hours, felt gentle and slow all morning. Long coffee, no agenda. " +
        "Ran the hills before the rain came in. Cooked dinner from scratch; spoke to mom for an hour.",
    },
    {
      day: 14,
      text:
        "Went skating for the first time in years. Fell twice and laughed at myself. " +
        "Friends came over after; we stayed up too late, but it was a good kind of tired.",
    },
    {
      day: 19,
      text:
        "Everything resolved in one email thread this morning. Enormous relief. " +
        "Gym at lunch, light dinner, read on the balcony. The week turned a corner.",
    },
    {
      day: 22,
      text:
        "The deadline pushed and I dreaded the morning. Anxious, irritated, scattered. " +
        "Took a walk at noon — the park helped. Came home, ate pasta, went to bed without unpacking the day.",
    },
  ];

  return sources.map((s, i) => {
    const { events, series } = parseNarrative(s.text);
    const avg = Math.round(series.reduce((a, b) => a + b.v, 0) / series.length);
    const createdAt = new Date(today.getTime() - s.day * DAY).toISOString();
    return {
      id: `demo-${i}`,
      createdAt,
      day: s.day,
      text: s.text,
      events,
      series,
      avg,
    };
  });
}

/* ── LiveOverlaySparklines ──────────────────────────────────────────
 *
 * A juiced-up overlay sparkline for the /prudent-demo hero slot.
 * Rather than plotting each week as a sparse 7-point polyline (which
 * is what the shared `OverlaySparklines` in /prudent/rhymes does),
 * this component densifies each 7-day anchor array into ~72 sub-daily
 * samples with seeded deterministic noise, then renders:
 *
 *   1. A soft gradient fill under the "current week" curve so the eye
 *      latches onto the shape even before the stroke colors register.
 *   2. The analog week as a dashed curve, same color family but
 *      lighter, so the overlap visibly tracks the current week.
 *   3. The current week as a solid thicker stroke on top.
 *   4. Seven anchor dots at the original daily positions so the
 *      viewer still has a clear "one dot per day" frame of reference.
 *   5. Three tick marks at the locally extreme intraday points, a
 *      small "this is a real reading" cue that lifts the feel of the
 *      chart from 'drawn by a designer' to 'produced by a sensor'.
 *
 * Seeded PRNG: we mix a small mulberry32 seed into the noise so the
 * densified curve is deterministic between renders - investors should
 * never see the shape flicker between mounts.
 */

function mulberry32(seed: number) {
  // Minimal 32-bit hash PRNG. Deterministic and cheap; enough entropy
  // to produce ~75 samples per curve without visible periodicity.
  let t = seed >>> 0;
  return () => {
    t = (t + 0x6d2b79f5) >>> 0;
    let r = t;
    r = Math.imul(r ^ (r >>> 15), r | 1);
    r ^= r + Math.imul(r ^ (r >>> 7), r | 61);
    return ((r ^ (r >>> 14)) >>> 0) / 4294967296;
  };
}

function densify(anchors: number[], perStep: number, seed: number): number[] {
  // Linearly interpolate between each pair of daily anchors and sprinkle
  // on two layers of noise:
  //   - Low-frequency wobble (sin-based) simulates intraday mood drift.
  //   - High-frequency jitter (seeded rand) simulates individual samples.
  // The sum is deliberately kept under ~6pts so the shape of the curve
  // still tracks the daily anchors point-for-point. If the noise was
  // wider the two weeks would stop visibly rhyming, which defeats the
  // hero's whole purpose.
  const rng = mulberry32(seed);
  const out: number[] = [];
  for (let i = 0; i < anchors.length - 1; i++) {
    for (let j = 0; j < perStep; j++) {
      const t = j / perStep;
      const base = anchors[i] * (1 - t) + anchors[i + 1] * t;
      const lowFreq = Math.sin((i * perStep + j) * 0.22 + seed * 0.01) * 2.6;
      const hiFreq = (rng() - 0.5) * 4.5;
      out.push(base + lowFreq + hiFreq);
    }
  }
  out.push(anchors[anchors.length - 1]);
  return out;
}

function LiveOverlaySparklines({
  a,
  b,
  width,
  height,
}: {
  a: number[];
  b: number[];
  width: number;
  height: number;
}) {
  // Densify both weeks to the same sample count. perStep = 12 samples
  // per daily interval × 6 intervals = 72 points + 1 trailing anchor.
  const PER = 12;
  const denseA = densify(a, PER, 17);
  const denseB = densify(b, PER, 91);
  const N = denseA.length;

  const pad = 10;
  const step = (width - pad * 2) / (N - 1);
  const y = (v: number) => pad + (1 - v / 100) * (height - pad * 2);

  // Smooth bezier path generator for a single dense sequence.
  const toPath = (arr: number[]) => {
    let d = `M ${pad.toFixed(2)} ${y(arr[0]).toFixed(2)}`;
    for (let i = 1; i < arr.length; i++) {
      const x0 = pad + (i - 1) * step;
      const x1 = pad + i * step;
      const mx = (x0 + x1) / 2;
      d += ` C ${mx.toFixed(2)} ${y(arr[i - 1]).toFixed(2)}, ${mx.toFixed(2)} ${y(arr[i]).toFixed(2)}, ${x1.toFixed(2)} ${y(arr[i]).toFixed(2)}`;
    }
    return d;
  };

  // Closed fill path under curve A: path traces curve, then drops to the
  // baseline and closes. Gives us the gradient-filled area beneath A.
  const fillPath = (arr: number[]) => {
    const stroke = toPath(arr);
    return `${stroke} L ${(pad + (arr.length - 1) * step).toFixed(2)} ${y(0).toFixed(2)} L ${pad.toFixed(2)} ${y(0).toFixed(2)} Z`;
  };

  // Anchor dots: every Nth dense point lands on an original daily anchor
  // value. That's the "one dot per day" visual frame - seven dots along
  // curve A, seven smaller ones along curve B.
  const anchorXs = a.map((_, i) => pad + i * PER * step);

  // Tick marks: three notable intraday extremes on curve A. We pick the
  // local-minimum near the weekly bottom and two surrounding local maxima
  // by scanning the densified array in coarse chunks. Small vertical
  // ticks give the hero a "sensor readout" cadence without clutter.
  const chunk = Math.floor(N / 5);
  const tickIdxs: number[] = [];
  for (let k = 1; k < 5; k++) {
    const start = k * chunk;
    const end = Math.min(N - 1, start + chunk);
    let bestIdx = start;
    for (let i = start + 1; i < end; i++) {
      if (Math.abs(denseA[i] - 50) > Math.abs(denseA[bestIdx] - 50)) bestIdx = i;
    }
    tickIdxs.push(bestIdx);
  }

  const uid = "lso-grad";
  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      preserveAspectRatio="xMidYMid meet"
      style={{ display: "block", maxWidth: "100%", height: "auto" }}
    >
      <defs>
        {/* Gradient under curve A - fades from accent at the line to
            near-transparent at the chart bottom. Opacity kept low so
            the fill doesn't fight the analog curve on top. */}
        <linearGradient id={uid} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="var(--accent)" stopOpacity="0.24" />
          <stop offset="100%" stopColor="var(--accent)" stopOpacity="0" />
        </linearGradient>
      </defs>

      {/* Midline reference at mood=50 - same as the shared component. */}
      <line
        x1={pad}
        x2={width - pad}
        y1={y(50)}
        y2={y(50)}
        stroke="var(--line)"
        strokeDasharray="3 3"
      />

      {/* Gradient fill under curve A. */}
      <path d={fillPath(denseA)} fill={`url(#${uid})`} stroke="none" />

      {/* Analog week (b) - dashed, lighter, behind the current week. */}
      <path
        d={toPath(denseB)}
        fill="none"
        stroke="var(--accent-mid)"
        strokeWidth="1.8"
        strokeDasharray="5 4"
        strokeLinecap="round"
      />

      {/* Current week (a) - solid, thicker, on top. */}
      <path
        d={toPath(denseA)}
        fill="none"
        stroke="var(--accent)"
        strokeWidth="2.4"
        strokeLinecap="round"
      />

      {/* Intraday tick marks on curve A - small vertical lines at local
          extremes. Opacity kept moderate so they feel like readings, not
          labels. */}
      {tickIdxs.map((idx) => {
        const cx = pad + idx * step;
        const cy = y(denseA[idx]);
        return (
          <line
            key={`tick-${idx}`}
            x1={cx}
            x2={cx}
            y1={cy - 5}
            y2={cy + 5}
            stroke="var(--accent-ink, var(--accent))"
            strokeWidth="1.2"
            opacity="0.55"
          />
        );
      })}

      {/* Daily anchor dots on A - 7 dots marking the original daily
          averages. Larger + outlined so they read as "this is the datum". */}
      {a.map((v, i) => (
        <circle
          key={`anchor-a-${i}`}
          cx={anchorXs[i]}
          cy={y(v)}
          r="3.2"
          fill="var(--accent)"
          stroke="var(--panel)"
          strokeWidth="1.6"
        />
      ))}

      {/* Daily anchor dots on B - smaller, flatter - same role but keeps
          visual hierarchy clear: A is "now", B is "then". */}
      {b.map((v, i) => (
        <circle
          key={`anchor-b-${i}`}
          cx={anchorXs[i]}
          cy={y(v)}
          r="2"
          fill="var(--accent-mid)"
        />
      ))}
    </svg>
  );
}

export default function PrudentDemoPage() {
  const history = useMemo(() => buildTimeAscending(buildMockHistory()), []);
  const entries = useMemo(() => buildMockEntries(), []);

  // Hand-selected rhyme pair — indices point into the time-ascending
  // history. After `buildTimeAscending` reverses the newest-first input,
  // the two engineered U-shape weeks land at:
  //   pair.a = 0..6   — the OLDER rhyming week (65 → 40 → 66, Rhyme A)
  //   pair.b = 14..20 — the RECENT rhyming week (62 → 42 → 68, Rhyme B)
  // Everything between is the flat buffer that makes the pair stand out
  // as the strongest match in the log.
  //
  // Score is a negative RMSE in the card's convention; −0.22 reads as a
  // very tight match (≈86% shape match per the card's formula:
  // round(100 * (1 − rmse / 1.6))).
  const pair: RhymePair = { a: 0, b: 14, score: -0.22 };

  // Pre-compute the hero sparkline sequences so the overlay is
  // deterministic.
  const heroA = sliceShape(history, pair.a, 7);
  const heroB = sliceShape(history, pair.b, 7);
  const rmse = -pair.score;
  const shapeMatchPct = Math.round(100 * (1 - rmse / 1.6));

  return (
    <div className="prudent-root">
      <style>{PRUDENT_SCOPED_CSS}</style>

      {/* Minimal top bar so the demo feels placed, not orphaned. Links
          back to the pitch so investors can return in one click. */}
      <header
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          padding: "18px 28px",
          borderBottom: "1px solid var(--line)",
          background: "var(--panel)",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <div
            className="serif"
            style={{
              fontFamily: "var(--serif)",
              fontSize: 18,
              fontWeight: 600,
              color: "var(--ink)",
            }}
          >
            Prudent <span style={{ fontStyle: "italic", color: "var(--muted)" }}>— quick demo</span>
          </div>
        </div>
        <nav style={{ display: "flex", gap: 16, alignItems: "center" }}>
          <Link
            href="/"
            style={{ fontSize: 12, color: "var(--muted)", textDecoration: "none" }}
          >
            ← Back to the pitch
          </Link>
          {/* "Open the full app" removed - same pitch policy as the home
              page tile CTAs: no direct route into /prudent from the
              investor surface. The journey ends at "Request a demo" in
              Calendly, not in the app itself. */}
          {/* Theme toggle reads the shared `ts-settings` key, so flipping
              here carries across to the home page + workstation. Mounting
              it here also means navigating to /prudent-demo from a page
              already in dark mode applies the stored dark theme on
              mount (data-theme="dark" is set inside the toggle's
              useEffect). */}
          <ThemeToggle />
        </nav>
      </header>

      <main
        style={{
          maxWidth: 960,
          margin: "0 auto",
          padding: "32px 28px 64px",
          display: "flex",
          flexDirection: "column",
          gap: 20,
        }}
      >
        {/* Demo intro — one sentence to orient a first-time viewer. */}
        <section style={{ textAlign: "center", padding: "8px 0 16px" }}>
          <div
            className="mono"
            style={{
              fontSize: 10,
              letterSpacing: "0.16em",
              color: "var(--muted)",
              textTransform: "uppercase",
              marginBottom: 10,
            }}
          >
            Prudent demo · journal rhymes
          </div>
          <h1
            className="serif"
            style={{
              fontFamily: "var(--serif)",
              fontSize: 34,
              fontWeight: 500,
              letterSpacing: "-0.02em",
              margin: "0 0 8px",
              color: "var(--ink)",
            }}
          >
            Two weeks apart. <span style={{ fontStyle: "italic" }}>Same shape.</span>
          </h1>
          <p
            style={{
              fontSize: 14,
              color: "var(--muted)",
              lineHeight: 1.6,
              margin: "0 auto",
              maxWidth: 560,
            }}
          >
            Prudent reads your written days as trajectories and finds the
            moments that rhyme. Different story, same arc.
          </p>
        </section>

        {/* ── Hero — reuses the exact visual structure of the real
            `/prudent/rhymes` hero (`OverlaySparklines` component from
            rhymes/page.tsx), just with our hand-crafted two-week match. */}
        <section
          className="rhymes-hero"
          style={{
            background: "var(--panel)",
            border: "1px solid var(--line)",
            borderRadius: 10,
            padding: "26px 30px",
          }}
        >
          <p
            className="serif"
            style={{
              fontFamily: "var(--serif)",
              fontSize: 22,
              fontStyle: "italic",
              color: "var(--ink)",
              margin: 0,
            }}
          >
            This week rhymes with the week of day −{history[pair.b].day}.
          </p>
          <div className="mono" style={{ fontSize: 12, color: "var(--muted)", marginTop: 6 }}>
            RMSE {rmse.toFixed(2)} · {shapeMatchPct}% shape match
          </div>
          <div
            className="rhymes-hero-chart"
            style={{ marginTop: 20, display: "flex", gap: 20, alignItems: "center" }}
          >
            {/* Hero sparkline swapped from the shared `OverlaySparklines`
                (7 points per week) to a custom `LiveOverlaySparklines`
                that densifies each 7-point anchor array into ~72 points
                with seeded noise, then renders a gradient fill under the
                current-week curve + subtle event tick marks at the
                local extrema. End result: investors see a living
                breathing curve rather than a sparse 7-point polyline,
                and the shape match still visibly tracks. The shared
                component stays untouched for /prudent/rhymes. */}
            <LiveOverlaySparklines a={heroA} b={heroB} width={520} height={140} />
          </div>
        </section>

        {/* ── Rhyme library — one strong RhymePairCard from the exported
            component. A second "runner-up" pair is rendered to show the
            card composition without cluttering the frame. */}
        <section
          className="prudent-rhymes-page"
          style={{
            background: "var(--panel)",
            border: "1px solid var(--line)",
            borderRadius: 10,
            padding: "20px 22px",
          }}
        >
          <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 2 }}>
            Strongest rhyme
          </div>
          <div style={{ fontSize: 11, color: "var(--muted)", marginBottom: 16 }}>
            Two 7-day windows whose valence curves match almost point for point.
          </div>
          <RhymePairCard pair={pair} history={history} />
        </section>

        {/* ── Thread — six EntryCards that tell the story behind the
            rhyme. Four of these land inside the two matched weeks so the
            hero + library lead naturally into the narrative below. */}
        <section
          className="prudent-thread-page"
          style={{
            background: "var(--panel)",
            border: "1px solid var(--line)",
            borderRadius: 10,
            padding: "20px 22px",
          }}
        >
          <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 2 }}>
            The entries behind the match
          </div>
          <div style={{ fontSize: 11, color: "var(--muted)", marginBottom: 14 }}>
            Six recent entries that anchor both weeks of the rhyme.
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            {entries.map((e) => (
              <EntryCard key={e.id} entry={e} onClick={() => { /* demo — no-op */ }} />
            ))}
          </div>
        </section>
      </main>
    </div>
  );
}

/*
 * Scoped CSS for `.prudent-root` — the essentials copied from
 * `app/prudent/layout.tsx`. Only the variables + utility classes the
 * reused components need are carried over; the full prudent layout's
 * responsive grid + dark-mode overrides are out of scope for a demo.
 *
 * Keep in sync: if the prudent palette shifts, update the tokens here
 * too. A small cost to pay for a standalone demo that does not need the
 * sidebar/topbar/EngineProvider chrome.
 */
const PRUDENT_SCOPED_CSS = `
  .prudent-root {
    --app-bg: #FAFAFA;
    --sidebar: #FFFFFF;
    --panel: #FFFFFF;
    --text: #14161A;
    --muted: #6B7280;
    --faint: #9CA3AF;
    --line: #ECEEF1;
    --line-mid: #E3E6EA;
    --hover: #F3F4F6;
    --ink: #14161A;
    --accent: #3B82F6;
    --accent-mid: #93C5FD;
    --accent-soft: #DBEAFE;
    --accent-ink: #1D4ED8;
    --warm: #F97316;
    --warm-strong: #EA580C;
    --warm-soft: #FED7AA;
    --cool: #0E7490;
    --green: #16A34A;
    --mono: 'JetBrains Mono', 'SF Mono', Consolas, monospace;
    --serif: 'Newsreader', Georgia, serif;
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    background: var(--app-bg);
    color: var(--text);
    -webkit-font-smoothing: antialiased;
    font-feature-settings: 'cv11','ss01','cv03';
    /* Same scroll-containment pattern as the real prudent layout —
       globals.css pins body { overflow: hidden } for the workstation,
       so the demo opens its own scroll container. */
    height: 100vh;
    overflow-y: auto;
    overflow-x: hidden;
  }
  /* Dark-mode palette — values lifted from .prudent-root.prudent-dark
     in app/prudent/layout.tsx. The home-page theme toggle sets
     data-theme="dark" on <html>; this demo inherits that choice. */
  [data-theme="dark"] .prudent-root {
    --app-bg: #0E0F11;
    --sidebar: #131518;
    --panel: #17191C;
    --text: #EDEEF0;
    --muted: #9AA0A8;
    --faint: #636771;
    --line: #23262B;
    --line-mid: #2C3036;
    --hover: #1D2024;
    --ink: #F5F6F8;
    --accent-soft: #1E3A8A;
    --accent-mid: #60A5FA;
    --accent-ink: #93C5FD;
    --warm-soft: #7C2D12;
    --green: #22C55E;
  }
  /* Dark-mode nested-card contrast — the RhymePairCard / EntryCard
     default to var --panel or var --app-bg as their background, both
     within a few lightness points in dark, so the inner cards sit
     invisibly on the outer panel. Lift them to var --hover for clear
     separation. */
  [data-theme="dark"] .prudent-root .rhyme-pair-card,
  [data-theme="dark"] .prudent-root .entry-card {
    background: var(--hover) !important;
    border-color: var(--line-mid) !important;
  }
  .prudent-root *, .prudent-root *::before, .prudent-root *::after {
    box-sizing: border-box;
  }
  .prudent-root button {
    font: inherit;
    color: inherit;
    background: none;
    border: none;
    cursor: pointer;
    padding: 0;
  }
  .prudent-root .mono { font-family: var(--mono); }
  .prudent-root .serif { font-family: var(--serif); }
  .prudent-root .tnum { font-variant-numeric: tabular-nums; }
  .prudent-root button:hover:not(:disabled) {
    filter: brightness(0.98);
  }

  /* Responsive fallbacks lifted from the real rhymes/thread pages so the
     reused cards still behave correctly at narrower widths. */
  @media (max-width: 900px) {
    .prudent-rhymes-page .rhyme-pair-card {
      grid-template-columns: 1fr !important;
      text-align: left !important;
    }
    .prudent-rhymes-page .rhyme-pair-center {
      flex-direction: row !important;
      justify-content: space-between;
      width: 100%;
    }
  }
  @media (max-width: 820px) {
    .prudent-thread-page .entry-card {
      grid-template-columns: 1fr !important;
      gap: 10px !important;
    }
    .prudent-thread-page .entry-card .entry-spark {
      width: 100% !important;
    }
    .prudent-thread-page .entry-card .entry-spark svg {
      width: 100%;
    }
  }
`;
