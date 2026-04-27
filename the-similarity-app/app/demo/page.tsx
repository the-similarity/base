"use client";

/**
 * Demo — a standalone, presentation-ready trailer of the workstation.
 *
 * Embeds a looping MP4 screen-capture of the real workstation in the
 * slot where `DemoChart` used to mount, wrapped in the same marquee +
 * status bar + three-beat annotation strip. The capture autoplays on
 * every load so investors see the full motion sequence (pattern
 * search → historical analog overlay → projected path) without any
 * mouse interaction required.
 *
 * Why a video instead of the live DemoChart:
 *   - The /demo route is the "trailer" surface; the home page still
 *     embeds the interactive `DemoChart`. Separating the two means the
 *     trailer stays perfectly scripted (no empty-state edge cases, no
 *     cursor fumbling on first load) while the home page retains the
 *     live "drag the window and watch it re-match" interaction.
 *   - The workstation capture covers frames the engine fallback can't
 *     synthesize live (search UI, lens bars, regime strip, analog
 *     drawer) - the real product surface, not a trimmed demo.
 *
 * Asset pipeline: source GIF → ffmpeg (scale 1600w, 24fps, H.264
 * crf 26) → /public/workstation.mp4 (~400KB) + first-frame JPG poster.
 */

import Link from "next/link";
import { ThemeToggle } from "../../components/ui/theme-toggle";

export default function DemoPage() {
  return (
    <div className="app">
      {/* Same marquee chrome as home / workstation so the demo feels like
          part of the product, not a separate microsite. */}
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
                <span className="marquee__item">Quick demo &middot; pattern match + forward projection</span>
                <span className="marquee__item">Find what rhymes &middot; model what evolves &middot; simulate what comes next</span>
              </span>
            ))}
          </div>
        </div>
        <div className="nav__right">
          <ThemeToggle />
        </div>
      </div>

      <main className="page demo-page">
        <section className="demo-page__inner">
          {/* Thin header strip — gives the investor a one-line orientation
              before the chart. Kept tight so the chart itself dominates. */}
          <header className="demo-page__head">
            <div className="label">Quick demo</div>
            <h1 className="demo-page__title">
              One chart. One analog. One projection.
            </h1>
            <p className="demo-page__lede">
              The shaded box is the moment we&rsquo;re in. The fainter line
              behind it is the single most similar moment we&rsquo;ve ever
              seen. The cone on the right is what happened last time — and
              the most likely path ahead.
            </p>
          </header>

          {/* Looping screen-capture of the real workstation. Swapped in for
              the interactive DemoChart so the /demo page reads as a
              "trailer" - the full motion sequence plays automatically
              without requiring a mouse to explore. Muted + autoplay +
              loop + playsInline are all required for reliable mobile
              autoplay. Poster shows the first frame until the MP4 loads. */}
          <div className="demo-page__chart demo-page__video">
            <video
              src="/workstation.mp4"
              poster="/workstation.jpg"
              autoPlay
              muted
              loop
              playsInline
            />
          </div>

          {/* Three-beat annotation strip. Each row reinforces a single
              visual element in the chart without explaining the math —
              the goal is for a first-time viewer to name what they&rsquo;re
              seeing in under five seconds. */}
          <div className="demo-page__beats">
            <article className="demo-page__beat">
              <div className="demo-page__beat-num">01</div>
              <div className="demo-page__beat-body">
                <div className="demo-page__beat-head">The current pattern</div>
                <div className="demo-page__beat-sub">
                  The highlighted window on the right is a drawdown we&rsquo;re
                  living through right now. The question is: what happens
                  next?
                </div>
              </div>
            </article>
            <article className="demo-page__beat">
              <div className="demo-page__beat-num">02</div>
              <div className="demo-page__beat-body">
                <div className="demo-page__beat-head">A historical analog</div>
                <div className="demo-page__beat-sub">
                  The fainter line inside the window is the single moment from
                  earlier in history where prices moved most similarly. The
                  match score sits in the chart header.
                </div>
              </div>
            </article>
            <article className="demo-page__beat">
              <div className="demo-page__beat-num">03</div>
              <div className="demo-page__beat-body">
                <div className="demo-page__beat-head">The projected path</div>
                <div className="demo-page__beat-sub">
                  The green band extending past &ldquo;today&rdquo; is how
                  that analog resolved. Its median line is the most likely
                  forward path, P10–P90 is the range of plausibility.
                </div>
              </div>
            </article>
          </div>

          <div className="demo-page__cta-row">
            {/* Calendly replaces the old "Open the full workstation" link -
                the pitch posture is "request a live demo" everywhere
                outside the home page, same as the invest CTAs. Anchor
                + target=_blank keeps the pitch tab alive for them to
                come back to. rel=noopener is required with target=_blank
                to avoid window.opener leakage. */}
            <a
              href="https://calendly.com/buyan-khurel/30min"
              target="_blank"
              rel="noopener noreferrer"
              className="home__cta home__cta--primary"
            >
              Request a live demo
            </a>
            <Link href="/" className="home__cta">
              Back to the pitch
            </Link>
          </div>
        </section>
      </main>

      <footer className="statusbar">
        <span className="statusbar__item"><b>engine</b> v4.14 &middot; nine lenses</span>
        <span className="statusbar__sep">│</span>
        <span className="statusbar__item">surface <b>demo</b></span>
        <div className="statusbar__right">
          {/* Status-bar CTA mirrors the page CTA - "request a live demo"
              via Calendly rather than routing into the full workstation,
              keeping the investor journey pointed at a meeting booking. */}
          <span className="statusbar__item">
            want to try it live?{" "}
            <a
              href="https://calendly.com/buyan-khurel/30min"
              target="_blank"
              rel="noopener noreferrer"
              className="kbd kbd--link"
            >
              request a demo
            </a>
          </span>
        </div>
      </footer>
    </div>
  );
}
