"use client";

/**
 * /fractal — embeds the standalone Three.js world/terrain sim.
 *
 * The fractal project lives at repo root (`the-similarity-fractal/`) as a
 * pure-ESM Three.js app with its own `index.html`. Rather than rewrite it
 * as a React component, we symlink the project into
 * `the-similarity-app/public/fractal-static/` so Next.js serves it as
 * static assets, and this page renders a full-bleed iframe pointing at
 * `/fractal-static/index.html`.
 *
 * Why an iframe:
 *   - The fractal app owns its own top-level CSS (dark bg, fixed-position
 *     control panels). Inlining it into this Next page would require
 *     rewiring those selectors to something scoped.
 *   - The sim mounts into a `<canvas>` at document-root scale; sharing a
 *     Next layout would force us to split its mount math.
 *   - The iframe gives us a clean sandbox for the separate JS bundle
 *     (three.js + GLSL shaders) without Next's bundler touching it.
 *
 * No marquee / status bar here — the fractal UI is a full-viewport
 * experience. A single floating back button top-right lands the user
 * back on `/` for deep-linked visitors.
 */

import Link from "next/link";
import type { CSSProperties } from "react";

// Inline styles keep the fractal route's chrome self-contained rather
// than pushing its classes into the global sheet. Nothing else on the
// site uses these, so colocation is the cheapest correct move.
const hostStyle: CSSProperties = {
  position: "fixed",
  inset: 0,
  background: "#0a0a0f",
  zIndex: 1,
};

const frameStyle: CSSProperties = {
  border: 0,
  width: "100%",
  height: "100%",
  display: "block",
};

const backStyle: CSSProperties = {
  position: "fixed",
  top: 14,
  right: 14,
  zIndex: 10,
  width: 32,
  height: 32,
  display: "grid",
  placeItems: "center",
  background: "rgba(10, 10, 15, 0.85)",
  border: "1px solid rgba(255, 255, 255, 0.12)",
  color: "#e0e0e0",
  fontSize: 18,
  lineHeight: 1,
  textDecoration: "none",
  borderRadius: 8,
  backdropFilter: "blur(12px)",
  WebkitBackdropFilter: "blur(12px)",
};

export default function FractalPage() {
  return (
    <div style={hostStyle}>
      {/* Close-out affordance so users who landed here from a deep
          link have a single click back to the main surface. */}
      <Link
        href="/"
        aria-label="Back to The Similarity"
        title="Back"
        style={backStyle}
      >
        &larr;
      </Link>
      <iframe
        src="/fractal-static/index.html"
        title="Fractal 3D world sim"
        style={frameStyle}
        // The sim uses pointer capture for orbit controls and needs
        // full mouse/keyboard; leave sandbox permissive.
        allow="fullscreen"
      />
    </div>
  );
}
