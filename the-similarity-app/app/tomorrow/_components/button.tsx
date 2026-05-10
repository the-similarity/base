import type { ButtonHTMLAttributes, ReactNode } from "react";

type ButtonVariant = "primary" | "default" | "ghost";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  icon?: ReactNode;
}

export function Button({
  variant = "default",
  icon,
  children,
  className,
  ...props
}: ButtonProps) {
  return (
    <button
      className={["tomorrow-button", className].filter(Boolean).join(" ")}
      data-variant={variant}
      {...props}
    >
      {icon}
      {children}
    </button>
  );
}

