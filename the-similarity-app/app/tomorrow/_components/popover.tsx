import type { HTMLAttributes } from "react";

export function Popover({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={["tomorrow-card", className].filter(Boolean).join(" ")}
      role="dialog"
      {...props}
    />
  );
}

