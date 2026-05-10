import type { HTMLAttributes } from "react";

export function Card({ className, ...props }: HTMLAttributes<HTMLElement>) {
  return (
    <section
      className={["tomorrow-card", className].filter(Boolean).join(" ")}
      {...props}
    />
  );
}

