"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const links = [
  { href: "/", label: "Terminal" },
  { href: "/portfolio", label: "Portfolio" },
  { href: "/search", label: "Search" },
  { href: "/strategy", label: "Strategy" },
  { href: "/reports", label: "Reports" },
  { href: "/finance", label: "Finance" },
  { href: "/explore", label: "Explore" },
  { href: "/narrative", label: "Narrative" },
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
