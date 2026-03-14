"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const links = [
  { href: "/", label: "Dashboard" },
  { href: "/search", label: "Search" },
];

export function Nav() {
  const pathname = usePathname();

  return (
    <nav className="nav-bar" aria-label="Main navigation">
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
