import type { ReactNode } from "react";

export function StatusBadge({ children }: { children: ReactNode }) {
  return <span className="tomorrow-status-badge">{children}</span>;
}

