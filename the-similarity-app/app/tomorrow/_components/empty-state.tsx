import type { ReactNode } from "react";

export function EmptyState({
  title,
  children,
  action,
}: {
  title: string;
  children: ReactNode;
  action?: ReactNode;
}) {
  return (
    <section className="tomorrow-empty-state">
      <div style={{ color: "var(--ink)", fontSize: 14, fontWeight: 650 }}>{title}</div>
      <div style={{ fontSize: 13, lineHeight: 1.5 }}>{children}</div>
      {action}
    </section>
  );
}

