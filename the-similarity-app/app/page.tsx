"use client";

/**
 * Home — the investor-facing landing page at `/`.
 *
 * Audience: non-technical angel and seed investors. Assumes zero priors
 * about time series, quant finance, or pattern matching. The job of this
 * page is to make someone with no engineering background say "I get it,
 * and I want in" inside of ninety seconds.
 *
 * Layout: reuses the app chrome (marquee bar + status bar) from the
 * workstation so the investor lands somewhere that already feels like
 * a product, not a marketing microsite. Body is a long-scroll editorial:
 *   1. Hero with an animated "rhyme" SVG that renders the product
 *      metaphor in one glance.
 *   2. Plain-English explainer — "in plain English, what is this?"
 *   3. Two-up demo frames (Workstation + Prudent) showing the engine in
 *      two different surfaces so investors see the primitive generalizes.
 *   4. Numbers strip — production-proof points (lenses, tests, rows).
 *   5. Five-pillar vision — the application surfaces the engine powers.
 *   6. The ask — $100K on $750K cap, prominently framed.
 *   7. Closer + foot.
 *
 * Copy discipline: no CRPS, no SAX, no wavelet leaders. An investor who
 * wants to read the math can click through to the workstation or email
 * the founder. Here every sentence must be legible to a non-quant.
 *
 * Layout invariant: body { overflow: hidden } is set globally on the
 * app shell; `.page` has `overflow: auto`, so all scrolling on the
 * home page happens inside the 1fr middle row between the marquee and
 * status bar. Marquee + status bar remain fixed.
 */

import Link from "next/link";
import { useEffect, useState } from "react";
import { DemoChart } from "../components/demo/demo-chart";
import { PrudentDemoPreview } from "../components/demo/prudent-preview";
import { ThemeToggle } from "../components/ui/theme-toggle";
import { Signature } from "../components/ui/signature";

export default function HomePage() {
  // America/Los_Angeles (Pacific) wall clock for the status bar. The
  // founder is in SF, so the pitch surface should read SF time rather
  // than East Coast - small detail that reads as "built where we live"
  // to Bay Area LPs. Minute resolution; ticks on the minute.
  const [nyClock, setNyClock] = useState<string>("");
  useEffect(() => {
    const tick = () => {
      const now = new Date();
      const d = new Intl.DateTimeFormat("en-US", {
        timeZone: "America/Los_Angeles",
        month: "short",
        day: "numeric",
        year: "numeric",
      }).format(now);
      const t = new Intl.DateTimeFormat("en-US", {
        timeZone: "America/Los_Angeles",
        hour: "2-digit",
        minute: "2-digit",
        hour12: false,
      }).format(now);
      setNyClock(`${d} · ${t} SF`);
    };
    tick();
    const id = window.setInterval(tick, 60_000);
    return () => window.clearInterval(id);
  }, []);

  return (
    <div className="app">
      {/* ── Marquee bar ───────────────────────────────────────────
          Carries the brand wordmark and a rolling ticker. The ticker
          items lead with the round status so investors see the ask
          immediately, even before they scroll. */}
      <div className="marquee">
        <div className="brand">
          <div className="brand__logo" aria-hidden="true">
            <svg width="22" height="22" viewBox="0 0 26 26">
              <circle cx="13" cy="13" r="11" fill="none" stroke="var(--ink)" strokeWidth="1.2" />
              <circle cx="13" cy="13" r="6" fill="none" stroke="var(--ink)" strokeWidth="1.2" />
              <circle cx="13" cy="13" r="1.8" fill="var(--ink)" />
            </svg>
          </div>
          <div className="brand__word">The <em>Similarity</em></div>
        </div>
        <div style={{ overflow: "hidden", flex: 1 }}>
          <div className="marquee__track">
            {Array.from({ length: 2 }).map((_, k) => (
              <span key={k} style={{ display: "contents" }}>
                <span className="marquee__item">Seed round open &middot; <b>$100K on $750K</b></span>
                <span className="marquee__item">Structural intelligence for time, state &amp; simulation</span>
                <span className="marquee__item">Find what rhymes &middot; model what evolves &middot; simulate what comes next</span>
                <span className="marquee__item"><b>engine</b> nine lenses / five surfaces</span>
              </span>
            ))}
          </div>
        </div>
        <div className="nav__right">
          <ThemeToggle />
        </div>
      </div>

      {/* ── Body ─────────────────────────────────────────────────── */}
      <main className="page invest">
        {/* ── 1. Hero ──────────────────────────────────────────── */}
        <section className="invest__hero">
          <div className="invest__hero-copy">
            <div className="invest__eyebrow">
              <span className="invest__eyebrow-dot" aria-hidden="true" />
              Seed round open &middot; <b>$100,000 on $750,000 cap</b>
            </div>
            <h1 className="invest__headline">
              Every chart has <em>already</em> happened.
            </h1>
            <p className="invest__lede">
              We built a search engine for history. Point it at any moment
              - in the market, in a life, in a simulated world -
              and it shows you the shapes that came before, and the shapes
              most likely to come next.
            </p>
            <div className="invest__cta-row">
              <a
                href="https://calendly.com/buyan-khurel/30min"
                target="_blank"
                rel="noopener noreferrer"
                className="home__cta home__cta--primary"
              >
                Request a live demo
              </a>
              <a
                href="mailto:buyan.khurel@gmail.com?subject=Investor%20inquiry%20%E2%80%94%20The%20Similarity"
                className="home__cta"
              >
                Contact
              </a>
            </div>
            <div className="invest__hero-ticks">
              <span>Shipping in production</span>
              <span className="invest__tick-sep">&middot;</span>
              <span>Active research</span>
              <span className="invest__tick-sep">&middot;</span>
              <span>Five surfaces live</span>
            </div>
          </div>
          <div className="invest__hero-visual" aria-hidden="true">
            <HeroRhyme />
          </div>
        </section>

        {/* ── 2. Plain English ─────────────────────────────────── */}
        <section className="invest__plain">
          <div className="invest__plain-label">
            <span className="label">In plain English</span>
          </div>
          <p className="invest__plain-body">
            Markets <em>rhyme</em>. They don&rsquo;t repeat, but their shapes
            return - a crash in 2008 looks a lot like a crash in 1987
            looks a lot like a panic on Tuesday. Our engine reads the shape
            of right now and matches it against every moment that ever
            happened, across nine different ways of measuring what
            &ldquo;similar&rdquo; even means. The answer comes back in
            seconds, not weeks. That is the whole company.
          </p>
        </section>

        {/* ── 3. Live demo frames ──────────────────────────────── */}
        <section className="invest__demos">
          <header className="invest__section-header">
            <span className="label">Two products &middot; one engine</span>
            <h2 className="invest__section-head">Shipping on the engine today.</h2>
            <p className="invest__section-lede">
              Finance is the first surface because finance pays first. But
              the engine underneath is a primitive - it works anywhere
              a sequence of numbers carries a story.
            </p>
          </header>

          <div className="invest__demo-grid">
            <article className="invest__demo">
              {/* Real chart, not a static SVG mock. DemoChart wraps the
                  workstation's LineChart component with curated mock data
                  so the home page preview is the same chart experience
                  investors get when they click through to /workstation —
                  just scoped down to one strong analog and a clean cone. */}
              <div className="invest__demo-visual invest__demo-visual--chart">
                <DemoChart height={300} sub="pattern demo · one analog" />
              </div>
              <div className="invest__demo-body">
                <div className="label">01 &middot; Workstation</div>
                <h3 className="invest__demo-head">
                  Drag a window. Watch history answer.
                </h3>
                <p className="invest__demo-copy">
                  Pick any slice of any chart. The engine returns the
                  most structurally similar moments from the past -
                  each one drawing its own forward line on your screen.
                  It&rsquo;s a Bloomberg terminal that asks{" "}
                  <em>what rhymes with now?</em> and means it.
                </p>
                <div className="invest__demo-links">
                  <Link href="/demo" className="invest__demo-link">
                    See the quick demo &rarr;
                  </Link>
                  <a
                    href="https://calendly.com/buyan-khurel/30min"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="invest__demo-link invest__demo-link--muted"
                  >
                    Request a live demo
                  </a>
                </div>
              </div>
            </article>

            <article className="invest__demo">
              {/* Real RhymePairCard, not a static SVG mock. Mirrors the
                  workstation tile's "reuse the real component" pattern —
                  investors who click through to /prudent-demo see the
                  same card in a larger frame, with no surprise reveal. */}
              <div className="invest__demo-visual invest__demo-visual--chart invest__demo-visual--prudent">
                <PrudentDemoPreview />
              </div>
              <div className="invest__demo-body">
                <div className="label">02 &middot; Prudent</div>
                <h3 className="invest__demo-head">
                  Sentences become time series.
                </h3>
                <p className="invest__demo-copy">
                  Type a day in plain English - &ldquo;slept nine
                  hours, coffee with friends, meeting went sideways.&rdquo;
                  The engine compiles your words into a mood curve, then
                  finds days in your history that rhyme with it. Same
                  idea, a different frontier.
                </p>
                <div className="invest__demo-links">
                  <Link href="/prudent-demo" className="invest__demo-link">
                    See the quick demo &rarr;
                  </Link>
                  {/* Mirrors the workstation tile: no direct route into the
                      full product surface from the pitch page. Investors
                      journey ends at Calendly, not in the app itself. */}
                  <a
                    href="https://calendly.com/buyan-khurel/30min"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="invest__demo-link invest__demo-link--muted"
                  >
                    Request a live demo
                  </a>
                </div>
              </div>
            </article>

            <article className="invest__demo">
              {/* Fractal loop - the engine run in reverse. Self-similarity
                  doesn't just find repeats, it can also generate them:
                  this video is a 20-agent torus world the fractal renderer
                  spun up from a distribution. Autoplay muted loop, <2MB
                  MP4, poster frame is a 19KB JPG for cold-start. */}
              <div className="invest__demo-visual invest__demo-visual--chart invest__demo-visual--video">
                <video
                  src="/fractal.mp4"
                  poster="/fractal.jpg"
                  autoPlay
                  muted
                  loop
                  playsInline
                  aria-label="Fractal sandbox world - generated trajectories rendered in 3D"
                />
              </div>
              <div className="invest__demo-body">
                <div className="label">03 &middot; Sandbox</div>
                <h3 className="invest__demo-head">
                  Worlds on tap.
                </h3>
                <p className="invest__demo-copy">
                  The engine works in reverse too. Feed it a distribution
                  and it generates <em>new</em> trajectories that preserve
                  the dynamics - synthetic markets to stress-test a model,
                  simulated environments for world-model training, agent
                  trajectories for robotics policy evaluation. Same
                  primitive, different direction.
                </p>
                <div className="invest__demo-links">
                  <a
                    href="https://calendly.com/buyan-khurel/30min"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="invest__demo-link"
                  >
                    Request a live demo &rarr;
                  </a>
                </div>
              </div>
            </article>

            {/* 04 · Worlds - NEXUS SIM screenshot. Static PNG (encoded as
                JPG at ~680KB) rather than a loop because the image alone
                reads as "agent society" instantly, and a 15s capture would
                add weight to a page already carrying fractal.mp4 and
                workstation.mp4. If we later want motion here, the
                `invest__demo-visual--image` wrapper swaps cleanly for the
                `--video` variant; they share layout. */}
            <article className="invest__demo">
              <div className="invest__demo-visual invest__demo-visual--chart invest__demo-visual--image">
                <img
                  src="/worlds.jpg"
                  alt="NEXUS SIM - agent society generating market, chat, and movement time series"
                  loading="lazy"
                />
              </div>
              <div className="invest__demo-body">
                <div className="label">04 &middot; Worlds</div>
                <h3 className="invest__demo-head">
                  Agent societies in silicon.
                </h3>
                <p className="invest__demo-copy">
                  Every tick, agents trade, chat, and cooperate. Out of
                  that comes wealth, influence, and market activity
                  series. The same engine that finds rhymes in SPY finds
                  rhymes in worlds we ran ourselves - which is how we
                  test whether it generalizes past finance.
                </p>
                <div className="invest__demo-links">
                  <a
                    href="https://calendly.com/buyan-khurel/30min"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="invest__demo-link"
                  >
                    Request a live demo &rarr;
                  </a>
                </div>
              </div>
            </article>
          </div>
        </section>

        {/* ── 4. Numbers strip ─────────────────────────────────── */}
        <section className="invest__stats">
          <header className="invest__section-header">
            <span className="label">Not a deck &middot; real software</span>
            <h2 className="invest__section-head">By the numbers.</h2>
          </header>
          <div className="invest__stat-grid">
            <div className="invest__stat">
              <div className="invest__stat-value">9</div>
              <div className="invest__stat-label">
                Mathematical lenses<br />
                <span>shape &middot; dynamics &middot; scaling &middot; rhythm</span>
              </div>
            </div>
            <div className="invest__stat">
              <div className="invest__stat-value">~50M</div>
              <div className="invest__stat-label">
                Research tokens / month<br />
                <span>deep-research agents running every day</span>
              </div>
            </div>
            <div className="invest__stat">
              <div className="invest__stat-value">24/7</div>
              <div className="invest__stat-label">
                Autonomous research loop<br />
                <span>RL agents &middot; humans in the loop &middot; auto-research</span>
              </div>
            </div>
            <div className="invest__stat">
              <div className="invest__stat-value">5</div>
              <div className="invest__stat-label">
                Surfaces shipping<br />
                <span>finance &middot; life &middot; space &middot; worlds &middot; language</span>
              </div>
            </div>
          </div>
        </section>

        {/* ── 4b. Horizon - target industries ──────────────────────
            Honest forward-looking. These aren't invented revenue or AUM
            figures - they're the industries a horizontal self-similarity
            primitive *can* address. Framing is "pointed at" not "done",
            and each tile names the real domain + the real customer type.
            If we later sign specific partners or close specific revenue,
            those become their own stat tiles above; this section stays
            aspirational until then. */}
        <section className="invest__stats invest__stats--horizon">
          <header className="invest__section-header">
            <span className="label">Where we&rsquo;re pointed</span>
            <h2 className="invest__section-head">The horizon.</h2>
            <p className="invest__section-lede">
              Self-similarity is horizontal - any domain that produces
              trajectories is fair game. Finance pays first, and pays
              well. But the primitive wants to live in every time
              series a human or machine ever cared about.
            </p>
          </header>
          <div className="invest__stat-grid">
            <div className="invest__stat invest__stat--horizon">
              <div className="invest__stat-eyebrow">target &rarr;</div>
              <div className="invest__stat-headline">Every liquid market</div>
              <div className="invest__stat-label">
                Finance<br />
                <span>quant funds &middot; risk desks &middot; retail platforms</span>
              </div>
            </div>
            <div className="invest__stat invest__stat--horizon">
              <div className="invest__stat-eyebrow">target &rarr;</div>
              <div className="invest__stat-headline">Synthetic trajectories at scale</div>
              <div className="invest__stat-label">
                AI labs<br />
                <span>world models &middot; policy training &middot; evals</span>
              </div>
            </div>
            <div className="invest__stat invest__stat--horizon">
              <div className="invest__stat-eyebrow">target &rarr;</div>
              <div className="invest__stat-headline">Every continuous human signal</div>
              <div className="invest__stat-label">
                Personal<br />
                <span>wearables &middot; journals &middot; health records</span>
              </div>
            </div>
            <div className="invest__stat invest__stat--horizon">
              <div className="invest__stat-eyebrow">target &rarr;</div>
              <div className="invest__stat-headline">Text streams as time series</div>
              <div className="invest__stat-label">
                Language<br />
                <span>news feeds &middot; filings &middot; chat threads</span>
              </div>
            </div>
          </div>
        </section>

        {/* ── 5. Five pillars ──────────────────────────────────── */}
        <section className="invest__vision">
          <header className="invest__section-header">
            <span className="label">The five doors</span>
            <h2 className="invest__section-head">
              One primitive. Five products.
            </h2>
            <p className="invest__section-lede">
              Self-similarity is a lens that works anywhere trajectories
              repeat. Finance pays first. But the engine wants to live in
              every time series a human ever cared about.
            </p>
          </header>
          <div className="invest__pillars">
            {[
              [
                "01",
                "Finance",
                "Backtests, analog search, forward cones for quants, PMs and risk teams.",
                "live",
              ],
              [
                "02",
                "Synthetic data",
                "Block-bootstrap generation with fidelity and privacy scorecards.",
                "live",
              ],
              [
                "03",
                "3D data space",
                "Walk through the similarity landscape. Proximity is structural rhyme.",
                "preview",
              ],
              [
                "04",
                "World events",
                "Simulated worlds with evaluable dynamics. World models, tested.",
                "beta",
              ],
              [
                "05",
                "Language → time",
                "Describe anything in words. Get a calibrated trajectory back.",
                "live",
              ],
            ].map(([n, name, desc, status]) => (
              <article key={n} className="invest__pillar">
                <div className="invest__pillar-top">
                  <span className="invest__pillar-num">{n}</span>
                  <span
                    className={`invest__pillar-status invest__pillar-status--${status}`}
                  >
                    {status}
                  </span>
                </div>
                <h3 className="invest__pillar-name">{name}</h3>
                <p className="invest__pillar-desc">{desc}</p>
              </article>
            ))}
          </div>
        </section>

        {/* ── 6. The ask ───────────────────────────────────────── */}
        <section className="invest__ask">
          <div className="invest__ask-card">
            <div className="invest__ask-corner invest__ask-corner--tl" aria-hidden="true" />
            <div className="invest__ask-corner invest__ask-corner--tr" aria-hidden="true" />
            <div className="invest__ask-corner invest__ask-corner--bl" aria-hidden="true" />
            <div className="invest__ask-corner invest__ask-corner--br" aria-hidden="true" />

            <div className="label invest__ask-eyebrow">The ask</div>
            <h2 className="invest__ask-head">
              Raising <em>$100,000</em> on a <em>$750,000</em> cap.
            </h2>
            <p className="invest__ask-body">
              Ten to fifteen seats. First-check investors welcome. The
              product is shipping, the tests are green, five surfaces are
              live, and the founder is building in public. The raise buys
              twelve months of focus.
            </p>

            <div className="invest__ask-stats">
              <div>
                <b>$100K</b>
                <span>raising</span>
              </div>
              <div>
                <b>$750K</b>
                <span>valuation cap</span>
              </div>
              <div>
                <b>12 mo</b>
                <span>runway</span>
              </div>
              <div>
                <b>15 max</b>
                <span>seats</span>
              </div>
            </div>

            <div className="invest__ask-cta">
              <a
                href="https://calendly.com/buyan-khurel/30min"
                target="_blank"
                rel="noopener noreferrer"
                className="home__cta home__cta--primary invest__ask-primary"
              >
                Take my money &rarr;
              </a>
              <a
                href="mailto:buyan.khurel@gmail.com?subject=Live%20demo%20%E2%80%94%20The%20Similarity"
                className="home__cta"
              >
                Book a live demo
              </a>
            </div>

            {/* Signature block - puts a human behind the ask.
                Animated autograph reveals over 5.5s on mount. Researcher
                meta row sits beneath in mono type, matching the stat-tile
                / status-bar typographic cadence so the block feels like
                part of the card rather than an orphan. */}
            <div className="invest__signature">
              <div className="invest__signature-mark" aria-label="Signed, Buyan Khurel">
                <Signature />
              </div>
              <div className="invest__signature-meta">
                <div className="invest__signature-name">Buyan Khurel</div>
                <div className="invest__signature-role">
                  Researcher &middot; Founder
                </div>
                <div className="invest__signature-bio">
                  Computer Science &amp; Physics double major at San Jose
                  State University. Background: lab research, finance,
                  competitive programming.
                </div>
                <div className="invest__signature-links">
                  <a
                    href="https://github.com/buyan-kh"
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    github.com/buyan-kh
                  </a>
                  <span aria-hidden="true">&middot;</span>
                  <a
                    href="https://www.linkedin.com/in/buyankh/"
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    linkedin.com/in/buyankh
                  </a>
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* ── 7. Foot ──────────────────────────────────────────── */}
        <footer className="invest__foot">
          <div className="invest__foot-left">
            <div className="brand">
              <div className="brand__logo" aria-hidden="true">
                <svg width="18" height="18" viewBox="0 0 26 26">
                  <circle cx="13" cy="13" r="11" fill="none" stroke="var(--ink)" strokeWidth="1.2" />
                  <circle cx="13" cy="13" r="6" fill="none" stroke="var(--ink)" strokeWidth="1.2" />
                  <circle cx="13" cy="13" r="1.8" fill="var(--ink)" />
                </svg>
              </div>
              <div className="brand__word">The <em>Similarity</em></div>
            </div>
            <span className="label invest__foot-tag">MMXXVI</span>
          </div>
          <div className="invest__foot-right">
            {/* Footer routes trimmed - "Demo" + "Prudent demo" links
                removed so the only outbound surfaces from the pitch foot
                are Calendly + email, matching the tile-CTA policy. The
                demo pages are still reachable via the "See the quick
                demo" links inside each demo tile above. */}
            <a
              href="https://calendly.com/buyan-khurel/30min"
              target="_blank"
              rel="noopener noreferrer"
            >
              Request a demo
            </a>
            <a href="mailto:buyan.khurel@gmail.com">Email</a>
          </div>
        </footer>
      </main>

      {/* ── Status bar ───────────────────────────────────────────── */}
      <footer className="statusbar">
        <span className="statusbar__item"><b>engine</b> v4.14 &middot; nine lenses</span>
        <span className="statusbar__sep">│</span>
        <span className="statusbar__item">round <b>open</b></span>
        <span className="statusbar__sep">│</span>
        <span className="statusbar__item"><b>$100K</b> on <b>$750K</b></span>
        <div className="statusbar__right">
          <span className="statusbar__item">
            <a
              href="https://calendly.com/buyan-khurel/30min"
              target="_blank"
              rel="noopener noreferrer"
              className="kbd kbd--link"
            >
              request a live demo
            </a>
          </span>
          <span className="statusbar__item">
            <b>{nyClock}</b>
          </span>
        </div>
      </footer>
    </div>
  );
}

/*
 * ──────────────────────────────────────────────────────────────────────
 * HeroRhyme
 *
 * The headline visual. Renders the product metaphor in a single glance:
 * one bold "query" line, three fainter "analog" lines behind it with
 * similar shapes but offset phases (the rhyme), a dashed query window,
 * and a forward forecast cone extending right.
 *
 * Intentionally low-key: no JS, just SVG + CSS keyframes. The analogs
 * breathe with a slow offset animation so the composition feels alive
 * without looking like a loading state. All colors come from CSS tokens
 * so the visual flips correctly with dark theme.
 * ──────────────────────────────────────────────────────────────────────
 */
function HeroRhyme() {
  return (
    <svg
      viewBox="0 0 640 480"
      className="invest__rhyme"
      xmlns="http://www.w3.org/2000/svg"
      preserveAspectRatio="xMidYMid meet"
    >
      <defs>
        <linearGradient id="coneGradient" x1="0" x2="1" y1="0" y2="0">
          <stop offset="0%" stopColor="var(--c-cone-fill)" stopOpacity="0.95" />
          <stop offset="100%" stopColor="var(--c-cone-fill)" stopOpacity="0" />
        </linearGradient>
        <linearGradient id="coneEdge" x1="0" x2="1" y1="0" y2="0">
          <stop offset="0%" stopColor="var(--c-cone-line)" stopOpacity="0.9" />
          <stop offset="100%" stopColor="var(--c-cone-line)" stopOpacity="0" />
        </linearGradient>
      </defs>

      {/* Horizontal grid — kept very faint, just a chart-surface hint. */}
      {[0, 1, 2, 3, 4, 5, 6].map((i) => (
        <line
          key={i}
          x1="0"
          x2="640"
          y1={80 + i * 55}
          y2={80 + i * 55}
          stroke="var(--c-grid)"
          strokeWidth="1"
        />
      ))}

      {/*
       * Forward forecast cone — anchored at the query endpoint (400, 260)
       * and widening as we project forward toward x=620.
       *
       * Upper and lower edges are hand-tuned polylines (not quadratic
       * beziers) so the envelope reads as *data*: multiple local swings,
       * visible turning points, and sharp direction changes, instead of
       * one smooth blob. The two edges echo each other in phase but
       * aren't symmetric — a bullish-tilt path and a bearish-tilt path
       * that could plausibly come from two different Monte Carlo draws.
       *
       * Geometry invariants:
       *   - Both edges start at (400, 260) and end at their horizon
       *     points — upper at (620, 110), lower at (620, 400) — so the
       *     overall cone silhouette is preserved.
       *   - Fill path walks the upper edge forward, then the lower edge
       *     in reverse, then closes with Z.
       *   - Median is a separate polyline that dwells near the cone's
       *     centerline, with its own mild swings so it reads as a third
       *     path rather than a straight line.
       */}
      <path
        d="
          M 400 260
          L 416 251 L 432 233 L 450 247 L 466 218 L 484 202
          L 502 228 L 522 188 L 540 170 L 560 198 L 582 146
          L 602 130 L 620 110
          L 620 400
          L 608 388 L 590 372 L 570 330 L 552 356 L 530 338
          L 510 298 L 492 322 L 472 304 L 456 278 L 438 292
          L 420 272 L 400 260
          Z
        "
        fill="url(#coneGradient)"
      />
      <path
        d="
          M 400 260
          L 416 251 L 432 233 L 450 247 L 466 218 L 484 202
          L 502 228 L 522 188 L 540 170 L 560 198 L 582 146
          L 602 130 L 620 110
        "
        stroke="url(#coneEdge)"
        strokeWidth="1.1"
        strokeDasharray="3 4"
        fill="none"
        strokeLinejoin="round"
      />
      <path
        d="
          M 400 260
          L 420 272 L 438 292 L 456 278 L 472 304 L 492 322
          L 510 298 L 530 338 L 552 356 L 570 330 L 590 372
          L 608 388 L 620 400
        "
        stroke="url(#coneEdge)"
        strokeWidth="1.1"
        strokeDasharray="3 4"
        fill="none"
        strokeLinejoin="round"
      />

      {/* Analog lines — structurally similar to the query, drawn
          behind it with lower opacity. Each path gets a separate
          keyframe so they breathe out of phase. */}
      <path
        className="invest__rhyme-analog invest__rhyme-analog--1"
        d="M 20 320 C 90 220, 180 360, 250 280 S 360 200, 400 260"
        fill="none"
        stroke="var(--c-analog)"
        strokeWidth="1.4"
      />
      <path
        className="invest__rhyme-analog invest__rhyme-analog--2"
        d="M 20 300 C 90 240, 180 320, 250 260 S 360 210, 400 260"
        fill="none"
        stroke="var(--c-analog-strong)"
        strokeWidth="1.4"
      />
      <path
        className="invest__rhyme-analog invest__rhyme-analog--3"
        d="M 20 280 C 90 260, 180 300, 250 240 S 360 220, 400 260"
        fill="none"
        stroke="var(--c-analog)"
        strokeWidth="1.2"
      />

      {/* Query window — the slice the user has selected. */}
      <rect
        x="290"
        y="200"
        width="110"
        height="120"
        fill="var(--accent-soft)"
        stroke="var(--accent)"
        strokeWidth="1"
        strokeDasharray="4 4"
        rx="2"
      />

      {/* Query line — the bold foreground. Slightly heavier stroke so
          it reads as the protagonist against the analog backdrop. */}
      <path
        className="invest__rhyme-query"
        d="M 20 310 C 90 230, 180 340, 250 270 S 360 200, 400 260"
        fill="none"
        stroke="var(--c-query)"
        strokeWidth="2.4"
        strokeLinecap="round"
      />

      {/*
       * Forward median line — the engine's best guess for what happens
       * next. Like the cone edges, this is a polyline with several small
       * swings so the forecast reads as a real projection (market
       * trajectories breathe) instead of a straight ruler. Amplitude is
       * deliberately half of the edges' so the median still sits
       * visually between them and doesn't compete for attention.
       */}
      <path
        d="
          M 400 260
          L 422 252 L 444 262 L 462 246 L 482 252 L 502 234
          L 524 222 L 544 232 L 564 202 L 586 208 L 606 178
          L 620 160
        "
        fill="none"
        stroke="var(--c-cone-line)"
        strokeWidth="1.6"
        strokeDasharray="5 4"
        strokeLinejoin="round"
      />

      {/* "Now" marker — where the query ends and the forecast begins. */}
      <line
        x1="400"
        x2="400"
        y1="70"
        y2="420"
        stroke="var(--accent)"
        strokeWidth="0.8"
        strokeDasharray="2 4"
        opacity="0.5"
      />
      <circle cx="400" cy="260" r="5" fill="var(--c-query)" />
      <circle
        cx="400"
        cy="260"
        r="5"
        fill="none"
        stroke="var(--c-query)"
        strokeWidth="1"
        className="invest__rhyme-pulse"
      />

      {/* Axis labels — barely there, just enough to cue "this is a
          time-series chart" without shouting. */}
      <text x="395" y="60" className="invest__rhyme-axis" textAnchor="end">
        NOW
      </text>
      <text x="410" y="60" className="invest__rhyme-axis" textAnchor="start">
        FORWARD
      </text>
    </svg>
  );
}

