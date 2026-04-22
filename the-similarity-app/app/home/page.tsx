"use client";

/**
 * Home — editorial landing page for The Similarity.
 *
 * Shares chrome (marquee bar + status bar) with the workstation at `/`
 * so the app feels continuous when users click between them, but the
 * body is a hero + "what you'll do" explainer, not the interactive
 * workstation itself.
 *
 * Copy is lifted verbatim from the workstation's header so users
 * landing here see the same orienting text they'd see inside the
 * app. The workstation keeps its copy too for now (per the
 * product brief that introduced this page).
 */

import Link from "next/link";

export default function HomePage() {
  return (
    <div className="app">
      {/* ── Marquee bar ─────────────────────────────────────────────
          Same component/markup as the workstation page so the brand
          + tagline strip stay identical. Kept inline rather than
          extracted to avoid a wide refactor; if a third page needs
          this chrome we can lift both sites into a shared layout. */}
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
                <span className="marquee__item">Structural intelligence for time, state &amp; simulation</span>
                <span className="marquee__item">Find what rhymes &middot; model what evolves &middot; simulate what comes next</span>
                <span className="marquee__item"><b>engine</b> nine lenses / four layers</span>
              </span>
            ))}
          </div>
        </div>
      </div>

      {/* ── Body ───────────────────────────────────────────────────
          Single centered column. Editorial hierarchy: eyebrow label,
          serif headline, body paragraph, primary CTA to the live
          workstation. Uses the same .label / serif / ink tokens the
          workstation uses so the typography feels like one product. */}
      <main className="page home">
        <section className="home__hero">
          <div className="label home__eyebrow">Retrieve &middot; analog workstation</div>
          <h1 className="home__headline">
            What does <em>this</em> moment rhyme with?
          </h1>
          <p className="home__lede">
            Drag the query window along the timeline. The engine re-ranks 6
            historical matches and redraws the forecast cone. Pin analogs to
            overlay them.
          </p>
          <div className="home__cta-row">
            <Link href="/" className="home__cta home__cta--primary">
              Open the workstation
            </Link>
            <Link href="/explore" className="home__cta">
              Explore state map
            </Link>
          </div>
        </section>

        {/* A tiny explainer strip so the page isn't just a CTA. Three
            short lines describe what the app does, each one cross-
            referencing a surface the user can click into. Kept
            intentionally minimal — the app's real value is the
            workstation, not marketing copy. */}
        <section className="home__tiles" aria-label="What the workstation does">
          <article className="home__tile">
            <div className="home__tile-num">01</div>
            <h2 className="home__tile-title">Retrieve</h2>
            <p className="home__tile-body">
              Slice any moment on the timeline. The engine searches the full
              history for structurally similar windows using nine lenses —
              shape, dynamics, scaling, rhythm, and five more.
            </p>
          </article>
          <article className="home__tile">
            <div className="home__tile-num">02</div>
            <h2 className="home__tile-title">Compare</h2>
            <p className="home__tile-body">
              Each top match lands on the chart as its own forward projection.
              Activate the ones you trust. The right panel shows how tightly
              each analog agrees with the query across all nine lenses.
            </p>
          </article>
          <article className="home__tile">
            <div className="home__tile-num">03</div>
            <h2 className="home__tile-title">Forecast</h2>
            <p className="home__tile-body">
              Pin the analogs driving your view and the forecast cone
              re-centers on their curated set. The trust strip tells you
              whether to believe it.
            </p>
          </article>
        </section>
      </main>

      {/* ── Status bar ─────────────────────────────────────────────
          Minimal static version of the workstation footer — just the
          engine line + keyboard hint. No live-state pieces (feed,
          window, date) since those only make sense in-app. */}
      <footer className="statusbar">
        <span className="statusbar__item"><b>engine</b> v4.14 &middot; nine lenses</span>
        <span className="statusbar__sep">&boxv;</span>
        <span className="statusbar__item">home</span>
        <div className="statusbar__right">
          <span className="statusbar__item">
            press <Link href="/" className="kbd kbd--link">enter</Link> to open the workstation
          </span>
        </div>
      </footer>
    </div>
  );
}
