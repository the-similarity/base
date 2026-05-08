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
        <p className="label">Product boundary</p>
        <h1>Labs are isolated from the setup scanner.</h1>
        <p>
          Local product development now starts at <Link href="/scanner">/scanner</Link>.
          Marketing belongs to <code>{landingRoute.href}</code>. The links below are
          retained as experiments, demos, or archival product concepts; they are not
          part of the setup scanner release gate unless promoted intentionally.
        </p>

        <h2>Scanner product routes</h2>
        <ul>
          {scannerProductRoutes.map((route) => (
            <li key={route.href}>
              <Link href={route.href}>{route.label}</Link> <code>{route.href}</code>
            </li>
          ))}
        </ul>

        <h2>Lab routes</h2>
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
