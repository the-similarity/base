import Link from "next/link";
import { labRoutes, scannerProductRoutes, landingRoute } from "../../lib/product-boundary";

/**
 * Labs index — explicit quarantine for non-scanner surfaces.
 *
 * These routes remain available so old demos and internal experiments are not
 * lost, but they are intentionally outside the scanner product path. If a lab
 * graduates into something sellable, promote it through the boundary manifest
 * first instead of linking it from scanner navigation ad hoc.
 */
export default function LabsPage() {
  return (
    <main className="page" style={{ padding: 32, overflow: "auto" }}>
      <section style={{ maxWidth: 960, margin: "0 auto" }}>
        <p className="label">Experiments</p>
        <h1>These are not the main product.</h1>
        <p>
          The main product starts at <Link href="/scanner">Find Matches</Link>.
          Marketing lives in <code>{landingRoute.href}</code>. Everything below is
          an experiment until it earns its way into the product.
        </p>

        <h2>Main product</h2>
        <ul>
          {scannerProductRoutes.map((route) => (
            <li key={route.href}>
              <Link href={route.href}>{route.label}</Link> <code>{route.href}</code>
            </li>
          ))}
        </ul>

        <h2>Experiments</h2>
        <ul>
          {labRoutes.map((route) => (
            <li key={route.href}>
              <Link href={route.href}>{route.label}</Link> <code>{route.href}</code>
              {route.legacyHref ? <> redirects from <code>{route.legacyHref}</code></> : null}
            </li>
          ))}
        </ul>
      </section>
    </main>
  );
}
