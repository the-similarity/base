/**
 * Product boundary manifest for the Next app.
 *
 * The current repository is still physically arranged as a legacy lab app,
 * but this manifest is the routing contract that keeps the sellable setup
 * scanner separate from experiments while the larger apps/ monorepo move is
 * pending. Product routes may appear in primary development/deploy docs and
 * scanner CI. Lab routes are explicitly non-product surfaces: useful for
 * demos, archival review, or future spin-outs, but not allowed to become the
 * default localhost experience again.
 */
export type ProductBoundaryRoute = {
  href: string;
  label: string;
  owner: "scanner" | "ghost5" | "labs" | "landing";
  status: "product" | "lab" | "external";
  legacyHref?: string;
};

export const scannerProductRoutes: ProductBoundaryRoute[] = [
  {
    href: "/scanner",
    label: "Find Matches",
    owner: "scanner",
    status: "product",
    legacyHref: "/workstation",
  },
  {
    href: "/try",
    label: "Try Demo",
    owner: "scanner",
    status: "product",
  },
  {
    href: "/ghost5",
    label: "Ghost5",
    owner: "ghost5",
    status: "product",
  },
];

export const labRoutes: ProductBoundaryRoute[] = [
  { href: "/labs/cadence", label: "Cadence", owner: "labs", status: "lab", legacyHref: "/cadence" },
  { href: "/labs/fractal", label: "Fractal", owner: "labs", status: "lab", legacyHref: "/fractal" },
  { href: "/labs/narrative", label: "Narrative", owner: "labs", status: "lab", legacyHref: "/narrative" },
  { href: "/labs/prudent", label: "Prudent", owner: "labs", status: "lab", legacyHref: "/prudent" },
  { href: "/labs/prudent-demo", label: "Prudent Demo", owner: "labs", status: "lab", legacyHref: "/prudent-demo" },
  { href: "/labs/spatium", label: "Spatium", owner: "labs", status: "lab", legacyHref: "/spatium" },
  { href: "/labs/finance", label: "Finance", owner: "labs", status: "lab", legacyHref: "/finance" },
  { href: "/labs/portfolio", label: "Portfolio Scanner", owner: "labs", status: "lab", legacyHref: "/portfolio" },
  { href: "/labs/search", label: "Search", owner: "labs", status: "lab", legacyHref: "/search" },
  { href: "/labs/reports", label: "Reports", owner: "labs", status: "lab", legacyHref: "/reports" },
  {
    href: "/labs/workstation-lumen",
    label: "Workstation Lumen",
    owner: "labs",
    status: "lab",
    legacyHref: "/workstation/lumen",
  },
  { href: "/labs/explore", label: "Explore", owner: "labs", status: "lab", legacyHref: "/explore" },
  { href: "/labs/strategy", label: "Strategy", owner: "labs", status: "lab", legacyHref: "/strategy" },
  { href: "/labs/demo", label: "Investor Demo", owner: "labs", status: "lab", legacyHref: "/demo" },
  {
    href: "/labs/case-study-spy-2026-2007",
    label: "SPY 2026/2007 Case Study",
    owner: "labs",
    status: "lab",
    legacyHref: "/case-study/spy-2026-2007",
  },
];

export const landingRoute: ProductBoundaryRoute = {
  href: "../the-similarity-landing",
  label: "Landing Site",
  owner: "landing",
  status: "external",
};

export const legacyLabRedirects = labRoutes
  .filter((route): route is ProductBoundaryRoute & { legacyHref: string } => Boolean(route.legacyHref))
  .map(({ legacyHref, href }) => ({
    source: legacyHref,
    destination: href,
    permanent: false,
  }));
