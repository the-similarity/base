"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { scannerProductRoutes } from "../lib/product-boundary";

const links = [
  ...scannerProductRoutes,
  { href: "/labs", label: "Labs" },
];

export function Nav() {
  const pathname = usePathname();

  return (
    <nav className="nav-bar" aria-label="Main navigation">
      <span className="nav-bar__logo">THE SIMILARITY</span>
      <span className="nav-bar__sep" />
      {links.map((link) => {
        const isActive =
          link.href === "/"
            ? pathname === "/"
            : pathname.startsWith(link.href);

        return (
          <Link
            key={link.href}
            href={link.href}
            className={`nav-link ${isActive ? "active" : ""}`}
          >
            {link.label}
          </Link>
        );
      })}
    </nav>
  );
}
